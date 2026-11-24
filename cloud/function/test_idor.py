"""IDOR: o usuário da empresa A não alcança nada da empresa B trocando o ID (#114).

Rodar em cloud/function: python -m unittest test_idor -v

Duas empresas (E-A e E-B), cada uma com sensor, veículo, viagem e usuários. Para cada
rota que recebe ID: A usando o ID de B recebe 404 e o log mostra `idor bloqueado [`;
B usando o próprio continua 200.

`TestAtaqueEntreEmpresas` também roda no commit d44b301 (antes da verificação de dono),
pelo script seguranca/testes/idor_antes_depois.sh: lá os testes de bloqueio FALHAM,
porque o ataque funcionava. Para rodar nos dois commits, o arquivo só usa o que existe
nos dois (rotas pelo nome, gerar_token e o Cosmos falso) e grava os cadastros no formato
de id de cada versão: "<empresa>~<código>" depois do commit 19ace8e, só "<código>" antes.
Rota que não existia em d44b301 (dispositivos, predict/sensor) é pulada lá.
"""

import json
import logging
import os
import time
import unittest
from unittest import mock

import azure.functions as func

import function_app
from seguranca import gerar_token
from test_falsos import ContainerFalso

SEGREDO = "segredo-de-teste-com-tamanho-suficiente-para-hs256"
CODIGO_TESTE = "TESTE1"  # o código de missão de verdade fica só na app setting MISSAO_CODIGO
# Depois do 19ace8e veículos e viagens são gravados como "<empresa>~<código>".
POR_EMPRESA = hasattr(function_app, "id_interno")


def _id(empresa, codigo):
    return f"{empresa}~{codigo}" if POR_EMPRESA else codigo


def usuario(email, perfil="gestor", empresa="E-A", **extra):
    return {"id": email, "nome": email.split("@")[0].title(), "perfil": perfil,
            "empresaId": empresa, "sessao": 0, "senhaHash": "x", **extra}


def leitura(device, empresa, minutos_atras=1):
    medido = time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                           time.gmtime(time.time() - minutos_atras * 60))
    return {"id": f"{device}-{minutos_atras}", "deviceId": device, "empresaId": empresa,
            "temperatura": 4.0, "umidade": 80.0, "rssi": -60, "status": "OK",
            "perfil": "resfriado", "medidoEm": medido, "recebidoEm": medido}


class BaseIdor(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"JWT_SECRET": SEGREDO,
                                                "MISSAO_CODIGO": CODIGO_TESTE})
        self.env.start()
        self.containers = {
            "usuarios": ContainerFalso([
                usuario("ana@a.com"), usuario("bia@a.com", "operador"),
                usuario("mot@a.com", "motorista", veiculo="CT-002"),
                usuario("caio@b.com", empresa="E-B"),
                usuario("duda@b.com", "operador", empresa="E-B"),
            ]),
            "empresas": ContainerFalso([{"id": "E-A", "nome": "Frutas do Vale"},
                                        {"id": "E-B", "nome": "Outra"}]),
            "dispositivos": ContainerFalso([
                {"id": "sensor-a1", "empresaId": "E-A", "descricao": "baú A",
                 "chaveHash": "ha", "criadoEm": "2026-11-01T00:00:00+00:00"},
                {"id": "sensor-b1", "empresaId": "E-B", "descricao": "baú B",
                 "chaveHash": "hb", "criadoEm": "2026-11-01T00:00:00+00:00"},
            ]),
            "veiculos": ContainerFalso([
                {"id": _id("E-A", "CT-001"), "empresaId": "E-A", "tipo": "baú",
                 "deviceId": "sensor-a1", "perfil": "resfriado"},
                {"id": _id("E-B", "CT-002"), "empresaId": "E-B", "tipo": "baú",
                 "deviceId": "sensor-b1", "perfil": "resfriado"},
            ]),
            "viagens": ContainerFalso([
                {"id": _id("E-A", "V-AAA111"), "empresaId": "E-A", "veiculo": "CT-001",
                 "origem": "X", "destino": "Y", "carga": "uva",
                 "inicio": "2026-11-01T00:00:00+00:00", "fim": None},
                {"id": _id("E-B", "V-BBB222"), "empresaId": "E-B", "veiculo": "CT-002",
                 "origem": "X", "destino": "Y", "carga": "leite",
                 "inicio": "2026-11-01T00:00:00+00:00", "fim": None},
            ]),
            "leituras": ContainerFalso([leitura("sensor-a1", "E-A"),
                                        leitura("sensor-b1", "E-B")]),
            "limites": ContainerFalso([]),
        }
        self.cosmos = mock.patch.object(function_app, "container",
                                        lambda nome=None: self.containers[nome or "leituras"])
        self.cosmos.start()
        if hasattr(function_app, "LIMITES"):
            function_app.LIMITES.reiniciar()
        # Sem handler, o aviso iria para o stderr e sujaria a evidência; assertLogs continua vendo.
        self.silencio = logging.NullHandler()
        logging.getLogger().addHandler(self.silencio)

    def tearDown(self):
        logging.getLogger().removeHandler(self.silencio)
        self.cosmos.stop()
        self.env.stop()

    def rota(self, nome):
        if not hasattr(function_app, nome):
            self.skipTest(f"a rota {nome} não existia nesta versão da API")
        return getattr(function_app, nome).build().get_user_function()

    def chamar(self, nome, metodo, email, corpo=None, params=None, **rota_params):
        doc = self.containers["usuarios"]._achar(email)
        h = {"Content-Type": "application/json",
             "Authorization": "Bearer " + gerar_token(doc, SEGREDO)}
        r = self.rota(nome)(func.HttpRequest(
            method=metodo, url=f"/api/{nome}", headers=h, params=params or {},
            route_params=rota_params,
            body=json.dumps(corpo).encode() if corpo is not None else b""))
        return r.status_code, json.loads(r.get_body() or b"null")

    def existe(self, nome, item_id):
        return any(i["id"] == item_id for i in self.containers[nome].itens)

    def bloqueado(self, nome, metodo, email, **kwargs):
        """A chamada recebe 404 e deixa `idor bloqueado [<código>]` no log."""
        with self.assertLogs(level="WARNING") as logs:
            status, corpo = self.chamar(nome, metodo, email, **kwargs)
        self.assertEqual(status, 404, corpo)
        self.assertTrue(any(f"idor bloqueado [{CODIGO_TESTE}]" in m for m in logs.output),
                        logs.output)
        return corpo


class TestAtaqueEntreEmpresas(BaseIdor):
    """A (empresa E-A) troca o ID pelo de B (empresa E-B). Roda também no commit d44b301."""

    def test_ler_leituras_do_sensor_de_b(self):
        corpo = self.bloqueado("leituras", "GET", "ana@a.com", params={"deviceId": "sensor-b1"})
        self.assertNotIn("leituras", corpo)

    def test_apagar_veiculo_de_b(self):
        self.bloqueado("veiculos", "DELETE", "ana@a.com", id="CT-002")
        self.assertTrue(self.existe("veiculos", _id("E-B", "CT-002")))

    def test_apagar_viagem_de_b(self):
        self.bloqueado("viagens", "DELETE", "ana@a.com", id="V-BBB222")
        self.assertTrue(self.existe("viagens", _id("E-B", "V-BBB222")))

    def test_apagar_usuario_de_b(self):
        self.bloqueado("usuarios", "DELETE", "ana@a.com", id="caio@b.com")
        self.assertTrue(self.existe("usuarios", "caio@b.com"))

    def test_trocar_chave_do_sensor_de_b(self):
        self.bloqueado("dispositivos", "PUT", "ana@a.com", id="sensor-b1")
        self.assertEqual(self.containers["dispositivos"]._achar("sensor-b1")["chaveHash"], "hb")

    def test_previsao_do_sensor_de_b(self):
        self.bloqueado("predict_sensor", "GET", "ana@a.com", params={"deviceId": "sensor-b1"})

    def test_b_continua_lendo_o_proprio_sensor(self):
        status, corpo = self.chamar("leituras", "GET", "caio@b.com",
                                    params={"deviceId": "sensor-b1"})
        self.assertEqual(status, 200, corpo)
        self.assertEqual({x["deviceId"] for x in corpo["leituras"]}, {"sensor-b1"})


class TestMatrizDeRotas(BaseIdor):
    """Todas as rotas com ID: o de B dá 404 para A, o próprio continua funcionando."""

    def test_dispositivo_de_b_put_e_delete(self):
        self.bloqueado("dispositivos", "DELETE", "ana@a.com", id="sensor-b1")
        self.assertTrue(self.existe("dispositivos", "sensor-b1"))
        self.bloqueado("dispositivos", "PUT", "ana@a.com", id="")  # sem id na rota

    def test_veiculo_de_b_get_put_delete(self):
        self.bloqueado("veiculos", "GET", "bia@a.com", id="CT-002")
        corpo = {"id": "CT-002", "tipo": "roubado", "deviceId": "sensor-a1"}
        self.bloqueado("veiculos", "PUT", "ana@a.com", corpo=corpo, id="CT-002")
        self.assertEqual(self.containers["veiculos"]._achar("E-B~CT-002")["tipo"], "baú")

    def test_viagem_de_b_get_put(self):
        self.bloqueado("viagens", "GET", "bia@a.com", id="V-BBB222")
        corpo = {"veiculo": "CT-001", "origem": "A", "destino": "B", "carga": "x",
                 "inicio": "2026-11-02T00:00:00+00:00"}
        self.bloqueado("viagens", "PUT", "ana@a.com", corpo=corpo, id="V-BBB222")
        self.assertEqual(self.containers["viagens"]._achar("E-B~V-BBB222")["carga"], "leite")

    def test_usuario_de_b_put(self):
        self.bloqueado("usuarios", "PUT", "ana@a.com", corpo={"senha": "tomada-123456"},
                       id="caio@b.com")
        self.assertEqual(self.containers["usuarios"]._achar("caio@b.com")["senhaHash"], "x")

    def test_operador_le_leituras_e_previsao_de_b(self):
        self.bloqueado("leituras", "GET", "bia@a.com", params={"deviceId": "sensor-b1"})
        self.bloqueado("predict_sensor", "GET", "bia@a.com", params={"deviceId": "sensor-b1"})

    def test_inexistente_e_de_outra_empresa_recebem_a_mesma_resposta(self):
        outro = self.bloqueado("leituras", "GET", "ana@a.com", params={"deviceId": "sensor-b1"})
        nada = self.bloqueado("leituras", "GET", "ana@a.com", params={"deviceId": "nao-existe"})
        self.assertEqual(outro, nada)
        self.assertEqual(self.bloqueado("veiculos", "DELETE", "ana@a.com", id="CT-002"),
                         self.bloqueado("veiculos", "DELETE", "ana@a.com", id="CT-999"))

    def test_dono_continua_usando_os_proprios(self):
        a = "ana@a.com"
        self.assertEqual(self.chamar("leituras", "GET", a,
                                     params={"deviceId": "sensor-a1"})[0], 200)
        self.assertEqual(self.chamar("predict_sensor", "GET", a,
                                     params={"deviceId": "sensor-a1"})[0], 200)
        status, corpo = self.chamar("veiculos", "GET", a, id="CT-001")
        self.assertEqual((status, [v["id"] for v in corpo["veiculos"]]), (200, ["CT-001"]))
        self.assertEqual(self.chamar("viagens", "GET", a, id="V-AAA111")[0], 200)
        self.assertEqual(self.chamar("dispositivos", "PUT", a, id="sensor-a1")[0], 200)
        self.assertEqual(self.chamar("viagens", "DELETE", a, id="V-AAA111")[0], 204)
        self.assertEqual(self.chamar("usuarios", "PUT", a, corpo={"senha": "nova-senha-123"},
                                     id="bia@a.com")[0], 200)
        self.assertEqual(self.chamar("usuarios", "DELETE", a, id="bia@a.com")[0], 204)

    def test_item_apagado_entre_a_checagem_e_o_delete(self):
        from azure.cosmos import exceptions
        sumiu = exceptions.CosmosResourceNotFoundError(status_code=404, message="sumiu")
        with mock.patch.object(self.containers["viagens"], "delete_item", side_effect=sumiu):
            status, _ = self.chamar("viagens", "DELETE", "ana@a.com", id="V-AAA111")
        self.assertEqual(status, 404)

    def test_motorista_so_ve_o_veiculo_do_proprio_cadastro(self):
        # O veículo vem do cadastro (relido do banco), nunca da URL: mesmo com o código de
        # um veículo de B gravado, o motorista de A não enxerga nada de B.
        status, corpo = self.chamar("motorista", "GET", "mot@a.com",
                                    params={"veiculo": "CT-002", "deviceId": "sensor-b1"})
        self.assertEqual(status, 404, corpo)


class TestTentativasDeContorno(BaseIdor):
    def test_device_id_em_maiusculas(self):
        self.bloqueado("leituras", "GET", "ana@a.com", params={"deviceId": "SENSOR-B1"})
        self.bloqueado("dispositivos", "DELETE", "ana@a.com", id="SENSOR-B1")
        # A normalização não abre brecha, mas também não quebra o dono.
        self.assertEqual(self.chamar("leituras", "GET", "ana@a.com",
                                     params={"deviceId": "SENSOR-A1"})[0], 200)

    def test_empresa_de_b_no_corpo_do_put(self):
        corpo = {"veiculo": "CT-001", "origem": "A", "destino": "B", "carga": "trocada",
                 "inicio": "2026-11-02T00:00:00+00:00", "empresaId": "E-B"}
        self.bloqueado("viagens", "PUT", "ana@a.com", corpo=corpo, id="V-BBB222")
        self.assertEqual(self.containers["viagens"]._achar("E-B~V-BBB222")["carga"], "leite")
        # Na própria viagem, o empresaId do corpo é ignorado: o dono vem do token.
        status, _ = self.chamar("viagens", "PUT", "ana@a.com", corpo=corpo, id="V-AAA111")
        self.assertEqual(status, 200)
        self.assertEqual(self.containers["viagens"]._achar("E-A~V-AAA111")["empresaId"], "E-A")
        self.assertFalse(self.existe("viagens", "E-B~V-AAA111"))

    def test_device_id_repetido_na_url(self):
        # ?deviceId=sensor-a1&deviceId=sensor-b1: o host do Azure junta os valores com
        # vírgula; nenhum sensor tem esse id. Qualquer que seja o valor que chegue, a
        # checagem e a consulta usam o mesmo.
        for valor in ("sensor-a1,sensor-b1", "sensor-b1,sensor-a1"):
            self.bloqueado("leituras", "GET", "ana@a.com", params={"deviceId": valor})

    def test_token_de_usuario_apagado(self):
        doc = self.containers["usuarios"]._achar("ana@a.com")
        token = gerar_token(doc, SEGREDO)
        self.containers["usuarios"].itens.remove(doc)
        r = self.rota("leituras")(func.HttpRequest(
            method="GET", url="/api/leituras", headers={"Authorization": "Bearer " + token},
            params={"deviceId": "sensor-a1"}, body=b""))
        self.assertEqual(r.status_code, 401)

    def test_id_de_veiculo_com_prefixo_de_outra_empresa(self):
        # "E-B~CT-002" vira "E-A~E-B~CT-002": o prefixo é sempre o da empresa do token.
        self.bloqueado("veiculos", "DELETE", "ana@a.com", id="E-B~CT-002")
        self.assertTrue(self.existe("veiculos", "E-B~CT-002"))


if __name__ == "__main__":
    unittest.main()
