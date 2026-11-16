"""Testes da rota GET /api/predict e do módulo predicao (modelo de risco térmico)."""

import json
import unittest
from unittest import mock

import function_app
import predicao
from test_rotas import BaseRotas

PREDICT = function_app.predict.build().get_user_function()


class TestModeloExportado(unittest.TestCase):
    """O modelo_risco.json publicado precisa ter a forma que a rota consulta."""

    def setUp(self):
        with open(predicao.ARQUIVO, encoding="utf-8") as f:
            self.modelo = json.load(f)

    def test_tabelas_12_por_24(self):
        for nome in ("probabilidade", "horasPorCelula"):
            tabela = self.modelo[nome]
            self.assertEqual(len(tabela), 12, nome)
            self.assertTrue(all(len(linha) == 24 for linha in tabela), nome)

    def test_probabilidades_entre_0_e_1(self):
        valores = [v for linha in self.modelo["probabilidade"] for v in linha]
        self.assertTrue(all(0.0 <= v <= 1.0 for v in valores))
        self.assertTrue(0.0 <= self.modelo["baseline"] <= 1.0)

    def test_modelo_melhor_que_baseline_com_divisao_temporal(self):
        m = self.modelo["metricas"]
        self.assertLess(m["brierModelo"], m["brierBaseline"])
        self.assertLess(max(self.modelo["anosTreino"]), min(self.modelo["anosTeste"]))

    def test_niveis_fecham_em_1(self):
        self.assertEqual(self.modelo["niveis"][-1]["ate"], 1.0)


class TestPredicao(unittest.TestCase):
    def test_validar_ok(self):
        self.assertEqual(predicao.validar({"mes": "10", "hora": "15"}), ([], 10, 15))
        self.assertEqual(predicao.validar({"mes": " 1 ", "hora": "0"}), ([], 1, 0))

    def test_validar_erros(self):
        casos = [
            ({}, ["mes: inteiro de 1 a 12", "hora: inteiro de 0 a 23"]),
            ({"mes": "13", "hora": "5"}, ["mes: inteiro de 1 a 12"]),
            ({"mes": "0", "hora": "24"}, ["mes: inteiro de 1 a 12", "hora: inteiro de 0 a 23"]),
            ({"mes": "abc", "hora": "-1"}, ["mes: inteiro de 1 a 12", "hora: inteiro de 0 a 23"]),
            ({"mes": "2.5", "hora": "3"}, ["mes: inteiro de 1 a 12"]),
        ]
        for params, esperado in casos:
            with self.subTest(params=params):
                erros, _, _ = predicao.validar(params)
                self.assertEqual(erros, esperado)

    def test_nivel_por_faixa(self):
        niveis = [{"nivel": "baixo", "ate": 0.2}, {"nivel": "moderado", "ate": 0.5},
                  {"nivel": "alto", "ate": 1.0}]
        self.assertEqual(predicao.nivel(0.0, niveis), "baixo")
        self.assertEqual(predicao.nivel(0.2, niveis), "baixo")
        self.assertEqual(predicao.nivel(0.35, niveis), "moderado")
        self.assertEqual(predicao.nivel(0.9, niveis), "alto")
        # Acima do último teto (não acontece com probabilidade válida) fica no nível mais alto.
        self.assertEqual(predicao.nivel(1.5, niveis), "alto")

    def test_carregar_le_uma_vez(self):
        with mock.patch.object(predicao, "_modelo", None):
            primeiro = predicao.carregar()
            with mock.patch("builtins.open", side_effect=AssertionError("leu de novo")):
                self.assertIs(predicao.carregar(), primeiro)


class TestRotaPredict(BaseRotas):
    def test_sucesso_operador(self):
        status, corpo = self.chamar(PREDICT, "GET", "/api/predict", email="operador@a.com",
                                    params={"mes": "10", "hora": "15"})
        self.assertEqual(status, 200)
        modelo = predicao.carregar()
        self.assertEqual(corpo["probabilidade"], modelo["probabilidade"][9][15])
        self.assertEqual((corpo["mes"], corpo["hora"], corpo["limiarC"]), (10, 15, 30.0))
        self.assertIn(corpo["nivel"], {"baixo", "moderado", "alto"})
        self.assertEqual(corpo["baseline"]["probabilidade"], modelo["baseline"])
        self.assertEqual(corpo["modelo"]["versao"], modelo["versao"])
        self.assertFalse(corpo["modelo"]["usaLeiturasDoSensor"])
        self.assertGreater(corpo["horasDeHistorico"], 0)

    def test_madrugada_baixo_e_tarde_de_outubro_alto(self):
        _, noite = self.chamar(PREDICT, "GET", "/api/predict", email="gestor@a.com",
                               params={"mes": "7", "hora": "3"})
        _, tarde = self.chamar(PREDICT, "GET", "/api/predict", email="gestor@a.com",
                               params={"mes": "10", "hora": "15"})
        self.assertEqual(noite["nivel"], "baixo")
        self.assertEqual(tarde["nivel"], "alto")

    def test_sem_token_401(self):
        status, corpo = self.chamar(PREDICT, "GET", "/api/predict",
                                    params={"mes": "10", "hora": "15"})
        self.assertEqual(status, 401)
        self.assertIn("faça login para continuar", corpo["erros"])

    def test_parametros_invalidos_400(self):
        status, corpo = self.chamar(PREDICT, "GET", "/api/predict", email="operador@a.com",
                                    params={"mes": "13"})
        self.assertEqual(status, 400)
        self.assertEqual(corpo["erros"], ["mes: inteiro de 1 a 12", "hora: inteiro de 0 a 23"])

    def test_modelo_ausente_503(self):
        sem_arquivo = FileNotFoundError("nao-existe.json")
        with mock.patch.object(predicao, "carregar", side_effect=sem_arquivo):
            status, corpo = self.chamar(PREDICT, "GET", "/api/predict", email="operador@a.com",
                                        params={"mes": "1", "hora": "1"})
        self.assertEqual(status, 503)
        self.assertEqual(corpo["erros"], ["modelo indisponível"])
        self.assertNotIn("nao-existe", json.dumps(corpo))


if __name__ == "__main__":
    unittest.main()
