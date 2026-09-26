"""Azure Function do ColdTrack Edge.

POST /api/telemetria  -> recebe a leitura do ESP32, valida, classifica e grava no Cosmos DB.
GET  /api/leituras    -> devolve as últimas leituras de um dispositivo (consumo do front).

As duas rotas exigem a chave da função (header `x-functions-key`).
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import azure.functions as func
from azure.cosmos import CosmosClient

from contrato import classificar, validar

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

_container = None


def container():
    global _container
    if _container is None:
        cliente = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION"])
        _container = cliente.get_database_client(
            os.getenv("COSMOS_DATABASE", "coldtrack")
        ).get_container_client(os.getenv("COSMOS_CONTAINER", "leituras"))
    return _container


def resposta(corpo, status=200):
    return func.HttpResponse(
        json.dumps(corpo, ensure_ascii=False),
        status_code=status,
        mimetype="application/json",
    )


@app.route(route="telemetria", methods=["POST"])
def telemetria(req: func.HttpRequest) -> func.HttpResponse:
    try:
        dados = req.get_json()
    except ValueError:
        return resposta({"erros": ["corpo não é JSON válido"]}, 400)

    erros = validar(dados)
    if erros:
        logging.warning("telemetria rejeitada: %s", erros)
        return resposta({"erros": erros}, 400)

    leitura = {
        "id": str(uuid.uuid4()),
        "deviceId": dados["deviceId"],
        "temperatura": float(dados["temperatura"]),
        "umidade": float(dados["umidade"]),
        "rssi": None if dados["rssi"] is None else int(dados["rssi"]),
        "status": classificar(dados["temperatura"]),
        "recebidoEm": datetime.now(timezone.utc).isoformat(),
    }
    container().create_item(leitura)
    return resposta({"id": leitura["id"], "status": leitura["status"]}, 201)


@app.route(route="leituras", methods=["GET"])
def leituras(req: func.HttpRequest) -> func.HttpResponse:
    device = req.params.get("deviceId")
    if not device:
        return resposta({"erros": ["informe ?deviceId="]}, 400)
    try:
        limite = max(1, min(int(req.params.get("limite", "50")), 500))
    except ValueError:
        return resposta({"erros": ["limite deve ser inteiro"]}, 400)

    itens = list(
        container().query_items(
            query=(
                "SELECT TOP @limite c.deviceId, c.temperatura, c.umidade, c.rssi, "
                "c.status, c.recebidoEm FROM c WHERE c.deviceId = @device "
                "ORDER BY c.recebidoEm DESC"
            ),
            parameters=[
                {"name": "@limite", "value": limite},
                {"name": "@device", "value": device},
            ],
            partition_key=device,
        )
    )
    return resposta({"deviceId": device, "leituras": itens})
