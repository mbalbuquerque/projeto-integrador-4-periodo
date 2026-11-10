"""Testes automatizados das rotas de telemetria, empresas, perfis, leituras,
dispositivos, veículos e viagens de function_app.py.
"""

import json
import os
import re
import time
import unittest
from unittest import mock

import azure.functions as func

import function_app
from seguranca import gerar_chave_dispositivo, gerar_hash, gerar_token, hash_chave
from test_falsos import ContainerFalso

SEGREDO = "segredo-de-teste-com-tamanho-suficiente-para-hs256"
SENHA = "senha-certa-123"
HASH = gerar_hash(SENHA)

PERFIS = function_app.perfis.build().get_user_function()
EMPRESAS = function_app.empresas.build().get_user_function()
TELEMETRIA = function_app.telemetria.build().get_user_function()
LEITURAS = function_app.leituras.build().get_user_function()
DISPOSITIVOS = function_app.dispositivos.build().get_user_function()
VEICULOS = function_app.veiculos.build().get_user_function()
VIAGENS = function_app.viagens.build().get_user_function()
SENHA_ROTA = function_app.senha.build().get_user_function()
USUARIOS = function_app.usuarios.build().get_user_function()


class ContainerRotas(ContainerFalso):
    """Container falso estendido para suportar consultas com SELECT VALUE e TOP."""

    def query_items(self, query, parameters=(), partition_key=None, **kwargs):
        is_value_id = "SELECT VALUE c.id FROM" in query
        q = re.sub(r"SELECT TOP \d+\s+", "SELECT ", query)
        q = re.sub(r"SELECT VALUE c\.id FROM", "SELECT * FROM", q)
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
        if "@status" in p:
            itens = [i for i in itens if i.get("status") in p["@status"]]
        if "ORDER BY c.medidoEm DESC" in query:
            itens.sort(key=lambda i: i["medidoEm"], reverse=True)
        if "@limite" in p:
            itens = itens[:p["@limite"]]

        if is_value_id:
            return iter([item["id"] for item in itens])

        campos_match = re.match(r"SELECT (?:TOP @limite )?(.+?) FROM", q)
        if campos_match:
            campos = campos_match.group(1)
            if campos != "*" and not campos.startswith("VALUE"):
                nomes = [c.strip()[2:] for c in campos.split(",")]
                itens = [{k: i[k] for k in nomes if k in i} for i in itens]
        return iter(itens)


class BaseRotas(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {
            "JWT_SECRET": SEGREDO,
            "COSMOS_CONTAINER": "leituras",
            "COSMOS_CONNECTION": "AccountEndpoint=https://fake.documents.azure.com:443/;"
        })
        self.env.start()

        self.chave_dev1 = gerar_chave_dispositivo()
        self.chave_hash_dev1 = hash_chave(self.chave_dev1)
        self.chave_dev2 = gerar_chave_dispositivo()
        self.chave_hash_dev2 = hash_chave(self.chave_dev2)

        self.agora = int(time.time()) - 60
        self.containers = {
            "usuarios": ContainerRotas([
                {"id": "gestor@a.com", "nome": "Gestor A", "perfil": "gestor",
                 "empresaId": "E-A", "sessao": 0, "senhaHash": HASH},
                {"id": "operador@a.com", "nome": "Operador A", "perfil": "operador",
                 "empresaId": "E-A", "sessao": 0, "senhaHash": HASH},
                {"id": "gestor@b.com", "nome": "Gestor B", "perfil": "gestor",
                 "empresaId": "E-B", "sessao": 0, "senhaHash": HASH},
            ]),
            "empresas": ContainerRotas([
                {"id": "E-A", "nome": "Frutas A", "criadaEm": "2026-01-01T00:00:00+00:00"},
                {"id": "E-B", "nome": "Frutas B", "criadaEm": "2026-01-01T00:00:00+00:00"},
            ]),
            "dispositivos": ContainerRotas([
                {"id": "dev-01", "empresaId": "E-A", "chaveHash": self.chave_hash_dev1,
                 "descricao": "Sensor 1", "criadoEm": "2026-01-01T00:00:00+00:00"},
                {"id": "dev-livre", "empresaId": "E-A", "chaveHash": self.chave_hash_dev2,
                 "descricao": "Sensor Livre", "criadoEm": "2026-01-01T00:00:00+00:00"},
                {"id": "dev-livre2", "empresaId": "E-A", "chaveHash": self.chave_hash_dev2,
                 "descricao": "Sensor Livre 2", "criadoEm": "2026-01-01T00:00:00+00:00"},
                {"id": "dev-b", "empresaId": "E-B", "chaveHash": self.chave_hash_dev1,
                 "descricao": "Sensor de B", "criadoEm": "2026-01-01T00:00:00+00:00"},
            ]),
            "veiculos": ContainerRotas([
                {"id": "E-A~CAM-01", "empresaId": "E-A", "deviceId": "dev-01",
                 "tipo": "Carreta", "perfil": "manga"}
            ]),
            "viagens": ContainerRotas([
                {"id": "E-A~V-001", "empresaId": "E-A", "veiculo": "CAM-01",
                 "origem": "Petrolina", "destino": "Recife", "carga": "Manga",
                 "inicio": "2026-05-10T10:00:00+00:00", "fim": None}
            ]),
            "leituras": ContainerRotas([
                {"id": f"dev-01~{self.agora}", "deviceId": "dev-01", "empresaId": "E-A",
                 "temperatura": 12.0, "umidade": 85.0, "rssi": -60, "perfil": "manga",
                 "status": "NORMAL", "medidoEm": "2026-05-10T10:00:00+00:00",
                 "recebidoEm": "2026-05-10T10:00:01+00:00"}
            ]),
            "limites": ContainerRotas([]),
        }

        self.cosmos = mock.patch.object(
            function_app, "container",
            side_effect=lambda nome=None: self.containers[nome or "leituras"]
        )
        self.cosmos.start()
        self.senha = mock.patch.object(
            function_app, "conferir_senha",
            lambda s, h: h == HASH and s == SENHA
        )
        self.senha.start()

    def tearDown(self):
        self.senha.stop()
        self.cosmos.stop()
        self.env.stop()

    def chamar(self, rota, metodo, url, corpo=None, corpo_raw=None, email=None,
               headers=None, route_params=None, params=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if email:
            u = self.containers["usuarios"].read_item(email, partition_key=email)
            h["Authorization"] = "Bearer " + gerar_token(u, SEGREDO)
        if corpo_raw is not None:
            dados = corpo_raw
        elif corpo is not None:
            dados = json.dumps(corpo).encode()
        else:
            dados = b""
        req = func.HttpRequest(
            method=metodo,
            url=url,
            body=dados,
            headers=h,
            route_params=route_params or {},
            params=params or {},
        )
        r = rota(req)
        b = r.get_body() or b"null"
        try:
            corpo_ret = json.loads(b)
        except Exception:
            corpo_ret = b
        return r.status_code, corpo_ret


class TestPerfisEEmpresas(BaseRotas):
    def test_perfis(self):
        status, corpo = self.chamar(PERFIS, "GET", "/api/perfis")
        self.assertEqual(status, 200)
        self.assertIn("perfis", corpo)
        ids = [p["id"] for p in corpo["perfis"]]
        self.assertIn("manga", ids)
        self.assertIn("uva", ids)

    def test_empresas_corpo_invalido(self):
        status, corpo = self.chamar(EMPRESAS, "POST", "/api/empresas", corpo_raw=b"nao json")
        self.assertEqual(status, 400)
        self.assertIn("corpo não é JSON válido", corpo["erros"])

    def test_empresas_validacao_falha(self):
        status, corpo = self.chamar(EMPRESAS, "POST", "/api/empresas", {"empresa": ""})
        self.assertEqual(status, 400)
        self.assertTrue(len(corpo["erros"]) > 0)

    def test_empresas_email_ja_existe(self):
        status, corpo = self.chamar(EMPRESAS, "POST", "/api/empresas", {
            "empresa": "Nova", "nome": "Gestor", "email": "gestor@a.com", "senha": "senha-forte-123"
        })
        self.assertEqual(status, 409)
        self.assertIn("já existe uma conta com esse e-mail", corpo["erros"])

    def test_empresas_sucesso(self):
        status, corpo = self.chamar(EMPRESAS, "POST", "/api/empresas", {
            "empresa": "Agro Frutas", "nome": "Silvia", "email": "silvia@agro.com",
            "senha": "senha-forte-123"
        })
        self.assertEqual(status, 201)
        self.assertIn("token", corpo)
        self.assertEqual(corpo["usuario"]["empresa"], "Agro Frutas")


class TestTelemetria(BaseRotas):
    def test_telemetria_corpo_invalido(self):
        status, corpo = self.chamar(TELEMETRIA, "POST", "/api/telemetria", corpo_raw=b"{")
        self.assertEqual(status, 400)

    def test_telemetria_validacao_falha(self):
        status, corpo = self.chamar(TELEMETRIA, "POST", "/api/telemetria", {"deviceId": ""})
        self.assertEqual(status, 400)

    def test_telemetria_dispositivo_inexistente(self):
        payload = {"deviceId": "dev-inexistente", "temperatura": 12.0, "umidade": 80.0, "rssi": -60}
        status, corpo = self.chamar(TELEMETRIA, "POST", "/api/telemetria", payload,
                                    headers={"x-device-key": "qualquer"})
        self.assertEqual(status, 401)

    def test_telemetria_chave_errada(self):
        payload = {"deviceId": "dev-01", "temperatura": 12.0, "umidade": 80.0, "rssi": -60}
        status, corpo = self.chamar(TELEMETRIA, "POST", "/api/telemetria", payload,
                                    headers={"x-device-key": "chave-errada"})
        self.assertEqual(status, 401)

    def test_telemetria_sucesso_com_veiculo(self):
        payload = {
            "deviceId": "dev-01", "temperatura": 12.5, "umidade": 85.0, "rssi": -65,
            "medidoEm": self.agora + 10
        }
        status, corpo = self.chamar(TELEMETRIA, "POST", "/api/telemetria", payload,
                                    headers={"x-device-key": self.chave_dev1})
        self.assertEqual(status, 201)
        self.assertEqual(corpo["perfil"], "manga")
        self.assertEqual(corpo["status"], "NORMAL")
        self.assertIn("faixa", corpo)

    def test_telemetria_sucesso_sem_veiculo_e_sem_medido_em(self):
        # dev-livre não tem veículo associado: usa PERFIL_PADRAO ("demonstrativo")
        payload = {"deviceId": "dev-livre", "temperatura": 10.0, "umidade": 70.0, "rssi": None}
        status, corpo = self.chamar(TELEMETRIA, "POST", "/api/telemetria", payload,
                                    headers={"x-device-key": self.chave_dev2})
        self.assertEqual(status, 201)
        self.assertEqual(corpo["perfil"], "demonstrativo")

    def test_telemetria_duplicada_reenvio_identico(self):
        payload = {
            "deviceId": "dev-01", "temperatura": 12.0, "umidade": 85.0, "rssi": -60,
            "medidoEm": self.agora
        }
        status, corpo = self.chamar(TELEMETRIA, "POST", "/api/telemetria", payload,
                                    headers={"x-device-key": self.chave_dev1})
        self.assertEqual(status, 200)
        self.assertTrue(corpo["duplicada"])

    def test_telemetria_conflito_valores_diferentes(self):
        payload = {
            "deviceId": "dev-01", "temperatura": 25.0, "umidade": 50.0, "rssi": -60,
            "medidoEm": self.agora
        }
        status, corpo = self.chamar(TELEMETRIA, "POST", "/api/telemetria", payload,
                                    headers={"x-device-key": self.chave_dev1})
        self.assertEqual(status, 409)


class TestLeituras(BaseRotas):
    def test_leituras_sem_device_id(self):
        status, corpo = self.chamar(LEITURAS, "GET", "/api/leituras", email="operador@a.com")
        self.assertEqual(status, 400)
        self.assertIn("informe ?deviceId=", corpo["erros"])

    def test_leituras_dispositivo_de_outra_empresa(self):
        status, corpo = self.chamar(LEITURAS, "GET", "/api/leituras", email="operador@a.com",
                                    params={"deviceId": "dev-b"})
        self.assertEqual(status, 404)

    def test_leituras_limite_invalido(self):
        status, corpo = self.chamar(LEITURAS, "GET", "/api/leituras", email="operador@a.com",
                                    params={"deviceId": "dev-01", "limite": "nao-int"})
        self.assertEqual(status, 400)
        self.assertIn("limite deve ser inteiro", corpo["erros"])

    def test_leituras_filtros_invalidos(self):
        status, corpo = self.chamar(LEITURAS, "GET", "/api/leituras", email="operador@a.com",
                                    params={"deviceId": "dev-01", "horas": "abc"})
        self.assertEqual(status, 400)

    def test_leituras_sucesso_com_filtros(self):
        status, corpo = self.chamar(LEITURAS, "GET", "/api/leituras", email="operador@a.com",
                                    params={"deviceId": "dev-01", "limite": "10",
                                            "horas": "24", "status": "NORMAL,ATENCAO"})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["deviceId"], "dev-01")


class TestDispositivos(BaseRotas):
    def test_get_dispositivos(self):
        status, corpo = self.chamar(
            DISPOSITIVOS, "GET", "/api/dispositivos", email="operador@a.com"
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["dispositivos"]), 3)

    def test_post_dispositivo_permissao_operador_nega(self):
        status, _ = self.chamar(DISPOSITIVOS, "POST", "/api/dispositivos",
                                {"id": "dev-novo"}, email="operador@a.com")
        self.assertEqual(status, 403)

    def test_post_dispositivo_corpo_invalido(self):
        status, _ = self.chamar(DISPOSITIVOS, "POST", "/api/dispositivos",
                                corpo_raw=b"nao-json", email="gestor@a.com")
        self.assertEqual(status, 400)

    def test_post_dispositivo_validacao_erro(self):
        status, _ = self.chamar(DISPOSITIVOS, "POST", "/api/dispositivos",
                                {"id": "x"}, email="gestor@a.com")
        self.assertEqual(status, 400)

    def test_post_dispositivo_sucesso(self):
        status, corpo = self.chamar(DISPOSITIVOS, "POST", "/api/dispositivos",
                                    {"id": "dev-novo", "descricao": "Novo"}, email="gestor@a.com")
        self.assertEqual(status, 201)
        self.assertIn("chave", corpo)
        self.assertEqual(corpo["id"], "dev-novo")

    def test_post_dispositivo_ja_existe(self):
        status, corpo = self.chamar(DISPOSITIVOS, "POST", "/api/dispositivos",
                                    {"id": "dev-01"}, email="gestor@a.com")
        self.assertEqual(status, 409)

    def test_put_dispositivo_nao_encontrado(self):
        status, _ = self.chamar(DISPOSITIVOS, "PUT", "/api/dispositivos/dev-xyz",
                                email="gestor@a.com", route_params={"id": "dev-xyz"})
        self.assertEqual(status, 404)

    def test_put_dispositivo_sucesso(self):
        status, corpo = self.chamar(DISPOSITIVOS, "PUT", "/api/dispositivos/dev-01",
                                    email="gestor@a.com", route_params={"id": "dev-01"})
        self.assertEqual(status, 200)
        self.assertIn("chave", corpo)

    def test_delete_dispositivo_em_uso_por_veiculo(self):
        status, corpo = self.chamar(DISPOSITIVOS, "DELETE", "/api/dispositivos/dev-01",
                                    email="gestor@a.com", route_params={"id": "dev-01"})
        self.assertEqual(status, 409)
        self.assertTrue(any("veículo CAM-01 usa este sensor" in e for e in corpo["erros"]))

    def test_delete_dispositivo_sucesso(self):
        status, _ = self.chamar(DISPOSITIVOS, "DELETE", "/api/dispositivos/dev-livre",
                                email="gestor@a.com", route_params={"id": "dev-livre"})
        self.assertEqual(status, 204)


class TestVeiculosEViagens(BaseRotas):
    def test_veiculos_fluxo_completo(self):
        # GET
        status, corpo = self.chamar(VEICULOS, "GET", "/api/veiculos", email="operador@a.com")
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["veiculos"]), 1)
        self.assertEqual(corpo["veiculos"][0]["id"], "CAM-01")

        # POST corpo inválido
        status, _ = self.chamar(
            VEICULOS, "POST", "/api/veiculos", corpo_raw=b"erro", email="gestor@a.com"
        )
        self.assertEqual(status, 400)

        # POST sensor não registrado
        status, corpo = self.chamar(VEICULOS, "POST", "/api/veiculos",
                                    {"id": "CAM-02", "tipo": "Truck", "deviceId": "dev-inexistente",
                                     "perfil": "manga"}, email="gestor@a.com")
        self.assertEqual(status, 400)
        self.assertTrue(any("não está registrado em Sensores" in e for e in corpo["erros"]))

        # POST sensor já em uso por outro veículo
        status, corpo = self.chamar(VEICULOS, "POST", "/api/veiculos",
                                    {"id": "CAM-02", "tipo": "Truck", "deviceId": "dev-01",
                                     "perfil": "manga"}, email="gestor@a.com")
        self.assertEqual(status, 400)
        self.assertTrue(any("já está no veículo CAM-01" in e for e in corpo["erros"]))

        # POST sucesso
        status, corpo = self.chamar(VEICULOS, "POST", "/api/veiculos",
                                    {"id": "CAM-02", "tipo": "Truck", "deviceId": "dev-livre",
                                     "perfil": "uva"}, email="gestor@a.com")
        self.assertEqual(status, 201)
        self.assertEqual(corpo["id"], "CAM-02")

        # POST duplicado (com outro sensor livre, para falhar no ID repetido e não no sensor em uso)
        status, _ = self.chamar(VEICULOS, "POST", "/api/veiculos",
                                {"id": "CAM-02", "tipo": "Truck", "deviceId": "dev-livre2",
                                 "perfil": "uva"}, email="gestor@a.com")
        self.assertEqual(status, 409)

        # PUT sem id na rota
        status, _ = self.chamar(VEICULOS, "PUT", "/api/veiculos",
                                {"tipo": "Truck 2"}, email="gestor@a.com")
        self.assertEqual(status, 400)

        # PUT não encontrado (com sensor livre, para passar na validação e falhar na busca do banco)
        status, _ = self.chamar(
            VEICULOS, "PUT", "/api/veiculos/CAM-99",
            {"id": "CAM-99", "tipo": "Truck 2", "deviceId": "dev-livre2", "perfil": "uva"},
            email="gestor@a.com", route_params={"id": "CAM-99"}
        )
        self.assertEqual(status, 404)

        # PUT sucesso
        status, corpo = self.chamar(
            VEICULOS, "PUT", "/api/veiculos/CAM-02",
            {"id": "CAM-02", "tipo": "Truck Modificado", "deviceId": "dev-livre", "perfil": "uva"},
            email="gestor@a.com", route_params={"id": "CAM-02"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(corpo["tipo"], "Truck Modificado")

        # DELETE sem id
        status, _ = self.chamar(VEICULOS, "DELETE", "/api/veiculos", email="gestor@a.com")
        self.assertEqual(status, 400)

        # DELETE não encontrado
        status, _ = self.chamar(VEICULOS, "DELETE", "/api/veiculos/CAM-99",
                                email="gestor@a.com", route_params={"id": "CAM-99"})
        self.assertEqual(status, 404)

        # DELETE sucesso
        status, _ = self.chamar(VEICULOS, "DELETE", "/api/veiculos/CAM-02",
                                email="gestor@a.com", route_params={"id": "CAM-02"})
        self.assertEqual(status, 204)

    def test_viagens_fluxo_completo(self):
        # GET
        status, corpo = self.chamar(VIAGENS, "GET", "/api/viagens", email="operador@a.com")
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["viagens"]), 1)

        # POST veículo não cadastrado
        status, corpo = self.chamar(VIAGENS, "POST", "/api/viagens", {
            "veiculo": "CAM-INEXISTENTE", "origem": "Petrolina", "destino": "Recife",
            "carga": "Uva", "inicio": "2026-05-10T12:00:00+00:00"
        }, email="gestor@a.com")
        self.assertEqual(status, 400)
        self.assertTrue(any("não está cadastrado" in e for e in corpo["erros"]))

        # POST sucesso com ID gerado automaticamente
        status, corpo = self.chamar(VIAGENS, "POST", "/api/viagens", {
            "veiculo": "CAM-01", "origem": "Petrolina", "destino": "Salvador",
            "carga": "Manga Palmer", "inicio": "2026-05-11T12:00:00+00:00"
        }, email="gestor@a.com")
        self.assertEqual(status, 201)
        self.assertTrue(corpo["id"].startswith("V-"))

        # PUT sucesso
        nova_viagem_id = corpo["id"]
        status, corpo = self.chamar(VIAGENS, "PUT", f"/api/viagens/{nova_viagem_id}", {
            "veiculo": "CAM-01", "origem": "Petrolina", "destino": "Salvador",
            "carga": "Manga Palmer", "inicio": "2026-05-11T12:00:00+00:00",
            "fim": "2026-05-12T12:00:00+00:00"
        }, email="gestor@a.com", route_params={"id": nova_viagem_id})
        self.assertEqual(status, 200)
        self.assertIsNotNone(corpo["fim"])

        # DELETE sucesso
        status, _ = self.chamar(VIAGENS, "DELETE", f"/api/viagens/{nova_viagem_id}",
                                email="gestor@a.com", route_params={"id": nova_viagem_id})
        self.assertEqual(status, 204)


class TestBordasUsuariosESenha(BaseRotas):
    def test_login_corpo_invalido(self):
        LOGIN = function_app.login.build().get_user_function()
        status, corpo = self.chamar(LOGIN, "POST", "/api/login", corpo_raw=b"nao-json")
        self.assertEqual(status, 400)

    def test_senha_bordas(self):
        # Sem autorização
        status, _ = self.chamar(
            SENHA_ROTA, "POST", "/api/senha", {"atual": SENHA, "nova": "nova12345"}
        )
        self.assertEqual(status, 401)

        # Corpo inválido
        status, _ = self.chamar(SENHA_ROTA, "POST", "/api/senha", corpo_raw=b"nao-json",
                                email="operador@a.com")
        self.assertEqual(status, 400)

        # Validação falha (ex: senha nova curta)
        status, corpo = self.chamar(SENHA_ROTA, "POST", "/api/senha",
                                    {"atual": SENHA, "nova": "123"}, email="operador@a.com")
        self.assertEqual(status, 400)

        # Senha atual incorreta
        status, corpo = self.chamar(SENHA_ROTA, "POST", "/api/senha",
                                    {"atual": "senha-errada-999", "nova": "nova-senha-123"},
                                    email="operador@a.com")
        self.assertEqual(status, 400)
        self.assertIn("atual: senha atual incorreta", corpo["erros"])

    def test_leituras_sem_autorizacao(self):
        status, _ = self.chamar(LEITURAS, "GET", "/api/leituras", params={"deviceId": "dev-01"})
        self.assertEqual(status, 401)

    def test_veiculos_e_viagens_bordas(self):
        # Operador não pode criar veículo
        status, _ = self.chamar(
            VEICULOS, "POST", "/api/veiculos",
            {"id": "CAM-03", "tipo": "Van", "deviceId": "dev-livre", "perfil": "manga"},
            email="operador@a.com"
        )
        self.assertEqual(status, 403)

        # POST veículo com dados inválidos
        status, _ = self.chamar(VEICULOS, "POST", "/api/veiculos",
                                {"id": "C!"}, email="gestor@a.com")
        self.assertEqual(status, 400)

        # POST viagem com dados inválidos
        status, _ = self.chamar(VIAGENS, "POST", "/api/viagens",
                                {"veiculo": ""}, email="gestor@a.com")
        self.assertEqual(status, 400)

    def test_usuarios_put_concorrente_e_post_invalido(self):
        # PUT em usuário que some no meio do patch
        with mock.patch.object(function_app, "_patch_usuario", return_value=None):
            status, _ = self.chamar(USUARIOS, "PUT", "/api/usuarios/operador@a.com",
                                    {"senha": "nova-senha-123"}, email="gestor@a.com",
                                    route_params={"id": "operador@a.com"})
            self.assertEqual(status, 404)

        # POST usuário com dados inválidos
        status, corpo = self.chamar(USUARIOS, "POST", "/api/usuarios",
                                    {"email": "invalido"}, email="gestor@a.com")
        self.assertEqual(status, 400)

    def test_container_real_init(self):
        self.cosmos.stop()
        try:
            with mock.patch("function_app.CosmosClient") as mock_client:
                mock_instancia = mock.MagicMock()
                mock_client.from_connection_string.return_value = mock_instancia
                function_app._banco = None
                function_app._containers.clear()
                c1 = function_app.container("test-container")
                c2 = function_app.container("test-container")  # já no cache
                c3 = function_app.container()  # nome padrão pelo env
                self.assertIsNotNone(c1)
                self.assertIsNotNone(c2)
                self.assertIsNotNone(c3)
                mock_client.from_connection_string.assert_called_once()
        finally:
            self.cosmos.start()

    def test_troca_senha_usuario_removido_no_meio(self):
        # Quando _patch_usuario retorna None (usuário removido no meio da chamada)
        with mock.patch.object(function_app, "_patch_usuario", return_value=None):
            status, corpo = self.chamar(SENHA_ROTA, "POST", "/api/senha",
                                        {"atual": SENHA, "nova": "nova-senha-123"},
                                        email="operador@a.com")
            self.assertEqual(status, 401)

    def test_usuarios_gestor_nao_deleta_a_si_mesmo(self):
        status, corpo = self.chamar(USUARIOS, "DELETE", "/api/usuarios/gestor@a.com",
                                    email="gestor@a.com", route_params={"id": "gestor@a.com"})
        self.assertEqual(status, 400)
        self.assertIn("você não pode remover o próprio usuário", corpo["erros"])

    def test_usuarios_put_senha_curta(self):
        status, corpo = self.chamar(USUARIOS, "PUT", "/api/usuarios/operador@a.com",
                                    {"senha": "curta"}, email="gestor@a.com",
                                    route_params={"id": "operador@a.com"})
        self.assertEqual(status, 400)
        self.assertTrue(any("senha: no mínimo" in e for e in corpo["erros"]))

    def test_usuarios_post_email_duplicado(self):
        status, corpo = self.chamar(USUARIOS, "POST", "/api/usuarios",
                                    {"email": "operador@a.com", "nome": "Operador",
                                     "perfil": "operador", "senha": "senha-valida-123"},
                                    email="gestor@a.com")
        self.assertEqual(status, 409)
        self.assertIn("já existe um usuário com esse e-mail", corpo["erros"])

    def test_usuarios_post_corpo_invalido(self):
        status, _ = self.chamar(USUARIOS, "POST", "/api/usuarios",
                                corpo_raw=b"nao-json", email="gestor@a.com")
        self.assertEqual(status, 400)

    def test_usuarios_get_lista(self):
        status, corpo = self.chamar(USUARIOS, "GET", "/api/usuarios", email="gestor@a.com")
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["usuarios"]), 2)


if __name__ == "__main__":
    unittest.main()
