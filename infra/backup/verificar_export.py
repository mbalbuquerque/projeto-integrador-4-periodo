"""Confere um export do backup lógico e ensaia a restauração em memória (sem rede).

Uso:
    python infra/backup/verificar_export.py <pasta-do-export>

Faz, com o export REAL e sem abrir conexão com nenhum Cosmos:
  1. confere o manifesto com os arquivos (contagem de linhas de cada container);
  2. lê cada documento (JSON válido, com `id` e com a chave de partição do container) e
     procura `id` repetido dentro da mesma partição;
  3. roda `restaurar.restaurar` contra um Cosmos falso em memória e compara, container a
     container, o esperado com o restaurado, e roda de novo para provar a idempotência.

Isto NÃO substitui a restauração num Cosmos de verdade (emulador ou conta de teste): prova
que o arquivo está íntegro e que a lógica de restauração o aceita por inteiro, mas não prova
que o serviço aceita os documentos. Só lê o export; nada é gravado.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backup_cosmos as bc  # noqa: E402
import restaurar  # noqa: E402


class _Container:
    """Falso em memória: um documento por (partição, id), como o Cosmos."""

    def __init__(self, caminho):
        self.caminho = caminho
        self.docs = {}

    def upsert_item(self, doc):
        self.docs[(str(_valor(doc, self.caminho)), str(doc["id"]))] = doc

    def query_items(self, *_, **__):
        return iter([len(self.docs)])


class _Banco:
    def __init__(self):
        self.containers = {}

    def create_container_if_not_exists(self, nome, partition_key, default_ttl=None):
        return self.containers.setdefault(nome, _Container(partition_key.path))


class _Cliente:
    def __init__(self):
        self.banco = _Banco()

    def create_database_if_not_exists(self, nome):
        return self.banco

def _valor(doc, caminho):
    atual = doc
    for parte in caminho.strip("/").split("/"):
        if not isinstance(atual, dict) or parte not in atual:
            return None
        atual = atual[parte]
    return atual


def verificar(pasta):
    """Devolve (linhas do relatório, ok). `ok` é False se algo estiver inconsistente."""
    with open(os.path.join(pasta, "manifesto.json"), encoding="utf-8") as f:
        manifesto = json.load(f)
    ok = True
    saida = [f"export de {manifesto['data']} do banco `{manifesto['banco']}`"]
    for nome, meta in manifesto["containers"].items():
        total, sem_chave, repetidos, vistos = 0, 0, 0, set()
        for doc in bc.ler_jsonl(os.path.join(pasta, meta["arquivo"])):
            total += 1
            chave = _valor(doc, meta["chaveParticao"])
            if "id" not in doc or chave is None:
                sem_chave += 1
                continue
            par = (str(chave), str(doc["id"]))
            if par in vistos:
                repetidos += 1
            vistos.add(par)
        bom = total == meta["contagem"] and not sem_chave and not repetidos
        ok &= bom
        saida.append(f"  {nome}: manifesto {meta['contagem']}, arquivo {total}, sem id ou "
                     f"chave de partição {sem_chave}, id repetido {repetidos} "
                     f"[{'ok' if bom else 'DIVERGE'}]")
    # Ensaio da restauração, duas vezes (a segunda prova a idempotência).
    cliente = _Cliente()
    for rodada in (1, 2):
        inicio = time.monotonic()
        resultado = restaurar.restaurar(cliente, pasta, "verificacao")
        duracao = time.monotonic() - inicio
        certo = all(e == o for e, o in resultado.values())
        ok &= certo
        saida.append(f"  restauração em memória, rodada {rodada}: "
                     + ", ".join(f"{n} {o}/{e}" for n, (e, o) in resultado.items())
                     + f" ({duracao:.2f} s) [{'ok' if certo else 'DIVERGE'}]")
    return saida, ok


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit(__doc__.split("\n")[0])
    linhas, ok = verificar(argv[0])
    print("\n".join(linhas))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
