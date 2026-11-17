"""Testes da rota GET /api/predict/sensor e do módulo previsao_sensor (previsão 10 min à frente)."""

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import function_app
import previsao_sensor
from test_rotas import BaseRotas

PREDICT_SENSOR = function_app.predict_sensor.build().get_user_function()

T0 = datetime(2026, 11, 17, 3, 0, tzinfo=timezone.utc)

MODELO = {
    "versao": "teste-v1", "fonte": "teste", "horizonteMin": 10, "janelaMin": 10,
    "lacunaMaxS": 300, "atributos": ["d5", "d10", "m10"], "coeficientes": [1.0, 0.0, 0.0],
    "treino": {"de": "a", "ate": "b", "amostras": 1},
    "teste": {"de": "c", "ate": "d", "amostras": 1},
    "metricas": {"maeModelo": 0.1, "maeBaseline": 0.2, "rmseModelo": 0.1, "rmseBaseline": 0.2},
    "superaBaseline": True,
}


def leitura(minutos, temperatura, perfil="manga", base=T0, device="dev-01", empresa="E-A"):
    momento = (base + timedelta(minutes=minutos)).isoformat()
    return {"id": f"{device}~{momento}", "deviceId": device, "empresaId": empresa,
            "temperatura": temperatura, "umidade": 80.0, "rssi": -60, "perfil": perfil,
            "status": "NORMAL", "medidoEm": momento, "recebidoEm": momento}


def subindo(base=T0, minutos=12, de=10.0, passo=0.2, perfil="manga"):
    """Uma leitura por minuto, de `base - minutos` até `base`, subindo `passo` por minuto."""
    return [leitura(m - minutos, de + passo * m, perfil, base) for m in range(minutos + 1)]


class TestModeloExportado(unittest.TestCase):
    """O modelo_sensor.json publicado precisa ter a forma que a rota usa."""

    def setUp(self):
        with open(previsao_sensor.ARQUIVO, encoding="utf-8") as f:
            self.modelo = json.load(f)

    def test_forma(self):
        m = self.modelo
        self.assertEqual(len(m["atributos"]), len(m["coeficientes"]))
        self.assertEqual(set(m["atributos"]), {"d5", "d10", "m10"})
        self.assertGreater(m["horizonteMin"], 0)
        self.assertGreaterEqual(m["janelaMin"], 10)
        for nome in ("maeModelo", "maeBaseline", "rmseModelo", "rmseBaseline"):
            self.assertGreaterEqual(m["metricas"][nome], 0)

    def test_divisao_temporal_e_veredito_coerente(self):
        m = self.modelo
        self.assertLess(m["treino"]["ate"], m["teste"]["de"])
        self.assertEqual(m["superaBaseline"],
                         m["metricas"]["maeModelo"] < m["metricas"]["maeBaseline"])


class TestSerie(unittest.TestCase):
    def test_serie_ordena_descarta_invalido_e_repetido(self):
        itens = [
            {"medidoEm": "2026-11-17T03:02:00Z", "temperatura": 11.0},
            {"medidoEm": "2026-11-17T03:01:00+00:00", "temperatura": 10},
            {"medidoEm": "2026-11-17T03:01:00+00:00", "temperatura": 99.0},
            {"medidoEm": "quebrado", "temperatura": 1.0},
            {"medidoEm": None, "temperatura": 1.0},
            {"medidoEm": "2026-11-17T03:03:00", "temperatura": 1.0},  # sem fuso
            {"medidoEm": "2026-11-17T03:04:00Z", "temperatura": None},
            {"medidoEm": "2026-11-17T03:05:00Z", "temperatura": True},
            {"medidoEm": "2026-11-17T03:06:00Z", "temperatura": "12"},
        ]
        serie = previsao_sensor.serie_de_leituras(itens)
        self.assertEqual([v for _, v in serie], [10.0, 11.0])
        self.assertLess(serie[0][0], serie[1][0])

    def test_trechos_quebram_na_lacuna(self):
        s = [(T0 + timedelta(seconds=x), 1.0) for x in (0, 20, 40, 400, 420, 1000)]
        partes = previsao_sensor.trechos(s, 300)
        self.assertEqual([len(p) for p in partes], [3, 2, 1])
        self.assertEqual(previsao_sensor.trechos([], 300), [])

    def test_valor_em_pega_ultima_ate_o_instante(self):
        trecho = [(T0, 1.0), (T0 + timedelta(minutes=2), 2.0)]
        tempos = [p[0] for p in trecho]
        self.assertIsNone(previsao_sensor.valor_em(trecho, tempos, T0 - timedelta(seconds=1)))
        self.assertEqual(previsao_sensor.valor_em(trecho, tempos, T0), 1.0)
        self.assertEqual(previsao_sensor.valor_em(trecho, tempos, T0 + timedelta(minutes=1)), 1.0)
        self.assertEqual(previsao_sensor.valor_em(trecho, tempos, T0 + timedelta(minutes=5)), 2.0)

    def test_atributos(self):
        serie = previsao_sensor.serie_de_leituras(subindo())
        a = previsao_sensor.atributos(serie, T0, 10)
        self.assertAlmostEqual(a["y0"], 12.4)
        self.assertAlmostEqual(a["d5"], 1.0)
        self.assertAlmostEqual(a["d10"], 2.0)
        self.assertAlmostEqual(a["m10"], -0.9)

    def test_atributos_sem_janela_inteira(self):
        serie = previsao_sensor.serie_de_leituras(subindo(minutos=9))
        self.assertIsNone(previsao_sensor.atributos(serie, T0, 10))
        self.assertIsNone(previsao_sensor.atributos([], T0, 10))

    def test_estimar(self):
        atrib = {"y0": 10.0, "d5": 1.0, "d10": 2.0, "m10": -0.5}
        modelo = {"atributos": ["d5", "d10", "m10"], "coeficientes": [0.5, 0.25, 2.0]}
        self.assertAlmostEqual(previsao_sensor.estimar(modelo, atrib), 10.0)

    def test_carregar_le_uma_vez(self):
        with mock.patch.object(previsao_sensor, "_modelo", None):
            primeiro = previsao_sensor.carregar()
            with mock.patch("builtins.open", side_effect=AssertionError("leu de novo")):
                self.assertIs(previsao_sensor.carregar(), primeiro)


class TestPrever(unittest.TestCase):
    AGORA = T0 + timedelta(seconds=30)

    def test_modelo_recomendado_antecipa_excursao(self):
        # manga: normal até 13 °C. Sobe 0,2 °C/min: 12,4 agora, modelo (coef d5=1) diz 13,4.
        r = previsao_sensor.prever(MODELO, subindo(), self.AGORA)
        self.assertIsNone(r["motivo"])
        self.assertEqual(r["ultimaLeitura"]["status"], "NORMAL")
        self.assertEqual(r["ultimaLeitura"]["perfil"], "manga")
        self.assertEqual(r["previsao"]["temperatura"], 13.4)
        self.assertEqual(r["previsao"]["status"], "ATENCAO")
        self.assertEqual(r["baseline"]["temperatura"], 12.4)
        self.assertEqual(r["previsao"]["para"], (T0 + timedelta(minutes=10)).isoformat())
        self.assertEqual(r["recomendada"], "modelo")
        self.assertTrue(r["antecipaExcursao"])
        self.assertTrue(r["modelo"]["usaLeiturasDoSensor"])
        self.assertEqual(r["modelo"]["versao"], "teste-v1")

    def test_baseline_recomendado_nunca_antecipa(self):
        modelo = {**MODELO, "superaBaseline": False}
        r = previsao_sensor.prever(modelo, subindo(), self.AGORA)
        self.assertEqual(r["recomendada"], "baseline")
        self.assertEqual(r["previsao"]["status"], "ATENCAO")
        self.assertFalse(r["antecipaExcursao"])

    def test_sem_leituras(self):
        r = previsao_sensor.prever(MODELO, [], self.AGORA)
        self.assertEqual(r["motivo"], "sem_leituras")
        self.assertIsNone(r["ultimaLeitura"])
        self.assertIsNone(r["previsao"])
        self.assertIsNone(r["baseline"])
        self.assertFalse(r["antecipaExcursao"])

    def test_leitura_velha(self):
        r = previsao_sensor.prever(MODELO, subindo(), T0 + timedelta(minutes=6))
        self.assertEqual(r["motivo"], "sem_leitura_recente")
        self.assertEqual(r["ultimaLeitura"]["temperatura"], 12.4)
        self.assertIsNone(r["previsao"])
        self.assertIsNone(r["baseline"])

    def test_historico_curto_so_baseline(self):
        r = previsao_sensor.prever(MODELO, subindo(minutos=5), self.AGORA)
        self.assertEqual(r["motivo"], "historico_insuficiente")
        self.assertIsNone(r["previsao"])
        self.assertEqual(r["baseline"]["temperatura"], 11.0)
        self.assertFalse(r["antecipaExcursao"])

    def test_lacuna_no_meio_corta_o_historico(self):
        itens = subindo()
        del itens[3:9]  # 6 min sem leitura: o trecho atual fica curto
        r = previsao_sensor.prever(MODELO, itens, self.AGORA)
        self.assertEqual(r["motivo"], "historico_insuficiente")

    def test_perfil_desconhecido_ou_sem_data_usa_padrao(self):
        itens = subindo(perfil="inexistente")
        r = previsao_sensor.prever(MODELO, itens, self.AGORA)
        self.assertEqual(r["ultimaLeitura"]["perfil"], function_app.PERFIL_PADRAO)
        self.assertEqual(previsao_sensor._perfil_mais_recente([{"perfil": "uva"}]),
                         function_app.PERFIL_PADRAO)


class TestRotaPredictSensor(BaseRotas):
    def setUp(self):
        super().setUp()
        self.base = datetime.now(timezone.utc) - timedelta(seconds=20)
        self.containers["leituras"].itens += subindo(base=self.base)
        self.containers["leituras"].itens.append(
            leitura(0, 30.0, base=self.base, device="dev-b", empresa="E-B"))
        self.containers["usuarios"].itens += [
            {"id": "moto@a.com", "nome": "Moto", "perfil": "motorista", "veiculo": "CAM-01",
             "empresaId": "E-A", "sessao": 0, "senhaHash": "x"},
            {"id": "moto2@a.com", "nome": "Moto 2", "perfil": "motorista",
             "empresaId": "E-A", "sessao": 0, "senhaHash": "x"},
            {"id": "moto3@a.com", "nome": "Moto 3", "perfil": "motorista", "veiculo": "CAM-SEM",
             "empresaId": "E-A", "sessao": 0, "senhaHash": "x"},
            {"id": "moto4@a.com", "nome": "Moto 4", "perfil": "motorista", "veiculo": "CAM-B",
             "empresaId": "E-A", "sessao": 0, "senhaHash": "x"},
        ]
        self.containers["veiculos"].itens += [
            {"id": "E-A~CAM-SEM", "empresaId": "E-A", "tipo": "Van", "perfil": "manga"},
            # Cadastro quebrado: id da empresa A apontando para empresa B.
            {"id": "E-A~CAM-SEM-B", "empresaId": "E-B", "deviceId": "dev-b"},
        ]
        self.modelo = mock.patch.object(previsao_sensor, "_modelo", MODELO)
        self.modelo.start()

    def tearDown(self):
        self.modelo.stop()
        super().tearDown()

    def get(self, email=None, params=None):
        return self.chamar(PREDICT_SENSOR, "GET", "/api/predict/sensor", email=email,
                           params=params or {})

    def test_operador_com_device(self):
        with mock.patch.object(function_app, "consultar_leituras",
                               wraps=function_app.consultar_leituras) as consulta:
            status, corpo = self.get("operador@a.com", {"deviceId": "DEV-01"})
        self.assertEqual(status, 200)
        # A consulta ao banco vai pelo sensor e pela empresa do token.
        self.assertEqual(consulta.call_args.args[:2], ("dev-01", "E-A"))
        self.assertEqual(corpo["deviceId"], "dev-01")
        self.assertIsNone(corpo["motivo"])
        self.assertEqual(corpo["baseline"]["temperatura"], 12.4)
        self.assertEqual(corpo["previsao"]["temperatura"], 13.4)
        self.assertEqual(corpo["recomendada"], "modelo")
        self.assertTrue(corpo["antecipaExcursao"])

    def test_sem_device_400(self):
        status, corpo = self.get("gestor@a.com")
        self.assertEqual(status, 400)
        self.assertEqual(corpo["erros"], ["informe ?deviceId="])

    def test_sensor_de_outra_empresa_404(self):
        for device in ("dev-b", "nao-existe"):
            with self.subTest(device=device):
                status, corpo = self.get("gestor@a.com", {"deviceId": device})
                self.assertEqual(status, 404)
                self.assertEqual(corpo["erros"], ["dispositivo não encontrado"])
                self.assertNotIn("30.0", json.dumps(corpo))

    def test_motorista_usa_o_sensor_do_proprio_veiculo(self):
        # deviceId da URL é ignorado: o motorista não escolhe sensor.
        status, corpo = self.get("moto@a.com", {"deviceId": "dev-b"})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["deviceId"], "dev-01")

    def test_motorista_sem_veiculo_ou_sem_sensor_404(self):
        for email in ("moto2@a.com", "moto3@a.com", "moto4@a.com"):
            with self.subTest(email=email):
                status, corpo = self.get(email)
                self.assertEqual(status, 404)
                self.assertEqual(corpo["erros"],
                                 ["nenhum sensor vinculado a este motorista; fale com o gestor"])

    def test_motorista_com_veiculo_de_outra_empresa_404(self):
        self.containers["usuarios"].itens[-1]["veiculo"] = "CAM-SEM-B"
        status, _ = self.get("moto4@a.com")
        self.assertEqual(status, 404)

    def test_sensor_sem_leitura_recente(self):
        status, corpo = self.get("gestor@a.com", {"deviceId": "dev-livre"})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["motivo"], "sem_leituras")

    def test_sem_token_401(self):
        status, corpo = self.get(params={"deviceId": "dev-01"})
        self.assertEqual(status, 401)
        self.assertIn("faça login para continuar", corpo["erros"])

    def test_modelo_ausente_503(self):
        with mock.patch.object(previsao_sensor, "carregar",
                               side_effect=FileNotFoundError("nao-existe.json")):
            status, corpo = self.get("operador@a.com", {"deviceId": "dev-01"})
        self.assertEqual(status, 503)
        self.assertEqual(corpo["erros"], ["modelo indisponível"])
        self.assertNotIn("nao-existe", json.dumps(corpo))

    def test_limite_por_minuto_429(self):
        for _ in range(function_app.PREVISAO_SENSOR_POR_MINUTO):
            status, _ = self.get("operador@a.com", {"deviceId": "dev-01"})
            self.assertEqual(status, 200)
        status, corpo = self.get("operador@a.com", {"deviceId": "dev-01"})
        self.assertEqual(status, 429)


if __name__ == "__main__":
    unittest.main()
