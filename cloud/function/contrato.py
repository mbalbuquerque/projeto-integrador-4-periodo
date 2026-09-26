"""Contrato de telemetria do ColdTrack Edge.

Valida o JSON enviado pelo ESP32 e classifica a leitura. Não depende de Azure,
então pode ser testado localmente com `python -m unittest`.

Payload esperado (POST /api/telemetria):
{
  "deviceId": "coldtrack-01",
  "temperatura": 12.4,
  "umidade": 81.0,
  "rssi": -58,
  "medidoEm": 1790000000      (opcional: epoch UTC em segundos da medição)
}
"""

import os
import re
import time

DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{3,40}$")

# Faixas físicas do sensor (DHT22). Fora disso é leitura inconsistente.
TEMP_MIN, TEMP_MAX = -40.0, 80.0
UMID_MIN, UMID_MAX = 0.0, 100.0
RSSI_MIN, RSSI_MAX = -120, 0

# Janela aceita para o horário da medição.
MEDIDO_FUTURO_MAX_S = 5 * 60
MEDIDO_PASSADO_MAX_S = 7 * 24 * 3600


def _limites():
    # Mesmos limites demonstrativos do firmware; configuráveis por app setting.
    return (
        float(os.getenv("TEMP_NORMAL_MAX", "15")),
        float(os.getenv("TEMP_ATENCAO_MAX", "20")),
    )


def _numero(valor):
    # bool é subclasse de int em Python; não aceitar true/false como número.
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def validar(dados, agora=None):
    """Retorna a lista de erros do payload. Lista vazia = payload válido."""
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"]

    erros = []
    device = dados.get("deviceId")
    if not isinstance(device, str) or not DEVICE_ID.match(device):
        erros.append("deviceId: texto de 3 a 40 caracteres (letras, números, _ ou -)")

    for campo, minimo, maximo in (
        ("temperatura", TEMP_MIN, TEMP_MAX),
        ("umidade", UMID_MIN, UMID_MAX),
        ("rssi", RSSI_MIN, RSSI_MAX),
    ):
        valor = dados.get(campo)
        # RSSI é diagnóstico de rede: o firmware manda null quando o rádio
        # devolve valor impossível (ex.: positivo no simulador). Temperatura e
        # umidade continuam obrigatórias.
        if campo == "rssi" and campo in dados and valor is None:
            continue
        if not _numero(valor):
            erros.append(f"{campo}: obrigatório e numérico")
        elif valor != valor or not minimo <= valor <= maximo:  # valor != valor pega NaN
            erros.append(f"{campo}: fora da faixa [{minimo}, {maximo}]")

    # medidoEm: horário da medição (epoch UTC em segundos), opcional.
    # Leituras guardadas offline no ESP32 chegam depois, então o horário de
    # recebimento não serve para a linha do tempo da carga.
    if "medidoEm" in dados:
        medido = dados["medidoEm"]
        referencia = time.time() if agora is None else agora
        if not _numero(medido) or medido != medido:
            erros.append("medidoEm: epoch em segundos (número)")
        elif medido > referencia + MEDIDO_FUTURO_MAX_S:
            erros.append("medidoEm: no futuro (relógio do dispositivo errado?)")
        elif medido < referencia - MEDIDO_PASSADO_MAX_S:
            erros.append("medidoEm: mais antigo que 7 dias")

    extras = set(dados) - {"deviceId", "temperatura", "umidade", "rssi", "medidoEm"}
    if extras:
        erros.append("campos não previstos: " + ", ".join(sorted(extras)))

    return erros


def classificar(temperatura):
    normal_max, atencao_max = _limites()
    if temperatura <= normal_max:
        return "NORMAL"
    if temperatura <= atencao_max:
        return "ATENCAO"
    return "CRITICO"
