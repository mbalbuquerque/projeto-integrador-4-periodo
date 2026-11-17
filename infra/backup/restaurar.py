"""Restaura um export JSONL (ver exportar.py) em um Cosmos DB de DESTINO.

Uso:
    export DEST_ENDPOINT=http://localhost:8081   # ou DEST_CONNECTION
    export DEST_KEY=<chave do destino>
    python infra/backup/restaurar.py <pasta-do-export> [--banco coldtrack-restaurado]

Recusa qualquer conta hospedada na Azure (*.documents.azure.com), em especial a de
producao: o destino e o emulador ou uma conta de teste criada fora deste repositorio.
Cria o banco e os containers (com a chave de particao e o TTL do manifesto) se faltarem
e grava com upsert, entao pode rodar de novo. Confere a contagem no fim e sai com 1 se
divergir.
"""
import argparse
import json
import os
import sys

from azure.cosmos import PartitionKey

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backup_cosmos as bc  # noqa: E402


def contar(container):
    return list(container.query_items("SELECT VALUE COUNT(1) FROM c",
                                      enable_cross_partition_query=True))[0]


def restaurar(cliente, pasta, nome_banco=None):
    """Restaura `pasta` em `cliente`; devolve {container: (esperado, restaurado)}."""
    with open(os.path.join(pasta, "manifesto.json"), encoding="utf-8") as f:
        manifesto = json.load(f)
    banco = cliente.create_database_if_not_exists(nome_banco or manifesto["banco"])
    resultado = {}
    for nome, meta in manifesto["containers"].items():
        container = banco.create_container_if_not_exists(
            nome, partition_key=PartitionKey(path=meta["chaveParticao"]),
            default_ttl=meta.get("ttl"))
        for doc in bc.ler_jsonl(os.path.join(pasta, meta["arquivo"])):
            container.upsert_item(doc)
        resultado[nome] = (meta["contagem"], contar(container))
    return resultado


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("pasta", help="pasta do export")
    p.add_argument("--banco", help="nome do banco no destino (padrao: o do manifesto)")
    args = p.parse_args(argv)
    cliente, _ = bc.cliente_de_ambiente("DEST", recusar_producao=True)
    resultado = restaurar(cliente, args.pasta, args.banco)
    ok = True
    for nome, (esperado, obtido) in resultado.items():
        ok &= esperado == obtido
        print(f"{nome}: esperado {esperado}, restaurado {obtido} "
              f"[{'ok' if esperado == obtido else 'DIVERGE'}]")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
