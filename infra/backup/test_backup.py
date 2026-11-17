"""Testes do backup logico.

Os testes com `Falso*` rodam em qualquer maquina. Os de integracao (marcados `emulador`)
precisam de um Cosmos de teste em TESTE_COSMOS_ENDPOINT e TESTE_COSMOS_KEY (o job
`Backup logico` do CI sobe o emulador oficial) e sao pulados sem elas.

    pip install azure-cosmos==4.17.1 pytest
    python -m pytest infra/backup -v
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import backup_cosmos as bc  # noqa: E402
import exportar  # noqa: E402
import restaurar  # noqa: E402

CONTAINERS = {"empresas": "/id", "usuarios": "/id", "leituras": "/deviceId", "limites": "/id"}


# ------------------------------------------------------------------ dubles em memoria

class FalsoContainer:
    def __init__(self, docs=()):
        self.docs = {d["id"]: dict(d) for d in docs}

    def read_all_items(self):
        return iter(self.docs.values())

    def upsert_item(self, doc):
        self.docs[doc["id"]] = dict(doc)

    def query_items(self, *_, **__):
        return iter([len(self.docs)])


class FalsoBanco:
    def __init__(self, id_, containers=None):
        self.id = id_
        self.props = {}
        self.containers = {}
        for nome, (pk, docs) in (containers or {}).items():
            self.props[nome] = {"id": nome, "partitionKey": {"paths": [pk]}}
            self.containers[nome] = FalsoContainer(docs)

    def list_containers(self):
        return list(self.props.values())

    def get_container_client(self, nome):
        return self.containers[nome]

    def create_container_if_not_exists(self, nome, partition_key, default_ttl=None):
        if nome not in self.containers:
            self.props[nome] = {"id": nome, "partitionKey": {"paths": [partition_key.path]}}
            if default_ttl is not None:
                self.props[nome]["defaultTtl"] = default_ttl
            self.containers[nome] = FalsoContainer()
        return self.containers[nome]


class FalsoCliente:
    def __init__(self):
        self.bancos = {}

    def get_database_client(self, nome):
        return self.bancos[nome]

    def create_database_if_not_exists(self, nome):
        return self.bancos.setdefault(nome, FalsoBanco(nome))


def origem():
    return FalsoBanco("coldtrack", {
        "empresas": ("/id", [{"id": "e1", "nome": "Acme", "_etag": "x", "_ts": 1}]),
        "usuarios": ("/id", [{"id": "a@x.com", "senhaHash": "h", "_rid": "r"},
                             {"id": "b@x.com", "senhaHash": "h2"}]),
        "leituras": ("/deviceId", [{"id": "l1", "deviceId": "d1", "temperatura": -18.5,
                                    "obs": "açaí ❄"}]),
        "limites": ("/id", []),
    })


# ------------------------------------------------------------------ funcoes puras

def test_limpar_remove_so_propriedades_de_sistema():
    doc = {"id": "1", "_etag": "e", "_ts": 5, "_rid": "r", "_self": "s", "_attachments": "a",
           "_lsn": 1, "campo": 2}
    assert bc.limpar(doc) == {"id": "1", "campo": 2}


@pytest.mark.parametrize("endpoint,esperado", [
    ("https://cosmos-coldtrack-7319.documents.azure.com:443/", True),
    ("https://OUTRA.DOCUMENTS.AZURE.COM/", True),
    ("http://localhost:8081", False),
    ("http://cosmos:8081/", False),
    ("https://evil.example.com/documents.azure.com", False),
])
def test_e_producao(endpoint, esperado):
    assert bc.e_producao(endpoint) is esperado


def test_endpoint_da_conexao():
    assert bc.endpoint_da_conexao("AccountEndpoint=http://cosmos:8081/;AccountKey=abc;") \
        == "http://cosmos:8081/"
    with pytest.raises(SystemExit):
        bc.endpoint_da_conexao("AccountKey=abc;")


def test_jsonl_ida_e_volta_com_acentos(tmp_path):
    caminho = tmp_path / "x.jsonl"
    docs = [{"id": "1", "t": "açaí"}, {"id": "2", "_etag": "e"}]
    assert bc.escrever_jsonl(caminho, docs) == 2
    assert b"\r" not in caminho.read_bytes()
    assert list(bc.ler_jsonl(caminho)) == [{"id": "1", "t": "açaí"}, {"id": "2"}]


def test_ambiente_sem_credencial_aborta(monkeypatch):
    for v in ("X_CONNECTION", "X_ENDPOINT", "X_KEY"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(SystemExit, match="Defina"):
        bc.cliente_de_ambiente("X")
    monkeypatch.setenv("X_ENDPOINT", "http://localhost:8081")
    with pytest.raises(SystemExit, match="Defina"):  # falta a chave
        bc.cliente_de_ambiente("X")


@pytest.mark.parametrize("variaveis", [
    {"DEST_ENDPOINT": "https://cosmos-coldtrack-7319.documents.azure.com:443/",
     "DEST_KEY": "k"},
    {"DEST_CONNECTION": "AccountEndpoint=https://cosmos-coldtrack-7319.documents.azure.com:443/;"
                        "AccountKey=k;"},
])
def test_restaurar_recusa_producao_sem_abrir_conexao(monkeypatch, variaveis):
    for v in ("DEST_CONNECTION", "DEST_ENDPOINT", "DEST_KEY"):
        monkeypatch.delenv(v, raising=False)
    for k, v in variaveis.items():
        monkeypatch.setenv(k, v)

    def nao_deve_conectar(*_, **__):
        raise AssertionError("abriu conexao com producao")
    monkeypatch.setattr(bc, "CosmosClient", nao_deve_conectar)
    with pytest.raises(SystemExit, match="Recusado"):
        restaurar.main(["qualquer"])


def test_cliente_de_ambiente_usa_endpoint_e_chave(monkeypatch):
    chamadas = []

    class Cli:
        def __init__(self, endpoint, credential):
            chamadas.append((endpoint, credential))
    monkeypatch.setattr(bc, "CosmosClient", Cli)
    monkeypatch.delenv("COSMOS_CONNECTION", raising=False)
    monkeypatch.setenv("COSMOS_ENDPOINT", "http://localhost:8081")
    monkeypatch.setenv("COSMOS_KEY", "k")
    _, endpoint = bc.cliente_de_ambiente("COSMOS")
    assert endpoint == "http://localhost:8081" and chamadas == [("http://localhost:8081", "k")]


# ------------------------------------------------------------------ exportar e restaurar

def test_exportar_grava_jsonl_e_manifesto(tmp_path):
    manifesto = exportar.exportar(origem(), tmp_path, excluir=("limites",))
    assert set(manifesto["containers"]) == {"empresas", "usuarios", "leituras"}
    assert manifesto["containers"]["usuarios"]["contagem"] == 2
    assert manifesto["containers"]["leituras"]["chaveParticao"] == "/deviceId"
    grav = json.loads((tmp_path / "manifesto.json").read_text(encoding="utf-8"))
    assert grav["banco"] == "coldtrack" and grav["data"] and grav["versao"] == bc.VERSAO
    linhas = (tmp_path / "usuarios.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2 and "_rid" not in linhas[0]
    assert not (tmp_path / "limites.jsonl").exists()


def test_exportar_inclui_container_vazio_e_ttl(tmp_path):
    src = origem()
    src.props["limites"]["defaultTtl"] = 172800
    m = exportar.exportar(src, tmp_path)
    assert m["containers"]["limites"]["contagem"] == 0
    assert m["containers"]["limites"]["ttl"] == 172800


def test_restaurar_recria_containers_e_documentos(tmp_path):
    src = origem()
    src.props["limites"]["defaultTtl"] = 172800
    exportar.exportar(src, tmp_path)
    destino = FalsoCliente()
    resultado = restaurar.restaurar(destino, tmp_path, "restaurado")
    assert resultado == {"empresas": (1, 1), "usuarios": (2, 2), "leituras": (1, 1),
                         "limites": (0, 0)}
    banco = destino.bancos["restaurado"]
    assert banco.props["leituras"]["partitionKey"]["paths"] == ["/deviceId"]
    assert banco.props["limites"]["defaultTtl"] == 172800
    assert banco.containers["leituras"].docs["l1"]["obs"] == "açaí ❄"


def test_restaurar_e_idempotente_e_detecta_divergencia(tmp_path):
    exportar.exportar(origem(), tmp_path)
    destino = FalsoCliente()
    restaurar.restaurar(destino, tmp_path)
    assert restaurar.restaurar(destino, tmp_path)["usuarios"] == (2, 2)
    # apaga uma linha do arquivo: o manifesto promete 2 e o arquivo traz 1
    f = tmp_path / "usuarios.jsonl"
    f.write_text(f.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    novo = FalsoCliente()
    assert restaurar.restaurar(novo, tmp_path)["usuarios"] == (2, 1)


def test_main_do_restaurar_sai_com_1_quando_diverge(tmp_path, monkeypatch, capsys):
    exportar.exportar(origem(), tmp_path)
    f = tmp_path / "empresas.jsonl"
    f.write_text("", encoding="utf-8")
    monkeypatch.setattr(bc, "cliente_de_ambiente", lambda *a, **k: (FalsoCliente(), "x"))
    with pytest.raises(SystemExit) as erro:
        restaurar.main([str(tmp_path)])
    assert erro.value.code == 1 and "DIVERGE" in capsys.readouterr().out


def test_main_do_exportar_e_do_restaurar_ok(tmp_path, monkeypatch, capsys):
    cli = FalsoCliente()
    cli.bancos["coldtrack"] = origem()
    monkeypatch.setattr(bc, "cliente_de_ambiente", lambda *a, **k: (cli, "x"))
    exportar.main([str(tmp_path / "e"), "--banco", "coldtrack"])
    assert "usuarios: 2 documentos" in capsys.readouterr().out
    with pytest.raises(SystemExit) as erro:
        restaurar.main([str(tmp_path / "e"), "--banco", "copia"])
    assert erro.value.code == 0


# ------------------------------------------------------------------ integracao (emulador)

emulador = pytest.mark.skipif(
    not (os.environ.get("TESTE_COSMOS_ENDPOINT") and os.environ.get("TESTE_COSMOS_KEY")),
    reason="sem TESTE_COSMOS_ENDPOINT/TESTE_COSMOS_KEY")


@emulador
def test_ida_e_volta_no_emulador(tmp_path):
    from azure.cosmos import CosmosClient, PartitionKey

    endpoint = os.environ["TESTE_COSMOS_ENDPOINT"]
    assert not bc.e_producao(endpoint)
    cli = CosmosClient(endpoint, credential=os.environ["TESTE_COSMOS_KEY"])
    for nome in ("bkp-origem", "bkp-destino"):
        if nome in [d["id"] for d in cli.list_databases()]:
            cli.delete_database(nome)

    # origem sintetica: os mesmos containers e chaves de particao do banco real
    src = cli.create_database_if_not_exists("bkp-origem")
    esperado = {}
    for nome, pk in CONTAINERS.items():
        c = src.create_container_if_not_exists(
            nome, partition_key=PartitionKey(path=pk),
            default_ttl=172800 if nome == "limites" else None)
        docs = []
        for i in range(25 if nome == "leituras" else 3):
            doc = {"id": f"{nome}-{i}", "deviceId": f"dev-{i % 2}", "n": i,
                   "texto": f"açaí {i}", "aninhado": {"a": [1, 2, {"b": None}]}}
            c.upsert_item(doc)
            docs.append(doc)
        esperado[nome] = docs

    manifesto = exportar.exportar(src, tmp_path / "export")
    assert {n: c["contagem"] for n, c in manifesto["containers"].items()} \
        == {n: len(d) for n, d in esperado.items()}

    resultado = restaurar.restaurar(cli, tmp_path / "export", "bkp-destino")
    destino = cli.get_database_client("bkp-destino")
    for nome, docs in esperado.items():
        assert resultado[nome] == (len(docs), len(docs))
        c = destino.get_container_client(nome)
        pk = CONTAINERS[nome].lstrip("/")
        amostra = docs[1]
        lido = c.read_item(amostra["id"], partition_key=amostra[pk])
        assert bc.limpar(lido) == amostra
        assert c.read()["partitionKey"]["paths"] == [CONTAINERS[nome]]
    assert destino.get_container_client("limites").read()["defaultTtl"] == 172800

    cli.delete_database("bkp-origem")
    cli.delete_database("bkp-destino")
