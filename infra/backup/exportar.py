"""Exporta todos os containers de um banco do Cosmos DB para JSONL (backup logico).

Uso:
    export COSMOS_ENDPOINT=https://<conta>.documents.azure.com:443/
    export COSMOS_KEY=<chave SOMENTE LEITURA>
    python infra/backup/exportar.py <pasta-de-saida> [--banco coldtrack] [--excluir limites]

A chave somente leitura sai de:
    az cosmosdb keys list -g rg-coldtrack -n cosmos-coldtrack-7319 --type read-only-keys \
        --query primaryReadonlyMasterKey -o tsv

A saida tem dado real (e-mail, hash de senha, leituras): grave FORA do repositorio.
Esta ferramenta so le; nao altera nada no banco de origem.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backup_cosmos as bc  # noqa: E402


def exportar(banco, saida, excluir=()):
    """Exporta cada container de `banco` para `saida`/<container>.jsonl e grava o manifesto."""
    os.makedirs(saida, exist_ok=True)
    manifesto = {"versao": bc.VERSAO, "banco": banco.id, "data": bc.agora(), "containers": {}}
    inicio = time.monotonic()
    for props in banco.list_containers():
        nome = props["id"]
        if nome in excluir:
            continue
        container = banco.get_container_client(nome)
        arquivo = f"{nome}.jsonl"
        total = bc.escrever_jsonl(os.path.join(saida, arquivo), container.read_all_items())
        manifesto["containers"][nome] = {
            "arquivo": arquivo,
            "contagem": total,
            "chaveParticao": props["partitionKey"]["paths"][0],
            "ttl": props.get("defaultTtl"),
        }
    manifesto["duracaoSegundos"] = round(time.monotonic() - inicio, 2)
    with open(os.path.join(saida, "manifesto.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifesto, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return manifesto


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("saida", help="pasta de saida (fora do repositorio)")
    p.add_argument("--banco", default=os.environ.get("COSMOS_DATABASE", "coldtrack"))
    p.add_argument("--excluir", nargs="*", default=[], help="containers a pular")
    args = p.parse_args(argv)
    cliente, _ = bc.cliente_de_ambiente("COSMOS")
    manifesto = exportar(cliente.get_database_client(args.banco), args.saida, args.excluir)
    for nome, c in manifesto["containers"].items():
        print(f"{nome}: {c['contagem']} documentos")
    print(f"export em {args.saida} ({manifesto['duracaoSegundos']} s)")


if __name__ == "__main__":
    main()
