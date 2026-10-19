"""Validação dos cadastros do painel: empresas, usuários, dispositivos, veículos e viagens.

Cada função recebe o JSON enviado pela tela e devolve (erros, documento):
erros vazio = válido, e o documento já normalizado para gravar no Cosmos DB.
Não depende do Azure: testado com `python -m unittest`.
"""

import re
from datetime import datetime

from contrato import PERFIS_CARGA
from seguranca import PERFIS

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
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
        erros.append("perfil: use " + " ou ".join(PERFIS))
    senha = _senha(dados, "senha", erros)
    if erros:
        return erros, None
    return [], {"id": email.lower(), "nome": nome, "perfil": perfil, "senha": senha}


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
