#!/usr/bin/env python3
"""Testes de IDOR (verificação de dono) — roda com: python -m unittest seguranca.testes.test_idor"""

import os
import sys
import unittest
from unittest import mock

# Adiciona o diretório cloud/function ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud', 'function'))

import function_app as function_app_mod


# Use the same ContainerFalso as test_falsos.py (which properly filters by empresaId in query_items)
class ContainerFalso:
    """Container Cosmos DB falso para testes (igual ao de test_falsos.py)."""

    def __init__(self, itens):
        self.itens = [dict(i) for i in itens]
        self.consultas = []
        self.escritas = []
        self.antes_do_patch = None

    def read_item(self, item, partition_key):
        for i in self.itens:
            if i["id"] == item:
                return dict(i)
        from azure.cosmos import exceptions
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
        if "@antes" in p:
            itens = [i for i in itens if i["medidoEm"] < p["@antes"]]
        if "ORDER BY c.medidoEm DESC" in query:
            itens.sort(key=lambda i: i["medidoEm"], reverse=True)
        if "@limite" in p:
            itens = itens[:p["@limite"]]
        import re
        campos = re.match(r"SELECT (?:TOP @limite )?(.+?) FROM", query)
        if campos:
            campos = campos.group(1)
            if campos != "*" and not campos.startswith("VALUE"):
                nomes = [c.strip()[2:] for c in campos.split(",")]
                itens = [{k: i[k] for k in nomes if k in i} for i in itens]
        return iter(itens)

    def _achar(self, item_id):
        for i in self.itens:
            if i["id"] == item_id:
                return i
        from azure.cosmos import exceptions
        raise exceptions.CosmosResourceNotFoundError(status_code=404, message="não achou")

    def create_item(self, body, **_):
        if any(i["id"] == body["id"] for i in self.itens):
            from azure.cosmos import exceptions
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


def usuario(email, perfil="gestor", empresa="E-A", **extra):
    return {"id": email, "nome": email.split("@")[0].title(), "perfil": perfil,
            "empresaId": empresa, "sessao": 0, "senhaHash": "hash", **extra}


class TestAcessoIDOR(unittest.TestCase):
    def setUp(self):
        # Patch os.environ globally so all modules see it
        self.env_patcher = mock.patch.dict('os.environ', {
            "JWT_SECRET": "segredo-de-teste-com-tamanho-suficiente-32b",
            "COSMOS_CONNECTION": "AccountEndpoint=https://test.documents.azure.com:443/;AccountKey=test",
            "COSMOS_DATABASE": "coldtrack",
            "COSMOS_CONTAINER": "leituras",
            "LIMITES_CONTAINER": "limites",
            "MISSAO_CODIGO": "TEST123"
        })
        self.env_patcher.start()

        self.SEGREDO = "segredo-de-teste-com-tamanho-suficiente-32b"

        self.containers = {
            "usuarios": ContainerFalso([
                usuario("ana@a.com", "gestor", "E-A"),
                usuario("bia@a.com", "operador", "E-A"),
                usuario("caio@b.com", "gestor", "E-B"),
            ]),
            "empresas": ContainerFalso([
                {"id": "E-A", "nome": "Frutas do Vale"},
                {"id": "E-B", "nome": "Outra"},
            ]),
            "dispositivos": ContainerFalso([
                {"id": "sensor-a1", "empresaId": "E-A", "descricao": "Sensor Ana"},
                {"id": "sensor-b1", "empresaId": "E-B", "descricao": "Sensor Caio"},
            ]),
            "veiculos": ContainerFalso([
                {"id": "E-A~CT-001", "empresaId": "E-A", "deviceId": "sensor-a1"},
                {"id": "E-B~CT-002", "empresaId": "E-B", "deviceId": "sensor-b1"},
            ]),
            "viagens": ContainerFalso([
                {"id": "E-A~V-001", "empresaId": "E-A", "veiculo": "CT-001"},
                {"id": "E-B~V-002", "empresaId": "E-B", "veiculo": "CT-002"},
            ]),
            "limites": ContainerFalso([]),
        }
        # Mock the container function to return our fake containers
        self.container_patcher = mock.patch.object(function_app_mod, "container",
                                                   lambda nome=None: self.containers[nome])
        self.container_patcher.start()
        # Recreate LIMITES with the mocked container
        function_app_mod.LIMITES = function_app_mod.Limites(
            lambda: function_app_mod.container(os.getenv("LIMITES_CONTAINER", "limites")))
        function_app_mod.LIMITES.reiniciar()

        # Mock time
        self.agora = 1_700_000_000
        self.relogio = mock.patch("time.time", lambda: self.agora)
        self.relogio.start()

        # Mock conferir_senha
        self.senha = mock.patch.object(function_app_mod, "conferir_senha",
                                       lambda s, h: h == "hash" and s == "senha-certa-123")
        self.senha.start()

    def tearDown(self):
        self.senha.stop()
        self.relogio.stop()
        self.container_patcher.stop()
        self.env_patcher.stop()
        function_app_mod.LIMITES.reiniciar()

    def token(self, email):
        from seguranca import gerar_token
        return gerar_token(self.containers["usuarios"]._achar(email), self.SEGREDO)

    def chamar(self, rota, metodo, url, corpo=None, email=None, headers=None, **rota_params):
        h = {"Content-Type": "application/json", **(headers or {})}
        if email:
            h["Authorization"] = "Bearer " + self.token(email)
        import json
        dados = json.dumps(corpo).encode() if corpo is not None else b""
        import azure.functions as func
        # Parse query string from URL
        if "?" in url:
            path, query = url.split("?", 1)
            params = {q.split("=")[0]: q.split("=")[1] for q in query.split("&")}
            req = func.HttpRequest(method=metodo, url=path, params=params, body=dados, headers=h, route_params=rota_params)
        else:
            req = func.HttpRequest(method=metodo, url=url, body=dados, headers=h, route_params=rota_params)
        r = rota(req)
        import json as json2
        return r.status_code, json2.loads(r.get_body() or b"null")

    def test_usuario_a_nao_le_dispositivo_usuario_b(self):
        # Ana (empresa A) tenta ler sensor do Caio (empresa B) via GET /leituras
        LEITURAS = function_app_mod.leituras.build().get_user_function()
        status, corpo = self.chamar(LEITURAS, "GET", "/api/leituras?deviceId=sensor-b1",
                                    email="ana@a.com")
        self.assertEqual(status, 404)
        self.assertIn("dispositivo não encontrado", str(corpo))

    def test_usuario_b_le_proprrio_dispositivo(self):
        # Caio (empresa B) lê seu próprio sensor
        LEITURAS = function_app_mod.leituras.build().get_user_function()
        status, corpo = self.chamar(LEITURAS, "GET", "/api/leituras?deviceId=sensor-b1",
                                    email="caio@b.com")
        self.assertEqual(status, 200)
        self.assertEqual(corpo["deviceId"], "sensor-b1")

    def test_usuario_a_nao_acessa_veiculo_usuario_b(self):
        # Ana tenta GET /veiculos/CT-002 (do Caio)
        VEICULOS = function_app_mod.veiculos.build().get_user_function()
        status, corpo = self.chamar(VEICULOS, "GET", "/api/veiculos/CT-002",
                                    email="ana@a.com", id="CT-002")
        self.assertEqual(status, 404)

    def test_usuario_b_acessa_proprrio_veiculo(self):
        # Caio acessa seu próprio veículo
        VEICULOS = function_app_mod.veiculos.build().get_user_function()
        status, corpo = self.chamar(VEICULOS, "GET", "/api/veiculos/CT-002",
                                    email="caio@b.com", id="CT-002")
        self.assertEqual(status, 200)

    def test_usuario_a_nao_acessa_viagem_usuario_b(self):
        VIAGENS = function_app_mod.viagens.build().get_user_function()
        status, corpo = self.chamar(VIAGENS, "GET", "/api/viagens/V-002",
                                    email="ana@a.com", id="V-002")
        self.assertEqual(status, 404)

    def test_usuario_b_acessa_proprria_viagem(self):
        VIAGENS = function_app_mod.viagens.build().get_user_function()
        status, corpo = self.chamar(VIAGENS, "GET", "/api/viagens/V-002",
                                    email="caio@b.com", id="V-002")
        self.assertEqual(status, 200)

    def test_usuario_a_nao_altera_dispositivo_usuario_b(self):
        # Ana tenta PUT /dispositivos/sensor-b1
        DISPOSITIVOS = function_app_mod.dispositivos.build().get_user_function()
        status, corpo = self.chamar(DISPOSITIVOS, "PUT", "/api/dispositivos/sensor-b1",
                                    {"descricao": "hackeado"}, email="ana@a.com", id="sensor-b1")
        self.assertEqual(status, 404)

    def test_usuario_b_altera_proprrio_dispositivo(self):
        DISPOSITIVOS = function_app_mod.dispositivos.build().get_user_function()
        status, corpo = self.chamar(DISPOSITIVOS, "PUT", "/api/dispositivos/sensor-b1",
                                    {"descricao": "atualizado"}, email="caio@b.com", id="sensor-b1")
        self.assertEqual(status, 200)

    def test_log_idor_bloqueado_formato(self):
        from seguranca import log_idor_bloqueado
        import logging
        with mock.patch("logging.warning") as mock_warning:
            log_idor_bloqueado("dispositivo", "id=sensor-b1 user=a***@a.com")
            mock_warning.assert_called_once()
            args, _ = mock_warning.call_args
            format_string = args[0]
            self.assertEqual(format_string, "idor bloqueado [%s] - %s%s")
            self.assertEqual(args[1], "TEST123")
            self.assertEqual(args[2], "dispositivo")
            self.assertIn("id=sensor-b1 user=a***@a.com", args[3])


if __name__ == "__main__":
    unittest.main()