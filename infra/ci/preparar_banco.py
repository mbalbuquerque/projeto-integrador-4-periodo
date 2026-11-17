"""Cria o banco, os containers e os dados de teste no emulador do Cosmos DB.

Uso (da raiz do repositório, com `pip install azure-cosmos`):
    python infra/ci/preparar_banco.py [endpoint]

Só para o emulador local e o ambiente de teste do CI: usa a chave pública do emulador,
a senha abaixo é fictícia e nada aqui vale para produção.
"""
import sys
import time
from pathlib import Path

from azure.cosmos import CosmosClient, PartitionKey

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud" / "function"))
from seguranca import gerar_hash  # noqa: E402

ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8081"
# Chave pública e documentada do emulador (não é segredo).
CHAVE = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
CONTAINERS = {"empresas": "/id", "usuarios": "/id", "veiculos": "/id", "dispositivos": "/id",
              "viagens": "/id", "leituras": "/deviceId", "limites": "/id"}
EMAIL, SENHA = "gestor.teste@exemplo.com", "SenhaDeTeste-123"

cliente = None
for tentativa in range(60):
    try:
        cliente = CosmosClient(ENDPOINT, credential=CHAVE)
        cliente.create_database_if_not_exists("coldtrack")
        break
    except Exception as erro:  # emulador ainda subindo
        print(f"emulador não respondeu ({tentativa + 1}/60): {type(erro).__name__}: {str(erro)[:200]}")
        time.sleep(5)
else:
    sys.exit("emulador do Cosmos não ficou pronto")

banco = cliente.get_database_client("coldtrack")
for nome, chave in CONTAINERS.items():
    banco.create_container_if_not_exists(nome, partition_key=PartitionKey(path=chave))
banco.get_container_client("empresas").upsert_item({"id": "emp-teste", "nome": "Empresa de Teste"})
banco.get_container_client("usuarios").upsert_item({
    "id": EMAIL, "nome": "Gestor de Teste", "perfil": "gestor",
    "empresaId": "emp-teste", "senhaHash": gerar_hash(SENHA)})
print("banco, containers e usuário de teste prontos")
