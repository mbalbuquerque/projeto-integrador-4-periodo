"""Carrega dados de exemplo (sintéticos) no emulador do Cosmos DB.

Uso (da raiz do repositório, depois de `python infra/ci/preparar_banco.py`):
    python infra/ci/dados_exemplo.py [endpoint]

Só para o emulador local e o ambiente de teste do CI. Nada aqui é dado real: tudo vem de uma
empresa fictícia ("emp-exemplo") e as leituras levam `origem: "simulador"`, para nunca serem
confundidas com as da placa física (`origem: "placa"`). Rodar de novo não duplica nada: cada
documento tem id determinístico e entra com upsert.
"""
import hashlib
import sys
from datetime import datetime, timedelta, timezone

# Chave pública e documentada do emulador (não é segredo).
CHAVE_EMULADOR = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
EMPRESA = "emp-exemplo"
SEP = "~"  # mesmo separador de id_interno() na API (empresa~codigo)
DISPOSITIVO = "exemplo-sensor-01"
CHAVE_DO_SENSOR = "chave-de-exemplo-nao-usar-em-producao"  # fictícia; só o hash é gravado
VEICULO = "EXE-0001"
INICIO = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
QTD_LEITURAS = 12
INTERVALO_S = 20


def _classificar(temperatura):
    # Perfil "demonstrativo" (contrato.py): ideal até 15 °C, margem de 5 °C.
    return "OK" if temperatura <= 15.0 else ("ALERTA" if temperatura <= 20.0 else "CRITICO")


def documentos():
    """Devolve {container: [documentos]} com o conjunto de exemplo."""
    leituras = []
    for seq in range(1, QTD_LEITURAS + 1):
        medido = INICIO + timedelta(seconds=INTERVALO_S * (seq - 1))
        temperatura = round(8.0 + seq * 1.0, 1)  # sobe de 9 a 20 °C: passa por OK e ALERTA
        leituras.append({
            # mesmo formato da API (id_leitura): dispositivo~epoch. É a chave de idempotência.
            "id": f"{DISPOSITIVO}{SEP}{int(medido.timestamp())}",
            "deviceId": DISPOSITIVO,
            "empresaId": EMPRESA,
            "temperatura": temperatura,
            "umidade": 60.0,
            "rssi": -55,
            "perfil": "demonstrativo",
            "status": _classificar(temperatura),
            "medidoEm": medido.isoformat(),
            "recebidoEm": (medido + timedelta(seconds=1)).isoformat(),
            "seq": seq,
            "origem": "simulador",
        })
    return {
        "empresas": [{"id": EMPRESA, "nome": "Empresa de Exemplo (dados sintéticos)"}],
        "dispositivos": [{
            "id": DISPOSITIVO, "descricao": "Sensor de exemplo", "empresaId": EMPRESA,
            "chaveHash": hashlib.sha256(CHAVE_DO_SENSOR.encode()).hexdigest(),
            "criadoEm": INICIO.isoformat(), "origem": "simulador"}],
        "veiculos": [{
            "id": f"{EMPRESA}{SEP}{VEICULO}", "empresaId": EMPRESA, "tipo": "Caminhão baú",
            "deviceId": DISPOSITIVO, "perfil": "demonstrativo", "origem": "simulador"}],
        "viagens": [{
            "id": f"{EMPRESA}{SEP}viagem-exemplo", "empresaId": EMPRESA, "veiculo": VEICULO,
            "origem": "Petrolina", "destino": "Suape", "carga": "Carga de exemplo",
            "inicio": INICIO.isoformat(), "fim": None}],
        "leituras": leituras,
    }


def carregar(banco):
    """Grava (upsert) os documentos no banco e devolve {container: quantidade}."""
    totais = {}
    for nome, docs in documentos().items():
        container = banco.get_container_client(nome)
        for doc in docs:
            container.upsert_item(doc)
        totais[nome] = len(docs)
    return totais


def verificar(banco):
    """Confere que o exemplo está no banco, sem duplicata; devolve a lista de problemas."""
    problemas = []
    for nome, docs in documentos().items():
        container = banco.get_container_client(nome)
        ids = [d["id"] for d in docs]
        achados = list(container.query_items(
            "SELECT c.id FROM c WHERE ARRAY_CONTAINS(@ids, c.id)",
            parameters=[{"name": "@ids", "value": ids}], enable_cross_partition_query=True))
        if len(achados) != len(ids):
            problemas.append(f"{nome}: esperados {len(ids)}, achados {len(achados)}")
    return problemas


def main(argv):
    from azure.cosmos import CosmosClient

    endpoint = argv[1] if len(argv) > 1 else "http://localhost:8081"
    cliente = CosmosClient(endpoint, credential=CHAVE_EMULADOR)
    banco = cliente.get_database_client("coldtrack")
    print("carregado:", carregar(banco))
    carregar(banco)  # segunda rodada: prova a idempotência
    problemas = verificar(banco)
    if problemas:
        sys.exit("dados de exemplo inconsistentes: " + "; ".join(problemas))
    print("dados de exemplo ok, sem duplicatas")


if __name__ == "__main__":
    main(sys.argv)
