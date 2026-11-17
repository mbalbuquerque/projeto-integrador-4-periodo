"""DELETE /api/empresa: exclusão da empresa inteira pelo gestor (LGPD).

Usa a mesma base falsa do test_rotas (duas empresas, E-A e E-B): tudo de E-A
some, nada de E-B é tocado.
"""

import time
from unittest import mock

from azure.cosmos import exceptions

import function_app
from cadastros import validar_exclusao_empresa
from test_rotas import SENHA, BaseRotas, ContainerRotas

EXCLUIR = function_app.excluir_empresa.build().get_user_function()
EU = function_app.eu.build().get_user_function()
URL = "/api/empresa"
PEDIDO = {"confirmacao": "Frutas A", "senha": SENHA}


class BaseExclusao(BaseRotas):
    def setUp(self):
        super().setUp()
        usuarios = self.containers["usuarios"].itens
        for u in usuarios:
            if u["id"] == "operador@a.com":
                u["push"] = [{"endpoint": "https://push.example/1", "keys": {}}]
        # Leitura de um sensor já removido antes: também é da empresa e precisa sair.
        self.containers["leituras"].itens.append(
            {"id": "dev-velho~1", "deviceId": "dev-velho", "empresaId": "E-A",
             "medidoEm": "2026-05-01T10:00:00+00:00"})
        self.containers["leituras"].itens.append(
            {"id": "dev-b~1", "deviceId": "dev-b", "empresaId": "E-B",
             "medidoEm": "2026-05-01T10:00:00+00:00"})
        self.containers["veiculos"].itens.append(
            {"id": "E-B~CAM-01", "empresaId": "E-B", "deviceId": "dev-b",
             "tipo": "Baú", "perfil": "uva"})
        self.containers["viagens"].itens.append(
            {"id": "E-B~V-001", "empresaId": "E-B", "veiculo": "CAM-01"})

    def excluir(self, corpo=PEDIDO, email="gestor@a.com", **kw):
        return self.chamar(EXCLUIR, "DELETE", URL, corpo, email=email, **kw)

    def da_empresa(self, empresa):
        return {nome: sorted(i["id"] for i in c.itens if i.get("empresaId") == empresa
                             or (nome == "empresas" and i["id"] == empresa))
                for nome, c in self.containers.items() if nome != "limites"}

    def assert_b_intacta(self):
        self.assertEqual(self.da_empresa("E-B"), {
            "usuarios": ["gestor@b.com"], "empresas": ["E-B"], "dispositivos": ["dev-b"],
            "veiculos": ["E-B~CAM-01"], "viagens": ["E-B~V-001"], "leituras": ["dev-b~1"]})

    def assert_a_vazia(self):
        self.assertEqual(self.da_empresa("E-A"), {n: [] for n in self.da_empresa("E-A")})


class TestExclusao(BaseExclusao):
    def test_apaga_tudo_da_empresa_e_nada_da_outra(self):
        status, corpo = self.excluir()
        self.assertEqual(status, 200)
        self.assertTrue(corpo["excluida"])
        self.assertEqual(corpo["removidos"], {
            "dispositivos": 3, "leituras": 2, "viagens": 1, "veiculos": 1,
            "usuarios": 2, "empresas": 1})
        self.assert_a_vazia()
        self.assert_b_intacta()

    def test_token_do_gestor_morre_depois(self):
        cabecalho = {"Authorization": "Bearer " + function_app.gerar_token(
            self.containers["usuarios"].read_item("gestor@a.com", "gestor@a.com"),
            "segredo-de-teste-com-tamanho-suficiente-para-hs256")}
        self.assertEqual(self.excluir()[0], 200)
        status, _ = self.chamar(EU, "GET", "/api/eu", headers=cabecalho)
        self.assertEqual(status, 401)
        # Repetir com o mesmo token não acha mais ninguém: 401, nada quebra.
        status, _ = self.chamar(EXCLUIR, "DELETE", URL, PEDIDO, headers=cabecalho)
        self.assertEqual(status, 401)

    def test_confirma_pelo_codigo_e_sem_diferenca_de_maiusculas(self):
        self.assertEqual(self.excluir({"confirmacao": " e-a ", "senha": SENHA})[0], 200)
        self.assert_a_vazia()

    def test_confirma_pelo_nome_sem_diferenca_de_maiusculas(self):
        self.assertEqual(self.excluir({"confirmacao": "FRUTAS a", "senha": SENHA})[0], 200)

    def test_confirmacao_errada_nao_apaga_nada(self):
        antes = self.da_empresa("E-A")
        status, corpo = self.excluir({"confirmacao": "Frutas B", "senha": SENHA})
        self.assertEqual(status, 400)
        self.assertEqual(corpo["erros"], ["confirmacao: não confere com o nome da empresa"])
        self.assertEqual(self.da_empresa("E-A"), antes)

    def test_senha_errada_conta_falha_e_nao_apaga(self):
        antes = self.da_empresa("E-A")
        status, corpo = self.excluir({"confirmacao": "Frutas A", "senha": "errada-123"})
        self.assertEqual(status, 400)
        self.assertEqual(corpo["erros"], ["senha: senha atual incorreta"])
        self.assertEqual(self.da_empresa("E-A"), antes)
        gestor = self.containers["usuarios"].read_item("gestor@a.com", "gestor@a.com")
        self.assertEqual(gestor["falhas"], 1)

    def test_conta_em_espera(self):
        for u in self.containers["usuarios"].itens:
            if u["id"] == "gestor@a.com":
                u["bloqueadoAte"] = time.time() + 600
        status, corpo = self.excluir()
        self.assertEqual(status, 429)
        self.assertEqual(corpo["erros"], [function_app.MSG_SENHA_EM_ESPERA])
        self.assertIn("E-A", self.da_empresa("E-A")["empresas"])

    def test_validacao(self):
        for corpo, erro in (
                ({"senha": SENHA}, "confirmacao: digite o nome da empresa para confirmar"),
                ({"confirmacao": "  ", "senha": SENHA},
                 "confirmacao: digite o nome da empresa para confirmar"),
                ({"confirmacao": "Frutas A"}, "senha: informe a sua senha atual"),
                ({"confirmacao": "Frutas A", "senha": 123}, "senha: informe a sua senha atual"),
                ({"confirmacao": "Frutas A", "senha": "x" * 129},
                 "senha: no máximo 128 caracteres"),
                ([], "corpo deve ser um objeto JSON")):
            with self.subTest(corpo=corpo):
                status, resp = self.excluir(corpo)
                self.assertEqual(status, 400)
                self.assertIn(erro, resp["erros"])

    def test_corpo_nao_json(self):
        status, corpo = self.excluir(corpo=None, corpo_raw=b"{x")
        self.assertEqual(status, 400)
        self.assertIn("corpo não é JSON válido", corpo["erros"])

    def test_so_gestor(self):
        self.assertEqual(self.excluir(email="operador@a.com")[0], 403)
        self.assertEqual(self.chamar(EXCLUIR, "DELETE", URL, PEDIDO)[0], 401)
        self.assertIn("E-A", self.da_empresa("E-A")["empresas"])

    def test_limite_por_gestor(self):
        errado = {"confirmacao": "outra", "senha": SENHA}
        for _ in range(function_app.EXCLUSOES_POR_HORA):
            self.assertEqual(self.excluir(errado)[0], 400)
        status, corpo = self.excluir()
        self.assertEqual(status, 429)
        self.assertEqual(corpo["erros"], [function_app.MSG_EXCLUSAO_LIMITE])
        self.assertIn("E-A", self.da_empresa("E-A")["empresas"])

    def test_log_sem_dado_pessoal(self):
        with self.assertLogs(level="INFO") as logs:
            self.excluir()
        texto = "\n".join(logs.output)
        self.assertIn("empresa E-A excluída", texto)
        for pessoal in ("gestor@", "operador@", "g***", "Gestor A", "Frutas A"):
            self.assertNotIn(pessoal, texto)


class TestRetomada(BaseExclusao):
    def test_falha_no_meio_e_repeticao_termina(self):
        leituras = self.containers["leituras"]
        original = leituras.delete_item
        chamadas = []

        def cai_na_segunda(item, partition_key, **kw):
            chamadas.append(item)
            if len(chamadas) == 2:
                raise exceptions.CosmosHttpResponseError(status_code=503, message="fora")
            return original(item, partition_key, **kw)

        leituras.delete_item = cai_na_segunda
        with self.assertRaises(exceptions.CosmosHttpResponseError):
            self.excluir()
        # Parou no meio: sensores já foram, a empresa e o gestor continuam.
        self.assertEqual(self.da_empresa("E-A")["dispositivos"], [])
        self.assertEqual(self.da_empresa("E-A")["empresas"], ["E-A"])
        leituras.delete_item = original
        status, corpo = self.excluir()
        self.assertEqual(status, 200)
        self.assertEqual(corpo["removidos"]["leituras"], 1)
        self.assertNotIn("dispositivos", corpo["removidos"])
        self.assert_a_vazia()
        self.assert_b_intacta()

    def test_prazo_responde_202_e_derruba_as_sessoes_dos_outros(self):
        with mock.patch.object(function_app, "_apagar",
                               side_effect=function_app.PrazoEsgotado()):
            status, corpo = self.excluir()
        self.assertEqual(status, 202)
        self.assertFalse(corpo["excluida"])
        self.assertEqual(corpo["mensagem"], function_app.MSG_EXCLUSAO_CONTINUAR)
        operador = self.containers["usuarios"].read_item("operador@a.com", "operador@a.com")
        self.assertEqual(operador["sessao"], 1)
        self.assertEqual(operador["push"], [])
        gestor = self.containers["usuarios"].read_item("gestor@a.com", "gestor@a.com")
        self.assertEqual(gestor["sessao"], 0)
        self.assertEqual(self.excluir()[0], 200)
        self.assert_a_vazia()

    def test_prazo_antes_dos_outros_usuarios(self):
        with mock.patch.object(function_app, "EXCLUSAO_PRAZO_S", -1):
            status, corpo = self.excluir()
        self.assertEqual((status, corpo["removidos"]), (202, {}))

    def test_prazo_no_meio_da_lista(self):
        contagem = {}
        with self.assertRaises(function_app.PrazoEsgotado):
            function_app._apagar("viagens", [{"id": "E-A~V-001"}], "id",
                                 time.monotonic() - 1, contagem)
        self.assertEqual(contagem, {})

    def test_empresa_ja_apagada_confirma_so_pelo_codigo(self):
        empresas = self.containers["empresas"]
        empresas.itens = [i for i in empresas.itens if i["id"] != "E-A"]
        self.assertEqual(self.excluir()[0], 400)
        status, corpo = self.excluir({"confirmacao": "E-A", "senha": SENHA})
        self.assertEqual(status, 200)
        self.assertNotIn("empresas", corpo["removidos"])
        self.assert_a_vazia()

    def test_item_que_some_no_meio_e_ignorado(self):
        class ComFantasma(ContainerRotas):
            def query_items(self, query, parameters=(), partition_key=None, **kw):
                itens = list(super().query_items(query, parameters, partition_key, **kw))
                return iter(itens + [{"id": "fantasma", "deviceId": "x"}])

        self.containers["leituras"] = ComFantasma(self.containers["leituras"].itens)
        status, corpo = self.excluir()
        self.assertEqual(status, 200)
        self.assertEqual(corpo["removidos"]["leituras"], 2)

    def test_tudo_ja_apagado_menos_o_gestor(self):
        for nome, c in self.containers.items():
            if nome != "usuarios":
                c.itens = [i for i in c.itens if i.get("empresaId") != "E-A" and i["id"] != "E-A"]
        self.containers["usuarios"].itens = [
            u for u in self.containers["usuarios"].itens if u["id"] != "operador@a.com"]
        with self.assertLogs(level="INFO") as logs:
            status, corpo = self.excluir({"confirmacao": "E-A", "senha": SENHA})
        self.assertEqual((status, corpo["removidos"]), (200, {"usuarios": 1}))
        self.assertTrue(any("1 usuarios" in linha for linha in logs.output))


class TestValidacao(BaseExclusao):
    def test_validar_exclusao_empresa(self):
        self.assertEqual(validar_exclusao_empresa({"confirmacao": " X ", "senha": "s"}),
                         ([], {"confirmacao": "X", "senha": "s"}))
        self.assertEqual(validar_exclusao_empresa(None)[0], ["corpo deve ser um objeto JSON"])
