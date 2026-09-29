"""Azure Function do ColdTrack Edge.

Dispositivo (chave própria do dispositivo no header `x-device-key`):
  POST /api/telemetria          leitura do ESP32: valida, classifica e grava

Público:
  POST /api/empresas            cadastro de empresa nova + primeiro gestor
  POST /api/login               e-mail e senha -> token de 8 h
  GET  /api/perfis              perfis de carga e faixas de temperatura

Painel (token do login no header `Authorization: Bearer <token>`):
  GET  /api/eu                  dados do usuário logado
  POST /api/senha               troca a própria senha                   (operador, gestor)
  GET  /api/leituras            últimas leituras de um dispositivo     (operador, gestor)
  GET  /api/dispositivos        sensores da empresa                     (operador, gestor)
  POST/PUT/DELETE /api/dispositivos[/{id}]  registra, troca a chave, remove (gestor)
  GET  /api/veiculos            frota                                   (operador, gestor)
  POST/PUT/DELETE /api/veiculos[/{id}]                                   (gestor)
  GET  /api/viagens             viagens                                 (operador, gestor)
  POST/PUT/DELETE /api/viagens[/{id}]                                    (gestor)
  GET/POST/PUT/DELETE /api/usuarios[/{id}]                               (gestor)

Cada empresa só enxerga os próprios dados: o token leva a empresa, e toda
consulta filtra por ela. Veículos e viagens são gravados com id
"<empresa>~<código>", para duas empresas poderem usar o mesmo código.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import azure.functions as func
from azure.cosmos import CosmosClient, exceptions

from cadastros import (validar_dispositivo, validar_empresa, validar_troca_senha,
                       validar_usuario, validar_veiculo, validar_viagem, SENHA_MIN)
from contrato import (PERFIL_PADRAO, PERFIS_CARGA, classificar, faixa, id_leitura, mesma_leitura,
                      filtros_de_leitura, validar)
from seguranca import (bloqueado_ate, conferir_chave, conferir_senha,
                       gerar_chave_dispositivo, gerar_hash, gerar_token,
                       hash_chave, ler_token, registrar_falha, token_do_cabecalho)

# Quem confere o acesso é o próprio código (token ou chave do dispositivo).
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Hash de uma senha aleatória, usado quando o e-mail não existe (mesmo tempo de resposta).
HASH_FALSO = gerar_hash(uuid.uuid4().hex)

TODOS = ("operador", "gestor")
GESTOR = ("gestor",)
SEP = "~"

_banco = None
_containers = {}


def container(nome=None):
    global _banco
    nome = nome or os.getenv("COSMOS_CONTAINER", "leituras")
    if nome not in _containers:
        if _banco is None:
            cliente = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION"])
            _banco = cliente.get_database_client(os.getenv("COSMOS_DATABASE", "coldtrack"))
        _containers[nome] = _banco.get_container_client(nome)
    return _containers[nome]


def ler(nome, item_id):
    try:
        return container(nome).read_item(item_id, partition_key=item_id)
    except exceptions.CosmosResourceNotFoundError:
        return None


def resposta(corpo, status=200):
    return func.HttpResponse(
        json.dumps(corpo, ensure_ascii=False),
        status_code=status,
        mimetype="application/json",
    )


def corpo_json(req):
    try:
        return req.get_json(), None
    except ValueError:
        return None, resposta({"erros": ["corpo não é JSON válido"]}, 400)


def limpo(doc):
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def autorizar(req, perfis):
    """Devolve (usuario, None) ou (None, resposta de erro 401/403).

    Além da assinatura do token, confere o usuário no banco: conta removida,
    senha trocada ou empresa diferente derrubam o token na hora, e o perfil
    vale o atual (não o de quando o token foi emitido).
    """
    token = token_do_cabecalho(req.headers.get("Authorization"))
    carga = ler_token(token, os.environ["JWT_SECRET"]) if token else None
    usuario = ler("usuarios", carga["sub"]) if carga else None
    if (usuario is None
            or usuario.get("empresaId") != carga["emp"]
            or usuario.get("sessao", 0) != carga.get("ver", 0)):
        return None, resposta({"erros": ["faça login para continuar"]}, 401)
    if usuario["perfil"] not in perfis:
        return None, resposta({"erros": ["seu perfil não tem acesso a esta ação"]}, 403)
    return usuario, None


def publico(usuario):
    return {k: usuario[k] for k in ("id", "nome", "perfil", "empresaId") if k in usuario}


def com_empresa(usuario):
    empresa = ler("empresas", usuario["empresaId"])
    return {**publico(usuario), "empresa": empresa["nome"] if empresa else ""}


def lista(nome, empresa, campos="*"):
    itens = container(nome).query_items(
        f"SELECT {campos} FROM c WHERE c.empresaId = @e",
        parameters=[{"name": "@e", "value": empresa}],
        enable_cross_partition_query=True)
    return [limpo(i) for i in itens]


def id_interno(empresa, codigo):
    return f"{empresa}{SEP}{codigo}"


def id_externo(doc):
    doc = limpo(doc)
    doc["id"] = doc["id"].split(SEP, 1)[-1]
    return doc


# ------------------------------------------------------------ dispositivo

@app.route(route="telemetria", methods=["POST"])
def telemetria(req: func.HttpRequest) -> func.HttpResponse:
    dados, erro = corpo_json(req)
    if erro:
        return erro

    erros = validar(dados)
    if erros:
        logging.warning("telemetria rejeitada: %s", erros)
        return resposta({"erros": erros}, 400)

    # A chave vale só para o próprio deviceId: um sensor não grava por outro.
    dispositivo = ler("dispositivos", dados["deviceId"].lower())
    if dispositivo is None or not conferir_chave(req.headers.get("x-device-key"),
                                                 dispositivo.get("chaveHash")):
        logging.warning("telemetria sem chave válida para %s", dados["deviceId"])
        return resposta({"erros": ["dispositivo não registrado ou chave inválida"]}, 401)

    empresa = dispositivo["empresaId"]
    veiculo = next(iter(container("veiculos").query_items(
        "SELECT TOP 1 c.perfil FROM c WHERE c.empresaId = @e AND c.deviceId = @d",
        parameters=[{"name": "@e", "value": empresa},
                    {"name": "@d", "value": dispositivo["id"]}],
        enable_cross_partition_query=True)), None)
    perfil = veiculo["perfil"] if veiculo else PERFIL_PADRAO

    recebido = datetime.now(timezone.utc)
    # Sem medidoEm (firmware antigo), o horário da medição é o do recebimento.
    medido = (
        datetime.fromtimestamp(dados["medidoEm"], timezone.utc)
        if "medidoEm" in dados
        else recebido
    )

    leitura = {
        "id": id_leitura(dispositivo["id"], dados.get("medidoEm")) or str(uuid.uuid4()),
        "deviceId": dispositivo["id"],
        "empresaId": empresa,
        "temperatura": float(dados["temperatura"]),
        "umidade": float(dados["umidade"]),
        "rssi": None if dados["rssi"] is None else int(dados["rssi"]),
        "perfil": perfil,
        "status": classificar(dados["temperatura"], perfil),
        "medidoEm": medido.isoformat(),
        "recebidoEm": recebido.isoformat(),
    }
    try:
        # create, nunca upsert: leitura gravada não se altera.
        container().create_item(leitura)
    except exceptions.CosmosResourceExistsError:
        gravada = container().read_item(leitura["id"], partition_key=leitura["deviceId"])
        if mesma_leitura(gravada, leitura):
            # Reenvio depois de resposta perdida: já está gravada, o sensor tira da fila.
            return resposta({"id": gravada["id"], "duplicada": True}, 200)
        logging.warning("telemetria: %s já gravada com outros valores (relógio repetido ou adulteração)",
                        leitura["id"])
        return resposta({"erros": ["já existe leitura deste sensor neste horário, com outros valores"]}, 409)
    # A faixa volta na resposta: o sensor acende o LED certo para a carga do veículo.
    return resposta({"id": leitura["id"], "status": leitura["status"],
                     "perfil": perfil, "faixa": faixa(perfil)}, 201)


# ------------------------------------------------------------ acesso

@app.route(route="perfis", methods=["GET"])
def perfis(req: func.HttpRequest) -> func.HttpResponse:
    return resposta({"perfis": [{"id": k, **v} for k, v in PERFIS_CARGA.items()]})


@app.route(route="empresas", methods=["POST"])
def empresas(req: func.HttpRequest) -> func.HttpResponse:
    dados, erro = corpo_json(req)
    if erro:
        return erro
    erros, doc = validar_empresa(dados)
    if erros:
        return resposta({"erros": erros}, 400)

    empresa_id = "E-" + uuid.uuid4().hex[:8].upper()
    usuario = doc["usuario"]
    usuario.update({"empresaId": empresa_id, "sessao": 0,
                    "senhaHash": gerar_hash(usuario.pop("senha"))})
    # Usuário primeiro: e-mail repetido não deixa empresa órfã no banco.
    try:
        container("usuarios").create_item(usuario)
    except exceptions.CosmosResourceExistsError:
        return resposta({"erros": ["já existe uma conta com esse e-mail"]}, 409)
    container("empresas").create_item({
        "id": empresa_id, "nome": doc["empresa"],
        "criadaEm": datetime.now(timezone.utc).isoformat(),
    })
    logging.info("empresa %s criada por %s", empresa_id, usuario["id"])

    token = gerar_token(usuario, os.environ["JWT_SECRET"])
    return resposta({"token": token,
                     "usuario": {**publico(usuario), "empresa": doc["empresa"]}}, 201)


@app.route(route="login", methods=["POST"])
def login(req: func.HttpRequest) -> func.HttpResponse:
    dados, erro = corpo_json(req)
    if erro:
        return erro

    email = str((dados or {}).get("email", "")).strip().lower()
    senha = str((dados or {}).get("senha", ""))

    usuario = ler("usuarios", email) if email else None

    # Mesma mensagem e mesmo custo para e-mail inexistente e senha errada:
    # sem o hash de mentira, a resposta mais rápida revelaria quem tem conta.
    senha_ok = conferir_senha(senha, usuario["senhaHash"] if usuario else HASH_FALSO)

    if usuario is not None:
        fim = bloqueado_ate(usuario)
        if fim:
            minutos = max(1, round((fim - time.time()) / 60))
            return resposta({"erros": [
                f"muitas tentativas erradas. Tente de novo em {minutos} min."]}, 429)
        if not senha_ok:
            container("usuarios").upsert_item(registrar_falha(usuario))
        elif usuario.get("falhas"):
            usuario["falhas"] = 0
            container("usuarios").upsert_item(usuario)

    if usuario is None or not senha_ok:
        logging.warning("login recusado para %s", email or "(vazio)")
        return resposta({"erros": ["e-mail ou senha incorretos"]}, 401)

    token = gerar_token(usuario, os.environ["JWT_SECRET"])
    return resposta({"token": token, "usuario": com_empresa(usuario)})


@app.route(route="eu", methods=["GET"])
def eu(req: func.HttpRequest) -> func.HttpResponse:
    usuario, erro = autorizar(req, TODOS)
    return erro or resposta(com_empresa(usuario))


@app.route(route="senha", methods=["POST"])
def senha(req: func.HttpRequest) -> func.HttpResponse:
    usuario, erro = autorizar(req, TODOS)
    if erro:
        return erro
    dados, erro = corpo_json(req)
    if erro:
        return erro
    erros, doc = validar_troca_senha(dados)
    if erros:
        return resposta({"erros": erros}, 400)
    if not conferir_senha(doc["atual"], usuario["senhaHash"]):
        return resposta({"erros": ["atual: senha atual incorreta"]}, 400)

    # Nova versão da sessão: tokens emitidos antes (outros aparelhos) param de valer.
    usuario["senhaHash"] = gerar_hash(doc["nova"])
    usuario["sessao"] = usuario.get("sessao", 0) + 1
    container("usuarios").upsert_item(usuario)
    logging.info("%s trocou a senha", usuario["id"])
    return resposta({"token": gerar_token(usuario, os.environ["JWT_SECRET"]),
                     "usuario": com_empresa(usuario)})


# ------------------------------------------------------------ leituras

def _dispositivo_da_empresa(device, empresa):
    disp = ler("dispositivos", device.lower()) if device else None
    return disp if disp and disp.get("empresaId") == empresa else None


@app.route(route="leituras", methods=["GET"])
def leituras(req: func.HttpRequest) -> func.HttpResponse:
    usuario, erro = autorizar(req, TODOS)
    if erro:
        return erro

    device = req.params.get("deviceId")
    if not device:
        return resposta({"erros": ["informe ?deviceId="]}, 400)
    # Sensor de outra empresa responde igual a sensor inexistente.
    if _dispositivo_da_empresa(device, usuario["empresaId"]) is None:
        return resposta({"erros": ["dispositivo não encontrado"]}, 404)
    device = device.lower()
    try:
        limite = max(1, min(int(req.params.get("limite", "50")), 500))
    except ValueError:
        return resposta({"erros": ["limite deve ser inteiro"]}, 400)

    erros, filtros = filtros_de_leitura(req.params)
    if erros:
        return resposta({"erros": erros}, 400)

    condicoes = ["c.deviceId = @device", "c.empresaId = @empresa"]
    parametros = [
        {"name": "@limite", "value": limite},
        {"name": "@device", "value": device},
        {"name": "@empresa", "value": usuario["empresaId"]},
    ]
    if filtros["desde"] is not None:
        condicoes.append("c.medidoEm >= @desde")
        parametros.append({
            "name": "@desde",
            "value": datetime.fromtimestamp(filtros["desde"], timezone.utc).isoformat(),
        })
    if filtros["status"] is not None:
        condicoes.append("ARRAY_CONTAINS(@status, c.status)")
        parametros.append({"name": "@status", "value": filtros["status"]})

    itens = list(
        container().query_items(
            query=(
                "SELECT TOP @limite c.deviceId, c.temperatura, c.umidade, c.rssi, "
                "c.perfil, c.status, c.medidoEm, c.recebidoEm FROM c WHERE "
                + " AND ".join(condicoes)
                + " ORDER BY c.medidoEm DESC"
            ),
            parameters=parametros,
            partition_key=device,
        )
    )
    return resposta({"deviceId": device, "leituras": itens})


# ------------------------------------------------------------ dispositivos

@app.route(route="dispositivos/{id?}", methods=["GET", "POST", "PUT", "DELETE"])
def dispositivos(req: func.HttpRequest) -> func.HttpResponse:
    metodo = req.method.upper()
    campos = "c.id, c.descricao, c.criadoEm"

    if metodo == "GET":
        usuario, erro = autorizar(req, TODOS)
        return erro or resposta({"dispositivos": lista("dispositivos", usuario["empresaId"], campos)})

    gestor, erro = autorizar(req, GESTOR)
    if erro:
        return erro
    empresa = gestor["empresaId"]
    item_id = (req.route_params.get("id") or "").lower()

    if metodo == "POST":
        dados, erro = corpo_json(req)
        if erro:
            return erro
        erros, doc = validar_dispositivo(dados)
        if erros:
            return resposta({"erros": erros}, 400)
        chave = gerar_chave_dispositivo()
        doc.update({"empresaId": empresa, "chaveHash": hash_chave(chave),
                    "criadoEm": datetime.now(timezone.utc).isoformat()})
        try:
            container("dispositivos").create_item(doc)
        except exceptions.CosmosResourceExistsError:
            return resposta({"erros": [f"o ID {doc['id']} já está em uso; escolha outro"]}, 409)
        logging.info("%s registrou o dispositivo %s", gestor["id"], doc["id"])
        # A chave aparece só agora: o banco guarda apenas o hash.
        return resposta({"id": doc["id"], "descricao": doc["descricao"],
                         "criadoEm": doc["criadoEm"], "chave": chave}, 201)

    disp = _dispositivo_da_empresa(item_id, empresa)
    if not item_id or disp is None:
        return resposta({"erros": ["dispositivo não encontrado"]}, 404)

    if metodo == "PUT":
        # Nova chave: a anterior para de valer na hora (sensor perdido ou chave vazada).
        chave = gerar_chave_dispositivo()
        disp["chaveHash"] = hash_chave(chave)
        container("dispositivos").upsert_item(disp)
        logging.info("%s trocou a chave do dispositivo %s", gestor["id"], item_id)
        return resposta({"id": item_id, "chave": chave})

    em_uso = list(container("veiculos").query_items(
        "SELECT VALUE c.id FROM c WHERE c.empresaId = @e AND c.deviceId = @d",
        parameters=[{"name": "@e", "value": empresa}, {"name": "@d", "value": item_id}],
        enable_cross_partition_query=True))
    if em_uso:
        codigo = em_uso[0].split(SEP, 1)[-1]
        return resposta({"erros": [f"o veículo {codigo} usa este sensor; remova ou troque o veículo antes"]}, 409)
    container("dispositivos").delete_item(item_id, partition_key=item_id)
    logging.info("%s removeu o dispositivo %s", gestor["id"], item_id)
    return func.HttpResponse(status_code=204)


# ------------------------------------------------------------ cadastros

def _cadastro(req, nome, validar_fn, gerar_id=None):
    """GET lista (todos); POST cria, PUT atualiza, DELETE remove (gestor)."""
    metodo = req.method.upper()
    item_id = req.route_params.get("id")

    if metodo == "GET":
        usuario, erro = autorizar(req, TODOS)
        return erro or resposta({nome: [id_externo(d) for d in lista(nome, usuario["empresaId"])]})

    usuario, erro = autorizar(req, GESTOR)
    if erro:
        return erro
    empresa = usuario["empresaId"]

    if metodo == "DELETE":
        if not item_id:
            return resposta({"erros": ["informe o id na rota"]}, 400)
        try:
            container(nome).delete_item(id_interno(empresa, item_id),
                                        partition_key=id_interno(empresa, item_id))
        except exceptions.CosmosResourceNotFoundError:
            return resposta({"erros": ["não encontrado"]}, 404)
        logging.info("%s removeu %s/%s", usuario["id"], nome, item_id)
        return func.HttpResponse(status_code=204)

    dados, erro = corpo_json(req)
    if erro:
        return erro
    if metodo == "PUT" and not item_id:
        return resposta({"erros": ["informe o id na rota"]}, 400)
    if metodo == "POST" and gerar_id:
        dados = {**dados, "id": gerar_id()} if isinstance(dados, dict) else dados
    erros, doc = validar_fn(dados, empresa, item_id if metodo == "PUT" else None)
    if erros:
        return resposta({"erros": erros}, 400)

    if metodo == "PUT":
        doc["id"] = item_id
        interno = id_interno(empresa, item_id)
        if ler(nome, interno) is None:
            return resposta({"erros": ["não encontrado"]}, 404)
        container(nome).upsert_item({**doc, "id": interno, "empresaId": empresa})
        return resposta(doc)

    try:
        container(nome).create_item({**doc, "id": id_interno(empresa, doc["id"]),
                                     "empresaId": empresa})
    except exceptions.CosmosResourceExistsError:
        return resposta({"erros": [f"já existe um cadastro com id {doc['id']}"]}, 409)
    logging.info("%s criou %s/%s", usuario["id"], nome, doc["id"])
    return resposta(doc, 201)


def _validar_veiculo_na_empresa(dados, empresa, editando):
    erros, doc = validar_veiculo(dados)
    if erros:
        return erros, doc
    if _dispositivo_da_empresa(doc["deviceId"], empresa) is None:
        return [f"deviceId: o sensor {doc['deviceId']} não está registrado em Sensores"], None
    outro = [c for c in container("veiculos").query_items(
        "SELECT VALUE c.id FROM c WHERE c.empresaId = @e AND c.deviceId = @d",
        parameters=[{"name": "@e", "value": empresa}, {"name": "@d", "value": doc["deviceId"]}],
        enable_cross_partition_query=True)
        if c != id_interno(empresa, editando or "")]
    if outro:
        return [f"deviceId: o sensor já está no veículo {outro[0].split(SEP, 1)[-1]}"], None
    return [], doc


@app.route(route="veiculos/{id?}", methods=["GET", "POST", "PUT", "DELETE"])
def veiculos(req: func.HttpRequest) -> func.HttpResponse:
    return _cadastro(req, "veiculos", _validar_veiculo_na_empresa)


def _validar_viagem_na_empresa(dados, empresa, editando):
    erros, doc = validar_viagem(dados)
    if erros:
        return erros, doc
    if ler("veiculos", id_interno(empresa, doc["veiculo"])) is None:
        return [f"veiculo: {doc['veiculo']} não está cadastrado"], None
    doc["id"] = dados.get("id") if isinstance(dados, dict) else None
    return [], doc


@app.route(route="viagens/{id?}", methods=["GET", "POST", "PUT", "DELETE"])
def viagens(req: func.HttpRequest) -> func.HttpResponse:
    return _cadastro(req, "viagens", _validar_viagem_na_empresa,
                     gerar_id=lambda: "V-" + uuid.uuid4().hex[:6].upper())


@app.route(route="usuarios/{id?}", methods=["GET", "POST", "PUT", "DELETE"])
def usuarios(req: func.HttpRequest) -> func.HttpResponse:
    gestor, erro = autorizar(req, GESTOR)
    if erro:
        return erro

    empresa = gestor["empresaId"]
    metodo = req.method.upper()
    item_id = (req.route_params.get("id") or "").lower()

    if metodo == "GET":
        return resposta({"usuarios": lista("usuarios", empresa, "c.id, c.nome, c.perfil")})

    if metodo in ("PUT", "DELETE"):
        alvo = ler("usuarios", item_id) if item_id else None
        if alvo is None or alvo.get("empresaId") != empresa:
            return resposta({"erros": ["não encontrado"]}, 404)

    if metodo == "DELETE":
        if item_id == gestor["id"]:
            return resposta({"erros": ["você não pode remover o próprio usuário"]}, 400)
        container("usuarios").delete_item(item_id, partition_key=item_id)
        logging.info("%s removeu o usuário %s", gestor["id"], item_id)
        return func.HttpResponse(status_code=204)

    dados, erro = corpo_json(req)
    if erro:
        return erro

    if metodo == "PUT":
        # Gestor redefine a senha de quem esqueceu: derruba as sessões abertas
        # e libera a conta se estava bloqueada.
        nova = (dados or {}).get("senha") if isinstance(dados, dict) else None
        if not isinstance(nova, str) or not SENHA_MIN <= len(nova) <= 128:
            return resposta({"erros": [f"senha: no mínimo {SENHA_MIN} caracteres"]}, 400)
        alvo.update({"senhaHash": gerar_hash(nova), "sessao": alvo.get("sessao", 0) + 1,
                     "falhas": 0, "bloqueadoAte": 0})
        container("usuarios").upsert_item(alvo)
        logging.info("%s redefiniu a senha de %s", gestor["id"], item_id)
        return resposta(publico(alvo))

    erros, doc = validar_usuario(dados)
    if erros:
        return resposta({"erros": erros}, 400)

    doc.update({"empresaId": empresa, "sessao": 0,
                "senhaHash": gerar_hash(doc.pop("senha"))})
    try:
        container("usuarios").create_item(doc)
    except exceptions.CosmosResourceExistsError:
        return resposta({"erros": ["já existe um usuário com esse e-mail"]}, 409)
    logging.info("%s criou o usuário %s (%s)", gestor["id"], doc["id"], doc["perfil"])
    return resposta(publico(doc), 201)
