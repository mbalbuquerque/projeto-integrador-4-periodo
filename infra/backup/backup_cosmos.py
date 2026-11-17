"""Funcoes comuns do backup logico do Cosmos DB (exportar e restaurar).

O export e um diretorio com um arquivo JSONL por container (um documento por linha) e um
`manifesto.json` com data, banco, chave de particao e contagem de cada container.
"""
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from azure.cosmos import CosmosClient

# Propriedades que o proprio Cosmos grava e recalcula; nao fazem parte do dado.
PROPRIEDADES_DE_SISTEMA = ("_rid", "_self", "_etag", "_attachments", "_ts", "_lsn")
VERSAO = 1


def limpar(doc):
    """Remove as propriedades de sistema do Cosmos de um documento."""
    return {k: v for k, v in doc.items() if k not in PROPRIEDADES_DE_SISTEMA}


def endpoint_da_conexao(conexao):
    achado = re.search(r"AccountEndpoint=([^;]+)", conexao)
    if not achado:
        raise SystemExit("String de conexao sem AccountEndpoint.")
    return achado.group(1)


def cliente_de_ambiente(prefixo="COSMOS", recusar_producao=False):
    """Cria o cliente a partir de `<P>_CONNECTION` ou de `<P>_ENDPOINT` + `<P>_KEY`.

    Com `recusar_producao`, aborta ANTES de abrir qualquer conexao se o endpoint for de uma
    conta Azure. Devolve (cliente, endpoint).
    """
    conexao = os.environ.get(f"{prefixo}_CONNECTION")
    chave = os.environ.get(f"{prefixo}_KEY")
    endpoint = endpoint_da_conexao(conexao) if conexao else os.environ.get(f"{prefixo}_ENDPOINT")
    if not endpoint or not (conexao or chave):
        raise SystemExit(f"Defina {prefixo}_CONNECTION ou {prefixo}_ENDPOINT e {prefixo}_KEY.")
    if recusar_producao and e_producao(endpoint):
        raise SystemExit(f"Recusado: {host(endpoint)} e uma conta Azure. "
                         "Restaure so no emulador ou em conta de teste.")
    if conexao:
        return CosmosClient.from_connection_string(conexao), endpoint
    return CosmosClient(endpoint, credential=chave), endpoint


def host(endpoint):
    return (urlparse(endpoint).hostname or "").lower()


def e_producao(endpoint):
    """True para qualquer conta hospedada na Azure (*.documents.azure.com)."""
    return host(endpoint).endswith("documents.azure.com")


def escrever_jsonl(caminho, docs):
    """Grava os documentos em JSONL (UTF-8, LF) e devolve a quantidade."""
    total = 0
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        for doc in docs:
            f.write(json.dumps(limpar(doc), ensure_ascii=False, separators=(",", ":")) + "\n")
            total += 1
    return total


def ler_jsonl(caminho):
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                yield json.loads(linha)


def agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
