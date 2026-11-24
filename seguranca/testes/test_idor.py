#!/usr/bin/env python3
"""Testes de IDOR (verificacao de dono) — roda com: python -m unittest seguranca.testes.test_idor"""

import os
import sys
import unittest
from unittest import mock

# Set environment variables BEFORE importing any modules that read them
os.environ["JWT_SECRET"] = "segredo-de-teste-com-tamanho-suficiente-32b"
os.environ["COSMOS_CONNECTION"] = "AccountEndpoint=https://test.documents.azure.com:443/;AccountKey=test"
os.environ["COSMOS_DATABASE"] = "coldtrack"
os.environ["COSMOS_CONTAINER"] = "leituras"
os.environ["LIMITES_CONTAINER"] = "limites"
os.environ["MISSAO_CODIGO"] = "TEST123"

# Adiciona o diretorio cloud/function ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud', 'function'))

import function_app as function_app_mod
from test_falsos import ContainerFalso


def usuario(email, perfil="gestor", empresa="E-A", **extra):
    return {"id": email, "nome": email.split("@")[0].title(), "perfil": perfil,
            "empresaId": empresa, "sessao": 0, "senhaHash": "hash", **extra}


class TestAcessoIDOR(unittest.TestCase):
    def setUp(self):
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
            "leituras": ContainerFalso([]),
            "limites": ContainerFalso([]),
        }
        # Mock the container function to return our fake containers
        self.container_patcher = mock.patch.object(function_app_mod, "container",
                                                   lambda nome=None: self.containers[nome or "leituras"])
        self.container_patcher.start()
        # Recreate LIMITES with the mocked container
        function_app_mod.LIMITES = function_app_mod.Limites(
            lambda: function_app_mod.container(os.getenv("LIMITES_CONTAINER", "limites")))
        function_app_mod.LIMITES.reiniciar()

        # Mock conferir_senha
        self.senha = mock.patch.object(function_app_mod, "conferir_senha",
                                       lambda s, h: h == "hash" and s == "senha-certa-123")
        self.senha.start()

    def tearDown(self):
        self.senha.stop()
        self.container_patcher.stop()
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
        # Caio (empresa B) le seu proprio sensor
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
        # Caio acessa seu proprio veiculo
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
                self.assertEqual(format_string, "idor bloqueado [%s] - %s")
                self.assertEqual(args[1], "TEST123")
                self.assertIn("dispositivo - id=sensor-b1 user=a***@a.com", args[2])


if __name__ == "__main__":
    unittest.main()
