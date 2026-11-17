"""Validação dos cadastros do painel: empresas, usuários, dispositivos, veículos e viagens.

Cada função recebe o JSON enviado pela tela e devolve (erros, documento):
erros vazio = válido, e o documento já normalizado para gravar no Cosmos DB.
Não depende do Azure: testado com `python -m unittest`.
"""

import re
from datetime import datetime

from contrato import PERFIS_CARGA
from seguranca import PERFIS

# Sem / \ ? # : o e-mail é o id do documento no Cosmos, e o SDK recusa esses caracteres em id.
EMAIL = re.compile(r"^[^@\s/\\?#]+@[^@\s/\\?#]+\.[^@\s/\\?#]+$")
CODIGO = re.compile(r"^[A-Z0-9-]{3,20}$")
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{3,40}$")
SENHA_MIN = 8


def _texto(dados, campo, maximo, erros, obrigatorio=True):
    valor = dados.get(campo)
    # Formulário manda campo opcional vazio como "": vale como não informado.
    if not obrigatorio and (valor is None or (isinstance(valor, str) and not valor.strip())):
        return None
    if not isinstance(valor, str) or not valor.strip():
        erros.append(f"{campo}: obrigatório")
        return None
    valor = valor.strip()
    if len(valor) > maximo:
        erros.append(f"{campo}: no máximo {maximo} caracteres")
    return valor


def _data(dados, campo, erros, obrigatorio=True):
    valor = dados.get(campo)
    if valor in (None, "") and not obrigatorio:
        return None
    try:
        data = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        erros.append(f"{campo}: data e hora inválidas (use ISO 8601)")
        return None
    if data.tzinfo is None:
        erros.append(f"{campo}: informe o fuso horário")
        return None
    return data


def _senha(dados, campo, erros):
    senha = dados.get(campo)
    if not isinstance(senha, str) or len(senha) < SENHA_MIN:
        erros.append(f"{campo}: no mínimo {SENHA_MIN} caracteres")
        return None
    if len(senha) > 128:
        erros.append(f"{campo}: no máximo 128 caracteres")
        return None
    return senha


def validar_usuario(dados):
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"], None
    erros = []
    email = _texto(dados, "email", 120, erros)
    if email and not EMAIL.match(email):
        erros.append("email: formato inválido")
    nome = _texto(dados, "nome", 80, erros)
    perfil = dados.get("perfil")
    if perfil not in PERFIS:
        erros.append("perfil: use " + ", ".join(PERFIS[:-1]) + " ou " + PERFIS[-1])
    veiculo = validar_vinculo(dados, perfil, erros)
    senha = _senha(dados, "senha", erros)
    if erros:
        return erros, None
    doc = {"id": email.lower(), "nome": nome, "perfil": perfil, "senha": senha}
    if veiculo:
        doc["veiculo"] = veiculo
    return [], doc


def validar_vinculo(dados, perfil, erros):
    """Veículo do motorista: obrigatório nesse perfil e proibido nos outros.

    Confere só o formato do código; se o veículo existe na empresa, quem confere
    é a rota (precisa do banco). Devolve o código em maiúsculas ou None.
    """
    valor = dados.get("veiculo")
    vazio = valor is None or (isinstance(valor, str) and not valor.strip())
    if perfil != "motorista":
        if not vazio:
            erros.append("veiculo: só o perfil motorista tem veículo vinculado")
        return None
    if vazio or not isinstance(valor, str):
        erros.append("veiculo: obrigatório para o perfil motorista")
        return None
    codigo = valor.strip().upper()
    if not CODIGO.match(codigo):
        erros.append("veiculo: 3 a 20 letras, números ou hífen (ex.: CT-001)")
        return None
    return codigo


def validar_empresa(dados):
    """Cadastro aberto: a empresa e o primeiro gestor dela."""
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"], None
    erros = []
    empresa = _texto(dados, "empresa", 80, erros)
    erros_usuario, usuario = validar_usuario({**dados, "perfil": "gestor"})
    erros += erros_usuario
    if erros:
        return erros, None
    return [], {"empresa": empresa, "usuario": usuario}


def validar_troca_senha(dados):
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"], None
    erros = []
    atual = dados.get("atual")
    if not isinstance(atual, str) or not atual:
        erros.append("atual: informe a senha atual")
    nova = _senha(dados, "nova", erros)
    if not erros and nova == atual:
        erros.append("nova: deve ser diferente da atual")
    if erros:
        return erros, None
    return [], {"atual": atual, "nova": nova}


def validar_exclusao_empresa(dados):
    """Pedido de exclusão da empresa: o texto de confirmação e a senha atual do gestor.

    Só confere o formato; se a confirmação bate com o nome ou o código da empresa
    e se a senha está certa, quem confere é a rota (precisa do banco).
    """
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"], None
    erros = []
    confirmacao = dados.get("confirmacao")
    if not isinstance(confirmacao, str) or not confirmacao.strip():
        erros.append("confirmacao: digite o nome da empresa para confirmar")
    senha = dados.get("senha")
    if not isinstance(senha, str) or not senha:
        erros.append("senha: informe a sua senha atual")
    elif len(senha) > 128:
        erros.append("senha: no máximo 128 caracteres")
    if erros:
        return erros, None
    return [], {"confirmacao": confirmacao.strip(), "senha": senha}


def validar_dispositivo(dados):
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"], None
    erros = []
    device = _texto(dados, "id", 40, erros)
    if device and not DEVICE_ID.match(device):
        erros.append("id: letras, números, _ ou - (3 a 40)")
    descricao = _texto(dados, "descricao", 60, erros, obrigatorio=False)
    if erros:
        return erros, None
    return [], {"id": device.lower(), "descricao": descricao or ""}


def validar_veiculo(dados):
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"], None
    erros = []
    codigo = _texto(dados, "id", 20, erros)
    if codigo:
        codigo = codigo.upper()
        if not CODIGO.match(codigo):
            erros.append("id: 3 a 20 letras, números ou hífen (ex.: CT-001)")
    tipo = _texto(dados, "tipo", 60, erros)
    device = _texto(dados, "deviceId", 40, erros)
    if device and not DEVICE_ID.match(device):
        erros.append("deviceId: letras, números, _ ou - (3 a 40)")
    elif device:
        device = device.lower()
    dispositivo = _texto(dados, "dispositivo", 60, erros, obrigatorio=False)
    perfil = dados.get("perfil", "demonstrativo")
    if perfil not in PERFIS_CARGA:
        erros.append("perfil: use " + ", ".join(PERFIS_CARGA))
    if erros:
        return erros, None
    return [], {"id": codigo, "tipo": tipo, "deviceId": device,
                "dispositivo": dispositivo or "", "perfil": perfil}


def validar_viagem(dados):
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"], None
    erros = []
    veiculo = _texto(dados, "veiculo", 20, erros)
    origem = _texto(dados, "origem", 80, erros)
    destino = _texto(dados, "destino", 80, erros)
    carga = _texto(dados, "carga", 120, erros)
    inicio = _data(dados, "inicio", erros)
    fim = _data(dados, "fim", erros, obrigatorio=False)
    if inicio and fim and fim <= inicio:
        erros.append("fim: deve ser depois do início")
    if erros:
        return erros, None
    return [], {"veiculo": veiculo.upper(), "origem": origem, "destino": destino,
                "carga": carga, "inicio": inicio.isoformat(),
                "fim": fim.isoformat() if fim else None}
