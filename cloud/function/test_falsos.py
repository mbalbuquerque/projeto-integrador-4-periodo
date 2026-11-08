"""Falsos do Cosmos usados pelos testes da API (sem rede)."""

import re

from azure.cosmos import exceptions


class ContainerFalso:
    """Imita o ContainerProxy do Cosmos para as consultas que a function_app usa.

    Só filtra por empresa quando a consulta pede (@e ou @empresa): consulta sem
    filtro devolveria dados das duas empresas, e o teste pegaria o vazamento.
    """

    def __init__(self, itens):
        self.itens = [dict(i) for i in itens]
        self.consultas = []
        self.escritas = []
        # Chamada antes de cada patch: simula outra escrita concorrente no meio.
        self.antes_do_patch = None

    def read_item(self, item, partition_key):
        for i in self.itens:
            if i["id"] == item:
                return dict(i)
        raise exceptions.CosmosResourceNotFoundError(status_code=404, message="não achou")

    def query_items(self, query, parameters=(), partition_key=None, **_):
        self.consultas.append(query)
        p = {x["name"]: x["value"] for x in parameters}
        itens = list(self.itens)
        if partition_key is not None:
            itens = [i for i in itens if i.get("deviceId") == partition_key]
        for nome in ("@e", "@empresa"):
            if nome in p:
                itens = [i for i in itens if i.get("empresaId") == p[nome]]
        for nome in ("@d", "@device"):
            if nome in p:
                itens = [i for i in itens if i.get("deviceId") == p[nome]]
        if "@desde" in p:
            itens = [i for i in itens if i["medidoEm"] >= p["@desde"]]
        if "ORDER BY c.medidoEm DESC" in query:
            itens.sort(key=lambda i: i["medidoEm"], reverse=True)
        if "@limite" in p:
            itens = itens[:p["@limite"]]
        campos = re.match(r"SELECT (?:TOP @limite )?(.+?) FROM", query).group(1)
        if campos != "*" and not campos.startswith("VALUE"):
            nomes = [c.strip()[2:] for c in campos.split(",")]
            itens = [{k: i[k] for k in nomes if k in i} for i in itens]
        return iter(itens)

    # ---- escrita (login, senha, sair, limites)

    def read(self):
        """Metadados do container: o falso sempre existe."""
        return {"id": "falso"}

    def _achar(self, item_id):
        for i in self.itens:
            if i["id"] == item_id:
                return i
        raise exceptions.CosmosResourceNotFoundError(status_code=404, message="não achou")

    def create_item(self, body, **_):
        if any(i["id"] == body["id"] for i in self.itens):
            raise exceptions.CosmosResourceExistsError(status_code=409, message="já existe")
        self.itens.append(dict(body))
        return dict(body)

    def upsert_item(self, body, **_):
        self.escritas.append(("upsert", body["id"], None))
        self.itens = [i for i in self.itens if i["id"] != body["id"]] + [dict(body)]
        return dict(body)

    def delete_item(self, item, partition_key, **_):
        self._achar(item)
        self.itens = [i for i in self.itens if i["id"] != item]

    def patch_item(self, item, partition_key, patch_operations, **_):
        """Aplica set/replace/incr/remove só nos campos pedidos, como o Cosmos."""
        self.escritas.append(("patch", item, [dict(o) for o in patch_operations]))
        if self.antes_do_patch:
            self.antes_do_patch(item)
        doc = self._achar(item)
        for op in patch_operations:
            campo = op["path"].lstrip("/")
            if op["op"] in ("set", "replace", "add"):
                doc[campo] = op["value"]
            elif op["op"] == "incr":
                doc[campo] = doc.get(campo, 0) + op["value"]
            elif op["op"] == "remove":
                doc.pop(campo, None)
            else:
                raise ValueError(op["op"])
        return dict(doc)
