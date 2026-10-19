"""Cria um usuário do painel direto no Cosmos DB (uso local, para suporte).

O caminho normal é o painel: a empresa se cadastra em cadastro.html e o gestor
cria os demais usuários em Configurações.

Uso:
  set COSMOS_CONNECTION=<string de conexão do Cosmos>
  python criar_usuario.py <email> "<nome>" <operador|gestor> <id da empresa>
  (a senha é pedida no terminal, sem aparecer na tela)
"""

import getpass
import os
import sys

from azure.cosmos import CosmosClient, exceptions

from cadastros import validar_usuario
from seguranca import gerar_hash


def main():
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    email, nome, perfil, empresa = sys.argv[1:]
    senha = os.environ.get("COLDTRACK_SENHA") or getpass.getpass("Senha (mín. 8): ")

    erros, doc = validar_usuario({"email": email, "nome": nome, "perfil": perfil, "senha": senha})
    if erros:
        sys.exit("\n".join(erros))
    doc.update({"empresaId": empresa, "sessao": 0, "senhaHash": gerar_hash(doc.pop("senha"))})

    banco = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION"]) \
        .get_database_client(os.getenv("COSMOS_DATABASE", "coldtrack"))
    try:
        banco.get_container_client("usuarios").create_item(doc)
    except exceptions.CosmosResourceExistsError:
        sys.exit(f"Já existe usuário {doc['id']}.")
    print(f"Usuário {doc['id']} criado ({doc['perfil']}).")


if __name__ == "__main__":
    main()
