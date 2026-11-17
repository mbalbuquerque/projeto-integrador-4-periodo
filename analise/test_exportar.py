"""Testes da exportação do modelo de risco térmico (exportar_modelo.py)."""

import json
import unittest

import pandas as pd

from exportar_modelo import VERSAO, montar, serializar


def leituras_sinteticas():
    """Seis anos sintéticos (2019 a 2024): tarde (12h a 16h) a 34 °C, resto a 22 °C."""
    registros = []
    for ano in (2019, 2020, 2021, 2022, 2023, 2024):
        for mes in range(1, 13):
            for hora in range(24):
                temp = 34.0 if 12 <= hora <= 16 else 22.0
                registros.append({"ano": ano, "mes": mes, "hora": hora, "temperatura_c": temp})
    return pd.DataFrame(registros)


class TestExportar(unittest.TestCase):
    def setUp(self):
        self.dados = montar(leituras_sinteticas())

    def test_tabela_12_por_24_com_probabilidades(self):
        prob = self.dados["probabilidade"]
        self.assertEqual((len(prob), {len(linha) for linha in prob}), (12, {24}))
        self.assertEqual(prob[0][14], 1.0)
        self.assertEqual(prob[0][3], 0.0)

    def test_horas_por_celula_contam_so_o_treino(self):
        # 4 anos de treino (2019 a 2022), uma hora por (ano, mês, hora).
        self.assertEqual({h for linha in self.dados["horasPorCelula"] for h in linha}, {4})

    def test_baseline_e_metricas_da_divisao_temporal(self):
        self.assertAlmostEqual(self.dados["baseline"], 5 / 24, places=4)
        self.assertEqual(self.dados["anosTreino"], [2019, 2020, 2021, 2022])
        self.assertEqual(self.dados["anosTeste"], [2023, 2024, 2025])
        m = self.dados["metricas"]
        self.assertLess(m["brierModelo"], m["brierBaseline"])
        self.assertEqual(self.dados["versao"], VERSAO)

    def test_celula_sem_treino_usa_o_baseline(self):
        df = leituras_sinteticas()
        df = df[~((df["mes"] == 2) & (df["hora"] == 5))]
        dados = montar(df)
        self.assertEqual(dados["probabilidade"][1][5], dados["baseline"])
        self.assertEqual(dados["horasPorCelula"][1][5], 0)

    def test_serializar_gera_json_valido_e_igual(self):
        texto = serializar(self.dados)
        self.assertEqual(json.loads(texto), json.loads(json.dumps(self.dados)))
        self.assertTrue(texto.endswith("}\n"))


if __name__ == "__main__":
    unittest.main()
