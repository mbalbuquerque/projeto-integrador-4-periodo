"""Migração única para o modelo com várias empresas (rodar antes de publicar a API nova).

- Cria a empresa de demonstração e põe nela os usuários, veículos e viagens que já existem.
- Veículos e viagens passam a ter id "<empresa>~<código>".
- Registra um dispositivo para cada sensor usado pela frota (e o coldtrack-01) com chave
  própria. As chaves vão para o arquivo indicado, nunca para a tela.

Uso:
  set COSMOS_CONNECTION=<string de conexão do Cosmos>
  python migrar_multiempresa.py <arquivo-das-chaves>

Pode rodar de novo: o que já foi migrado é pulado.
"""

import os
import sys
from datetime import datetime, timezone

from azure.cosmos import CosmosClient, exceptions

from seguranca import gerar_chave_dispositivo, hash_chave

EMPRESA = {"id": "coldtrack", "nome": "ColdTrack (demonstração)"}
SEP = "~"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    arquivo_chaves = sys.argv[1]
    agora = datetime.now(timezone.utc).isoformat()

    banco = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION"]) \
        .get_database_client(os.getenv("COSMOS_DATABASE", "coldtrack"))
    c = {n: banco.get_container_client(n)
         for n in ("empresas", "usuarios", "veiculos", "viagens", "dispositivos")}

    c["empresas"].upsert_item({**EMPRESA, "criadaEm": agora})
    emp = EMPRESA["id"]

    for u in list(c["usuarios"].read_all_items()):
        if "empresaId" not in u:
            u.update({"empresaId": emp, "sessao": u.get("sessao", 0)})
            c["usuarios"].upsert_item(u)
            print("usuário", u["id"])

    sensores = {"coldtrack-01"}
    for nome in ("veiculos", "viagens"):
        for d in list(c[nome].read_all_items()):
            if SEP in d["id"]:
                sensores.add(d.get("deviceId", "").lower())
                continue
            antigo = d["id"]
            novo = {k: v for k, v in d.items() if not k.startswith("_")}
            novo.update({"id": f"{emp}{SEP}{antigo}", "empresaId": emp})
            if nome == "veiculos":
                novo["deviceId"] = novo["deviceId"].lower()
                sensores.add(novo["deviceId"])
            c[nome].upsert_item(novo)
            c[nome].delete_item(antigo, partition_key=antigo)
            print(nome, antigo, "->", novo["id"])

    linhas = []
    for device in sorted(s for s in sensores if s):
        try:
            c["dispositivos"].read_item(device, partition_key=device)
            continue
        except exceptions.CosmosResourceNotFoundError:
            pass
        chave = gerar_chave_dispositivo()
        c["dispositivos"].create_item({
            "id": device, "empresaId": emp, "descricao": "migrado do piloto",
            "chaveHash": hash_chave(chave), "criadoEm": agora,
        })
        linhas.append(f"{device} {chave}")
        print("dispositivo", device)

    if linhas:
        with open(arquivo_chaves, "a", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
        print(f"{len(linhas)} chave(s) em {arquivo_chaves}")


if __name__ == "__main__":
    main()
