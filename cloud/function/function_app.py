"""Azure Function do ColdTrack Edge.

Dispositivo (chave da função no header `x-functions-key`):
  POST /api/telemetria          leitura do ESP32: valida, classifica e grava

Painel (token do login no header `Authorization: Bearer <token>`):
  POST /api/login               e-mail e senha -> token de 8 h
  GET  /api/eu                  dados do usuário logado
  GET  /api/leituras            últimas leituras de um dispositivo     (operador, gestor)
  GET  /api/veiculos            frota                                   (operador, gestor)
  POST/PUT/DELETE /api/veiculos[/{id}]                                   (gestor)
  GET  /api/viagens             viagens                                 (operador, gestor)
  POST/PUT/DELETE /api/viagens[/{id}]                                    (gestor)
  GET/POST/DELETE /api/usuarios[/{id}]                                   (gestor)

As rotas do painel são anônimas para a plataforma: quem confere o acesso é o
próprio código, pelo token, antes de tocar no banco.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import azure.functions as func
from azure.cosmos import CosmosClient, exceptions

from cadastros import validar_usuario, validar_veiculo, validar_viagem
from contrato import classificar, filtros_de_leitura, validar
from seguranca import (conferir_senha, gerar_hash, gerar_token, ler_token,
                       token_do_cabecalho)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
ANONIMO = func.AuthLevel.ANONYMOUS

# Hash de uma senha aleatória, usado quando o e-mail não existe (mesmo tempo de resposta).
HASH_FALSO = gerar_hash(uuid.uuid4().hex)

TODOS = ("operador", "gestor")
GESTOR = ("gestor",)

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


def autorizar(req, perfis):
    """Devolve (usuario, None) ou (None, resposta de erro 401/403)."""
    token = token_do_cabecalho(req.headers.get("Authorization"))
    usuario = ler_token(token, os.environ["JWT_SECRET"]) if token else None
    if usuario is None:
        return None, resposta({"erros": ["faça login para continuar"]}, 401)
    if usuario["perfil"] not in perfis:
        return None, resposta({"erros": ["seu perfil não tem acesso a esta ação"]}, 403)
    return usuario, None


def sem_senha(usuario):
    return {k: usuario[k] for k in ("id", "nome", "perfil") if k in usuario}


def lista(nome, consulta="SELECT * FROM c"):
    itens = container(nome).query_items(consulta, enable_cross_partition_query=True)
    return [{k: v for k, v in i.items() if not k.startswith("_")} for i in itens]


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

    recebido = datetime.now(timezone.utc)
    # Sem medidoEm (firmware antigo), o horário da medição é o do recebimento.
    medido = (
        datetime.fromtimestamp(dados["medidoEm"], timezone.utc)
        if "medidoEm" in dados
        else recebido
    )

    leitura = {
        "id": str(uuid.uuid4()),
        "deviceId": dados["deviceId"],
        "temperatura": float(dados["temperatura"]),
        "umidade": float(dados["umidade"]),
        "rssi": None if dados["rssi"] is None else int(dados["rssi"]),
        "status": classificar(dados["temperatura"]),
        "medidoEm": medido.isoformat(),
        "recebidoEm": recebido.isoformat(),
    }
    container().create_item(leitura)
    return resposta({"id": leitura["id"], "status": leitura["status"]}, 201)


# ------------------------------------------------------------ acesso

@app.route(route="login", methods=["POST"], auth_level=ANONIMO)
def login(req: func.HttpRequest) -> func.HttpResponse:
    dados, erro = corpo_json(req)
    if erro:
        return erro

    email = str((dados or {}).get("email", "")).strip().lower()
    senha = str((dados or {}).get("senha", ""))

    try:
        usuario = container("usuarios").read_item(email, partition_key=email) if email else None
    except exceptions.CosmosResourceNotFoundError:
        usuario = None

    # Mesma mensagem e mesmo custo para e-mail inexistente e senha errada:
    # sem o hash de mentira, a resposta mais rápida revelaria quem tem conta.
    senha_ok = conferir_senha(senha, usuario["senhaHash"] if usuario else HASH_FALSO)
    if usuario is None or not senha_ok:
        logging.warning("login recusado para %s", email or "(vazio)")
        return resposta({"erros": ["e-mail ou senha incorretos"]}, 401)

    token = gerar_token(usuario, os.environ["JWT_SECRET"])
    return resposta({"token": token, "usuario": sem_senha(usuario)})


@app.route(route="eu", methods=["GET"], auth_level=ANONIMO)
def eu(req: func.HttpRequest) -> func.HttpResponse:
    usuario, erro = autorizar(req, TODOS)
    if erro:
        return erro
    return resposta({"id": usuario["sub"], "nome": usuario["nome"], "perfil": usuario["perfil"]})


# ------------------------------------------------------------ leituras

@app.route(route="leituras", methods=["GET"], auth_level=ANONIMO)
def leituras(req: func.HttpRequest) -> func.HttpResponse:
    _, erro = autorizar(req, TODOS)
    if erro:
        return erro

    device = req.params.get("deviceId")
    if not device:
        return resposta({"erros": ["informe ?deviceId="]}, 400)
    try:
        limite = max(1, min(int(req.params.get("limite", "50")), 500))
    except ValueError:
        return resposta({"erros": ["limite deve ser inteiro"]}, 400)

    erros, filtros = filtros_de_leitura(req.params)
    if erros:
        return resposta({"erros": erros}, 400)

    condicoes = ["c.deviceId = @device"]
    parametros = [
        {"name": "@limite", "value": limite},
        {"name": "@device", "value": device},
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
                "c.status, c.medidoEm, c.recebidoEm FROM c WHERE "
                + " AND ".join(condicoes)
                + " ORDER BY c.medidoEm DESC"
            ),
            parameters=parametros,
            partition_key=device,
        )
    )
    return resposta({"deviceId": device, "leituras": itens})


# ------------------------------------------------------------ cadastros

def _cadastro(req, nome, validar_fn, gerar_id=None):
    """GET lista (todos); POST cria, PUT atualiza, DELETE remove (gestor)."""
    metodo = req.method.upper()
    item_id = req.route_params.get("id")

    if metodo == "GET":
        _, erro = autorizar(req, TODOS)
        return erro or resposta({nome: lista(nome)})

    usuario, erro = autorizar(req, GESTOR)
    if erro:
        return erro

    if metodo == "DELETE":
        if not item_id:
            return resposta({"erros": ["informe o id na rota"]}, 400)
        try:
            container(nome).delete_item(item_id, partition_key=item_id)
        except exceptions.CosmosResourceNotFoundError:
            return resposta({"erros": ["não encontrado"]}, 404)
        logging.info("%s removeu %s/%s", usuario["sub"], nome, item_id)
        return func.HttpResponse(status_code=204)

    dados, erro = corpo_json(req)
    if erro:
        return erro
    erros, doc = validar_fn(dados)
    if erros:
        return resposta({"erros": erros}, 400)

    if metodo == "PUT":
        if not item_id:
            return resposta({"erros": ["informe o id na rota"]}, 400)
        doc["id"] = item_id
        try:
            container(nome).read_item(item_id, partition_key=item_id)
        except exceptions.CosmosResourceNotFoundError:
            return resposta({"erros": ["não encontrado"]}, 404)
        container(nome).upsert_item(doc)
        return resposta(doc)

    if gerar_id:
        doc["id"] = gerar_id()
    try:
        container(nome).create_item(doc)
    except exceptions.CosmosResourceExistsError:
        return resposta({"erros": [f"já existe um cadastro com id {doc['id']}"]}, 409)
    logging.info("%s criou %s/%s", usuario["sub"], nome, doc["id"])
    return resposta(doc, 201)


def _veiculo_existe(codigo):
    try:
        container("veiculos").read_item(codigo, partition_key=codigo)
        return True
    except exceptions.CosmosResourceNotFoundError:
        return False


@app.route(route="veiculos/{id?}", methods=["GET", "POST", "PUT", "DELETE"], auth_level=ANONIMO)
def veiculos(req: func.HttpRequest) -> func.HttpResponse:
    return _cadastro(req, "veiculos", validar_veiculo)


def _validar_viagem_com_veiculo(dados):
    erros, doc = validar_viagem(dados)
    if not erros and not _veiculo_existe(doc["veiculo"]):
        erros = [f"veiculo: {doc['veiculo']} não está cadastrado"]
    return erros, doc


@app.route(route="viagens/{id?}", methods=["GET", "POST", "PUT", "DELETE"], auth_level=ANONIMO)
def viagens(req: func.HttpRequest) -> func.HttpResponse:
    return _cadastro(req, "viagens", _validar_viagem_com_veiculo,
                     gerar_id=lambda: "V-" + uuid.uuid4().hex[:6].upper())


@app.route(route="usuarios/{id?}", methods=["GET", "POST", "DELETE"], auth_level=ANONIMO)
def usuarios(req: func.HttpRequest) -> func.HttpResponse:
    gestor, erro = autorizar(req, GESTOR)
    if erro:
        return erro

    metodo = req.method.upper()
    item_id = (req.route_params.get("id") or "").lower()

    if metodo == "GET":
        itens = container("usuarios").query_items(
            "SELECT c.id, c.nome, c.perfil FROM c", enable_cross_partition_query=True)
        return resposta({"usuarios": list(itens)})

    if metodo == "DELETE":
        if item_id == gestor["sub"]:
            return resposta({"erros": ["você não pode remover o próprio usuário"]}, 400)
        try:
            container("usuarios").delete_item(item_id, partition_key=item_id)
        except exceptions.CosmosResourceNotFoundError:
            return resposta({"erros": ["não encontrado"]}, 404)
        logging.info("%s removeu o usuário %s", gestor["sub"], item_id)
        return func.HttpResponse(status_code=204)

    dados, erro = corpo_json(req)
    if erro:
        return erro
    erros, doc = validar_usuario(dados)
    if erros:
        return resposta({"erros": erros}, 400)

    doc["senhaHash"] = gerar_hash(doc.pop("senha"))
    try:
        container("usuarios").create_item(doc)
    except exceptions.CosmosResourceExistsError:
        return resposta({"erros": ["já existe um usuário com esse e-mail"]}, 409)
    logging.info("%s criou o usuário %s (%s)", gestor["sub"], doc["id"], doc["perfil"])
    return resposta(sem_senha(doc), 201)
