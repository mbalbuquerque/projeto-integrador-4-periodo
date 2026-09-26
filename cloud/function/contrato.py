"""Contrato de telemetria do ColdTrack Edge.

Valida o JSON enviado pelo ESP32 e classifica a leitura. Não depende de Azure,
então pode ser testado localmente com `python -m unittest`.

Payload esperado (POST /api/telemetria):
{
  "deviceId": "coldtrack-01",
  "temperatura": 12.4,
  "umidade": 81.0,
  "rssi": -58
}
"""

import os
import re

DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{3,40}$")

# Faixas físicas do sensor (DHT22). Fora disso é leitura inconsistente.
TEMP_MIN, TEMP_MAX = -40.0, 80.0
UMID_MIN, UMID_MAX = 0.0, 100.0
RSSI_MIN, RSSI_MAX = -120, 0


def _limites():
    # Mesmos limites demonstrativos do firmware; configuráveis por app setting.
    return (
        float(os.getenv("TEMP_NORMAL_MAX", "15")),
        float(os.getenv("TEMP_ATENCAO_MAX", "20")),
    )


def _numero(valor):
    # bool é subclasse de int em Python; não aceitar true/false como número.
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def validar(dados):
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

    extras = set(dados) - {"deviceId", "temperatura", "umidade", "rssi"}
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
