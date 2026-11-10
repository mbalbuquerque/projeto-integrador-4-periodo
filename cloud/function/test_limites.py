"""Testes dos limites de uso compartilhados (Cosmos falso). Rodar: python -m unittest -v"""

import json
import os
import unittest
from unittest import mock

from azure.cosmos import exceptions

import chat
import function_app
import limites
from test_assistente import ROTA as ROTA_ASSIST
from test_assistente import BaseRota
from test_assistente import pedido as pedido_assist
from test_chat import BASE, CONFIG, ClienteFalso
from test_chat import ROTA as ROTA_CHAT
from test_chat import pedido as pedido_chat
from test_falsos import ContainerFalso


class TestIp(unittest.TestCase):
    def test_cabecalho_do_azure_vence(self):
        self.assertEqual(limites.ip_do_cliente({"x-azure-clientip": "200.1.2.3",
                                                "x-forwarded-for": "6.6.6.6, 7.7.7.7"}),
                         "200.1.2.3")

    def test_ultimo_salto_do_forwarded_for(self):
        # O primeiro item pode ser forjado pelo cliente; o Azure acrescenta o real no fim.
        self.assertEqual(limites.ip_do_cliente(
            {"x-forwarded-for": "1.1.1.1, 200.1.2.3:5678"}), "200.1.2.3")
        self.assertEqual(limites.ip_do_cliente({"x-forwarded-for": "[2001:db8::1]:443"}),
                         "2001:db8::1")
        self.assertEqual(limites.ip_do_cliente({"x-forwarded-for": "2001:db8::1"}),
                         "2001:db8::1")
        self.assertEqual(limites.ip_do_cliente({"x-forwarded-for": "200.1.2.3, "}), "200.1.2.3")

    def test_sem_cabecalho(self):
        self.assertEqual(limites.ip_do_cliente({}), "desconhecido")


class TestContador(unittest.TestCase):
    def setUp(self):
        self.banco = ContainerFalso([])
        self.lim = limites.Limites(lambda: self.banco)

    def test_conta_na_janela_e_zera_na_seguinte(self):
        self.assertEqual([self.lim.contar("k", 60, agora=t) for t in (0, 10, 59)], [1, 2, 3])
        self.assertEqual(self.lim.total("k", 60, agora=30), 3)
        self.assertEqual(self.lim.contar("k", 60, agora=60), 1)
        self.assertEqual(self.lim.total("outra", 60, agora=60), 0)

    def test_permitir(self):
        self.assertEqual([self.lim.permitir("k", 2, 60, agora=1) for _ in range(3)],
                         [True, True, False])

    def test_soma_atomica_no_banco_com_ttl(self):
        self.lim.contar("chat:ip:200.1.2.3", 60, agora=0)
        self.lim.contar("chat:ip:200.1.2.3", 60, agora=1)
        (doc,) = self.banco.itens
        self.assertEqual(doc["n"], 2)
        self.assertEqual(doc["ttl"], 60 + limites.FOLGA_TTL_S)
        # O id é um hash: o IP não fica gravado.
        self.assertNotIn("200.1.2.3", json.dumps(doc))
        self.assertEqual([(t, ops[0]["op"]) for t, _, ops in self.banco.escritas],
                         [("patch", "incr"), ("patch", "incr")])

    def test_duas_instancias_somam_no_mesmo_contador(self):
        outra = limites.Limites(lambda: self.banco)
        self.assertTrue(self.lim.permitir("k", 2, 60, agora=0))
        self.assertTrue(outra.permitir("k", 2, 60, agora=0))
        self.assertFalse(self.lim.permitir("k", 2, 60, agora=0))

    def test_outra_instancia_cria_no_meio(self):
        # O patch não acha o contador, mas outra instância cria antes do create.
        original = self.banco.create_item

        def criar_concorrente(body, **kw):
            original({**body, "n": 5})
            return original(body, **kw)

        self.banco.create_item = criar_concorrente
        self.assertEqual(self.lim.contar("k", 60, agora=0), 6)

    def test_sem_container_conta_na_memoria_e_avisa_uma_vez(self):
        banco = mock.Mock()
        banco.read.side_effect = exceptions.CosmosResourceNotFoundError(
            status_code=404, message="sem container")
        lim = limites.Limites(lambda: banco)
        with self.assertLogs(level="WARNING") as log:
            resultados = [lim.permitir("k", 2, 60, agora=0) for _ in range(3)]
        self.assertEqual(resultados, [True, True, False])
        self.assertEqual(len(log.output), 1)
        self.assertEqual(banco.read.call_count, 1)
        banco.patch_item.assert_not_called()

    def test_falha_passageira_cai_para_a_memoria(self):
        self.banco.patch_item = mock.Mock(side_effect=exceptions.CosmosHttpResponseError(
            status_code=503, message="fora"))
        with self.assertLogs(level="WARNING"):
            self.assertEqual([self.lim.contar("k", 60, agora=0) for _ in range(2)], [1, 2])


class TestCotaDoChat(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, CONFIG)
        self.env.start()
        self.falso = ClienteFalso()
        self.fabrica = mock.patch.object(chat, "fabrica_cliente", lambda: self.falso)
        self.fabrica.start()
        chat.reiniciar()
        chat._base = list(BASE)
        self.limites = ContainerFalso([])
        self.cosmos = mock.patch.object(function_app, "container",
                                        lambda nome=None: self.limites)
        self.cosmos.start()
        self.teto = mock.patch.object(function_app, "CHAT_POR_DIA", 3)
        self.teto.start()
        function_app.LIMITES.reiniciar()

    def tearDown(self):
        for p in (self.teto, self.cosmos, self.fabrica, self.env):
            p.stop()
        chat.reiniciar()
        function_app.LIMITES.reiniciar()

    def test_teto_diario_vale_para_todos_os_ips(self):
        for n in range(3):
            r = ROTA_CHAT(pedido_chat({"pergunta": "oi"}, ip=f"200.0.0.{n}"))
            self.assertEqual(r.status_code, 200)
        with self.assertLogs(level="WARNING"):
            r = ROTA_CHAT(pedido_chat({"pergunta": "oi"}, ip="201.9.9.9"))
        self.assertEqual(r.status_code, 429)
        self.assertIn("limite de perguntas de hoje", json.loads(r.get_body())["erros"][0])

    def test_pergunta_invalida_nao_gasta_a_cota(self):
        for _ in range(5):
            r = ROTA_CHAT(pedido_chat({"pergunta": ""}, ip="200.0.0.1"))
            self.assertEqual(r.status_code, 400)
        r = ROTA_CHAT(pedido_chat({"pergunta": "oi"}, ip="200.0.0.2"))
        self.assertEqual(r.status_code, 200)

    def test_limite_por_minuto_usa_o_ip_real(self):
        # Trocar o primeiro item do X-Forwarded-For não escapa do limite.
        for n in range(function_app.CHAT_POR_MINUTO):
            ip = f"{n}.{n}.{n}.{n}, 200.1.2.3"
            ROTA_CHAT(pedido_chat({"pergunta": ""}, ip=ip))
        r = ROTA_CHAT(pedido_chat({"pergunta": "oi"}, ip="9.9.9.9, 200.1.2.3"))
        self.assertEqual(r.status_code, 429)


class TestCotaDoAssistente(BaseRota):
    def test_janela_memoria_limpeza_e_total(self):
        memoria = limites.JanelaEmMemoria()
        agora = 1000
        for i in range(5002):
            memoria._contas[f"k{i}"] = (1, agora - 10)
        memoria.contar("nova", agora + 60, 1, agora)
        self.assertEqual(memoria.total("nova"), 1)
        self.assertEqual(memoria.total("inexistente"), 0)

    def test_total_falha_no_banco_cai_para_memoria(self):
        banco_falho = mock.Mock()
        banco_falho.read.return_value = {"id": "falso"}
        banco_falho.read_item.side_effect = RuntimeError("falha no cosmos")
        lim = limites.Limites(lambda: banco_falho)
        self.assertEqual(lim.total("chave", 60), 0)

    def test_total_le_do_banco_quando_existe(self):
        banco = mock.Mock()
        banco.read.return_value = {"id": "falso"}
        banco.read_item.return_value = {"id": "doc", "n": 7}
        lim = limites.Limites(lambda: banco)
        self.assertEqual(lim.total("chave", 60), 7)

    def test_banco_ja_carregado(self):
        lim = limites.Limites(lambda: mock.Mock(read=lambda: {"id": "falso"}))
        lim._container = mock.Mock()
        self.assertIsNotNone(lim._banco())

    def test_total_sem_container_vai_para_memoria(self):
        lim = limites.Limites(lambda: None)
        lim._sem_container = True
        self.assertEqual(lim.total("chave", 60), 0)

    def test_duplo_check_concorrente(self):
        lim = limites.Limites(lambda: None)
        class TravaFalsa:
            def __enter__(self_trava):
                lim._container = mock.Mock()
            def __exit__(self_trava, *a):
                pass
        lim._trava = TravaFalsa()
        c = lim._banco()
        self.assertIsNotNone(c)

    def test_teto_diario_por_empresa(self):
        with mock.patch.object(function_app, "ASSISTENTE_POR_DIA", 2):
            self.assertEqual(self.chamar({"pergunta": "oi"})[0], 200)
            self.assertEqual(self.chamar({"pergunta": "oi"}, email="operador@a.com",
                                         perfil="operador")[0], 200)
            status, corpo = self.chamar({"pergunta": "oi"})
            self.assertEqual(status, 429)
            self.assertIn("limite de perguntas de hoje", corpo["erros"][0])
            # Outra empresa tem a própria cota.
            r = ROTA_ASSIST(pedido_assist({"pergunta": "oi"}, "gestor@b.com", empresa="E-B"))
            self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
