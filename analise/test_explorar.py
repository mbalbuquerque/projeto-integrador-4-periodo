"""Testes unitários automatizados para o modelo de risco térmico (explorar.py)."""

import unittest
import pandas as pd
from explorar import avaliar, probabilidade


class TestExplorar(unittest.TestCase):
    def setUp(self):
        # DataFrame sintético com 12 meses e 24 horas
        registros = []
        for ano in [2021, 2022, 2023, 2024]:
            for mes in range(1, 13):
                for hora in range(24):
                    # Madrugada fria (22°C), tarde quente (34°C)
                    temp = 34.0 if 12 <= hora <= 16 else 22.0
                    registros.append({
                        "ano": ano,
                        "mes": mes,
                        "hora": hora,
                        "temperatura_c": temp
                    })
        self.df = pd.DataFrame(registros)

    def test_probabilidade_calcula_tabela_12_por_24(self):
        tabela = probabilidade(self.df)
        self.assertEqual(tabela.shape, (12, 24))
        # Tarde (14h) deve ter 100% de probabilidade (> 30°C)
        self.assertEqual(tabela.loc[1, 14], 1.0)
        # Madrugada (4h) deve ter 0% de probabilidade
        self.assertEqual(tabela.loc[1, 4], 0.0)

    def test_avaliar_modelo_retorna_metricas(self):
        resultado = avaliar(self.df)
        self.assertIn("brier_modelo", resultado)
        self.assertIn("brier_ingenuo", resultado)
        self.assertIn("acerto_pct", resultado)
        self.assertIn("tabela", resultado)
        # O modelo ajustado à hora deve ter erro Brier menor que o ingênuo
        self.assertLessEqual(resultado["brier_modelo"], resultado["brier_ingenuo"])
        self.assertGreater(resultado["acerto_pct"], 90.0)


if __name__ == "__main__":
    unittest.main()

