"""Alertas Web Push (VAPID) do ColdTrack.

O navegador do usuário (Android, ou iPhone com o painel instalado como app) cria
uma inscrição no serviço de push dele (FCM, Mozilla, Apple, Windows) e o painel a
envia para a API. A inscrição fica no próprio documento do usuário, campo `push`,
no container `usuarios`: herda o `empresaId` do usuário, então só recebe alertas
de sensores da empresa dele, e some junto com o usuário.

    usuarios/{email}.push = [
        {"endpoint": "https://fcm.googleapis.com/fcm/send/...",
         "keys": {"p256dh": "<chave pública do navegador>", "auth": "<segredo>"},
         "criadaEm": "2026-11-16T12:00:00+00:00"},
        ...
    ]

Quando uma leitura piora de faixa (NORMAL -> ATENCAO, NORMAL -> CRITICO ou
ATENCAO -> CRITICO), a API manda um push para cada inscrição dos operadores e
gestores da empresa e dos motoristas vinculados ao veículo daquele sensor.
Configuração (app settings da Function App):

    VAPID_PUBLIC_KEY   chave pública (base64url, ponto P-256 não comprimido)
    VAPID_PRIVATE_KEY  chave privada (base64url, 32 bytes) - só no app setting
    VAPID_SUBJECT      contato do remetente (https://... ou mailto:...)

Sem as duas chaves, o push fica desligado e o resto da API segue igual.
"""

import json
import logging
import os
import re
from urllib.parse import urlparse

from pywebpush import WebPushException, webpush

from contrato import PERFIS_CARGA

# Serviços de push dos navegadores. A API só faz POST para esses hosts: uma
# inscrição com outro endereço seria um jeito de fazer a API chamar qualquer URL.
HOSTS_PUSH = (
    "fcm.googleapis.com",                   # Chrome, Edge (Android e desktop)
    "updates.push.services.mozilla.com",    # Firefox
    "push.services.mozilla.com",
    "push.apple.com",                       # Safari, iPhone (web.push.apple.com)
    "notify.windows.com",                   # Edge legado (*.notify.windows.com)
)

ENDPOINT_MAX = 2048
# Inscrições por usuário (celular, computador, outro navegador...). A mais antiga sai.
MAX_POR_USUARIO = 10
BASE64URL = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")

GRAVIDADE = {"NORMAL": 0, "ATENCAO": 1, "CRITICO": 2}

# Leitura medida há mais que isso (fila offline do sensor chegando depois) não
# vira push: o alerta seria velho, e um lote atrasado viraria uma rajada.
IDADE_MAX_S = 30 * 60

# No máximo 1 push por sensor e faixa a cada 10 min: leitura oscilando na borda
# da faixa não vira uma notificação a cada 20 s.
INTERVALO_S = 10 * 60

# Tempo que o serviço de push guarda a mensagem se o celular estiver desligado.
TTL_S = 60 * 60
TIMEOUT_S = 5


def chave_publica():
    return os.getenv("VAPID_PUBLIC_KEY") or None


def configurado():
    return bool(chave_publica() and os.getenv("VAPID_PRIVATE_KEY"))


def _host_permitido(host):
    return any(host == h or host.endswith("." + h) for h in HOSTS_PUSH)


def _chave_b64(valor, minimo, maximo):
    return isinstance(valor, str) and minimo <= len(valor) <= maximo and bool(
        BASE64URL.match(valor))


def validar_endpoint(endpoint):
    """Lista de erros do endereço da inscrição (vazia = válido)."""
    if not isinstance(endpoint, str) or not 1 <= len(endpoint) <= ENDPOINT_MAX:
        return [f"endpoint: texto de até {ENDPOINT_MAX} caracteres"]
    try:
        url = urlparse(endpoint)
        porta = url.port
    except ValueError:  # porta ou endereço malformado
        return ["endpoint: precisa ser https"]
    if url.scheme != "https" or not url.hostname or porta not in (None, 443):
        return ["endpoint: precisa ser https"]
    if not _host_permitido(url.hostname.lower()):
        return ["endpoint: serviço de push não reconhecido"]
    return []


def validar_inscricao(dados):
    """Valida o PushSubscription.toJSON() do navegador.

    Retorna (erros, doc) com doc = {"endpoint", "keys": {"p256dh", "auth"}}.
    `expirationTime` é aceito e ignorado; outros campos também.
    """
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"], None
    erros = validar_endpoint(dados.get("endpoint"))
    chaves = dados.get("keys")
    if not isinstance(chaves, dict):
        erros.append("keys: objeto com p256dh e auth")
    else:
        # p256dh: ponto P-256 de 65 bytes (87 caracteres em base64url);
        # auth: 16 bytes (22 caracteres). Folga para preenchimento com "=".
        if not _chave_b64(chaves.get("p256dh"), 80, 100):
            erros.append("keys.p256dh: chave pública do navegador em base64url")
        if not _chave_b64(chaves.get("auth"), 16, 32):
            erros.append("keys.auth: segredo da inscrição em base64url")
    if erros:
        return erros, None
    return [], {"endpoint": dados["endpoint"],
                "keys": {"p256dh": chaves["p256dh"], "auth": chaves["auth"]}}


def validar_remocao(dados):
    """Corpo do DELETE: {"endpoint": "..."}. Retorna (erros, endpoint)."""
    if not isinstance(dados, dict) or not isinstance(dados.get("endpoint"), str):
        return ["endpoint: obrigatório"], None
    if not 1 <= len(dados["endpoint"]) <= ENDPOINT_MAX:
        return [f"endpoint: texto de até {ENDPOINT_MAX} caracteres"], None
    return [], dados["endpoint"]


def juntar(inscricoes, nova):
    """Lista do usuário com `nova` no fim, sem repetir o endpoint e no máximo MAX_POR_USUARIO."""
    outras = [i for i in (inscricoes or []) if i.get("endpoint") != nova["endpoint"]]
    return (outras + [nova])[-MAX_POR_USUARIO:]


def sem(inscricoes, endpoints):
    """Lista do usuário sem os endpoints dados."""
    return [i for i in (inscricoes or []) if i.get("endpoint") not in endpoints]


def piorou(anterior, atual):
    """True quando a leitura passou para uma faixa pior que a anterior.

    Sem leitura anterior conta como NORMAL: o primeiro dado já fora da faixa avisa.
    """
    return GRAVIDADE.get(atual, 0) > GRAVIDADE.get(anterior or "NORMAL", 0)


NOMES = {"ATENCAO": "Atenção", "CRITICO": "Crítico"}


def mensagem(leitura, veiculo=None, motorista=False):
    """Conteúdo da notificação (o service worker do painel monta o aviso com ele).

    Para o motorista, o toque abre a tela dele (/motorista): o painel de alertas é
    só de operador e gestor.
    """
    status = leitura["status"]
    carga = PERFIS_CARGA.get(leitura["perfil"], {}).get("nome", leitura["perfil"])
    onde = f"Veículo {veiculo}" if veiculo else f"Sensor {leitura['deviceId']}"
    if motorista:
        url, acao = "/motorista", "Toque para ver a carga."
    else:
        url = f"/alertas?veiculo={veiculo}" if veiculo else "/alertas"
        acao = "Toque para ver os alertas."
    return {
        "titulo": f"{NOMES.get(status, status)}: {onde}",
        "corpo": (f"{leitura['temperatura']:.1f} °C, fora da faixa normal da carga "
                  f"({carga}). {acao}"),
        "url": url,
        "tag": f"coldtrack-{leitura['deviceId']}",
        "status": status,
        "deviceId": leitura["deviceId"],
    }


def enviar(inscricao, conteudo):
    """Manda um push. Retorna "ok", "expirada" (404/410: apagar) ou "falha".

    Nunca levanta exceção: falha no envio não pode derrubar quem chamou.
    Nada da inscrição (endereço, chaves) vai para o log.
    """
    try:
        webpush(
            subscription_info={"endpoint": inscricao["endpoint"], "keys": inscricao["keys"]},
            data=json.dumps(conteudo, ensure_ascii=False),
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": os.getenv("VAPID_SUBJECT",
                                           "https://github.com/mbalbuquerque/Front-End-pi")},
            ttl=TTL_S,
            timeout=TIMEOUT_S,
        )
        return "ok"
    except WebPushException as e:
        codigo = getattr(e.response, "status_code", None)
        if codigo in (404, 410):
            return "expirada"
        logging.warning("push: serviço de push recusou (HTTP %s)", codigo)
        return "falha"
    except Exception as e:  # rede, chave mal configurada, inscrição corrompida
        logging.warning("push: falha no envio (%s)", type(e).__name__)
        return "falha"
