"""Testes unitários automatizados para o pipeline de limpeza climática (limpar.py)."""

import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from limpar import ler_estacao, numero

CSV_SINTETICO = """REGIAO:;NE
UF:;PE
ESTACAO:;PETROLINA
CODIGO (WMO):;A307
VL_LATITUDE:;-9.38
VL_LONGITUDE:;-40.52
VL_ALTITUDE:;376.0
DATA DE INICIO:;2026-01-01
Data;Hora UTC;Chuva;Pressao;Rad;RadGlobal;RadKj;Temp;TempMax;TempMin;UmidMax;UmidMin;PtoOrvalho;OrvalhoMax;OrvalhoMin;Umid;Vento;DirVento;Rajada
2026/01/01;0000 UTC;;;;;0,0;25,5;;;;;;;;65,0;;;
2026/01/01;0100 UTC;;;;;-9999;-9999;;;;;;;;-9999;;;
2026/01/01;0200 UTC;;;;;150,0;55,0;;;;;;;;105,0;;;
2026/01/01;0300 UTC;;;;;10,0;-10,0;;;;;;;;-5,0;;;
"""


class TestLimpar(unittest.TestCase):
    def test_numero(self):
        s = pd.Series(["25,5", "-9999", " -10000 ", "texto", " 10.2 "])
        res = numero(s)
        self.assertEqual(res.iloc[0], 25.5)
        self.assertTrue(pd.isna(res.iloc[1]))
        self.assertTrue(pd.isna(res.iloc[2]))
        self.assertTrue(pd.isna(res.iloc[3]))
        self.assertEqual(res.iloc[4], 10.2)

    def test_ler_estacao_com_csv(self):
        with tempfile.NamedTemporaryFile("w", encoding="latin-1", suffix=".csv", delete=False) as f:
            f.write(CSV_SINTETICO)
            caminho = Path(f.name)

        try:
            df = ler_estacao(caminho)
            self.assertEqual(len(df), 4)
            self.assertEqual(df["codigo"].iloc[0], "A307")
            self.assertEqual(df["estacao"].iloc[0], "Petrolina")

            # Linha 1: 25.5 °C e 65% válidos
            self.assertEqual(df["temperatura_c"].iloc[0], 25.5)
            self.assertEqual(df["umidade_pct"].iloc[0], 65.0)

            # Linha 2: -9999 descartado como NaN
            self.assertTrue(pd.isna(df["temperatura_c"].iloc[1]))
            self.assertTrue(pd.isna(df["umidade_pct"].iloc[1]))

            # Linha 3: 55°C e 105% fora da faixa aceitável (-5 a 50°C, 0 a 100%) viram NaN
            self.assertTrue(pd.isna(df["temperatura_c"].iloc[2]))
            self.assertTrue(pd.isna(df["umidade_pct"].iloc[2]))

            # Linha 4: -10°C e -5% fora da faixa viram NaN
            self.assertTrue(pd.isna(df["temperatura_c"].iloc[3]))
            self.assertTrue(pd.isna(df["umidade_pct"].iloc[3]))

            # Fuso horário: 00:00 UTC vira 21:00 do dia anterior (UTC-3)
            self.assertEqual(df["datahora"].iloc[0].hour, 21)
            self.assertEqual(df["datahora"].iloc[0].day, 31)
        finally:
            caminho.unlink()

    def test_main_sem_arquivos(self):
        from unittest import mock
        from limpar import main
        with mock.patch.object(Path, "glob", return_value=[]):
            with self.assertRaises(SystemExit):
                main()

    def test_main_com_arquivos(self):
        from unittest import mock
        import limpar

        with tempfile.TemporaryDirectory() as tmpdir:
            bruto_csv = Path(tmpdir) / "INMET_A307_2026.CSV"
            bruto_csv.write_text(CSV_SINTETICO, encoding="latin-1")
            saida_csv = limpar.AQUI / "dados" / "test_saida_temp.csv"

            fake_brutos = Path(tmpdir)
            try:
                with mock.patch("limpar.BRUTOS", fake_brutos), \
                     mock.patch("limpar.SAIDA", saida_csv):
                    limpar.main()
                    self.assertTrue(saida_csv.exists())
                    df = pd.read_csv(saida_csv)
                    self.assertFalse(df.empty)
            finally:
                if saida_csv.exists():
                    saida_csv.unlink()



if __name__ == "__main__":
    unittest.main()
