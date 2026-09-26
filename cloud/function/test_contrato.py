"""Testes de contrato do payload de telemetria. Rodar: python -m unittest -v"""

import unittest

from contrato import classificar, validar

VALIDO = {"deviceId": "coldtrack-01", "temperatura": 12.4, "umidade": 81.0, "rssi": -58}


class TestValidar(unittest.TestCase):
    def test_payload_valido(self):
        self.assertEqual(validar(VALIDO), [])

    def test_corpo_nao_objeto(self):
        self.assertTrue(validar([1, 2]))

    def test_campo_faltando(self):
        dados = dict(VALIDO)
        del dados["umidade"]
        self.assertIn("umidade: obrigatório e numérico", validar(dados))

    def test_nan_rejeitado(self):
        # Fail-fast: leitura isnan do sensor nunca pode chegar ao banco.
        self.assertTrue(validar({**VALIDO, "temperatura": float("nan")}))

    def test_fora_da_faixa(self):
        self.assertTrue(validar({**VALIDO, "umidade": 120}))
        self.assertTrue(validar({**VALIDO, "temperatura": -100}))

    def test_texto_no_lugar_de_numero(self):
        self.assertTrue(validar({**VALIDO, "temperatura": "12"}))

    def test_rssi_nulo_aceito(self):
        self.assertEqual(validar({**VALIDO, "rssi": None}), [])

    def test_rssi_ausente_rejeitado(self):
        dados = dict(VALIDO)
        del dados["rssi"]
        self.assertTrue(validar(dados))

    def test_rssi_positivo_rejeitado(self):
        self.assertTrue(validar({**VALIDO, "rssi": 35}))

    def test_temperatura_nula_rejeitada(self):
        self.assertTrue(validar({**VALIDO, "temperatura": None}))

    def test_booleano_nao_e_numero(self):
        self.assertTrue(validar({**VALIDO, "rssi": True}))

    def test_device_id_invalido(self):
        self.assertTrue(validar({**VALIDO, "deviceId": "a b"}))
        self.assertTrue(validar({**VALIDO, "deviceId": ""}))

    def test_campo_extra(self):
        self.assertTrue(validar({**VALIDO, "senha": "x"}))


class TestClassificar(unittest.TestCase):
    def test_faixas(self):
        self.assertEqual(classificar(15.0), "NORMAL")
        self.assertEqual(classificar(15.1), "ATENCAO")
        self.assertEqual(classificar(20.0), "ATENCAO")
        self.assertEqual(classificar(20.1), "CRITICO")


if __name__ == "__main__":
    unittest.main()
