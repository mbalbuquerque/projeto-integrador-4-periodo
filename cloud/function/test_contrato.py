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


class TestMedidoEm(unittest.TestCase):
    AGORA = 1_790_000_000

    def validar(self, medido):
        return validar({**VALIDO, "medidoEm": medido}, agora=self.AGORA)

    def test_ausente_continua_valido(self):
        self.assertEqual(validar(VALIDO, agora=self.AGORA), [])

    def test_leitura_guardada_de_horas_atras(self):
        self.assertEqual(self.validar(self.AGORA - 3 * 3600), [])

    def test_futuro_rejeitado(self):
        self.assertTrue(self.validar(self.AGORA + 3600))

    def test_mais_de_7_dias_rejeitado(self):
        self.assertTrue(self.validar(self.AGORA - 8 * 24 * 3600))

    def test_relogio_nao_sincronizado_rejeitado(self):
        # ESP32 sem NTP começa em 1970: epoch pequeno não pode entrar.
        self.assertTrue(self.validar(120))

    def test_texto_rejeitado(self):
        self.assertTrue(self.validar("2026-09-26"))


class TestClassificar(unittest.TestCase):
    def test_faixas(self):
        self.assertEqual(classificar(15.0), "NORMAL")
        self.assertEqual(classificar(15.1), "ATENCAO")
        self.assertEqual(classificar(20.0), "ATENCAO")
        self.assertEqual(classificar(20.1), "CRITICO")


if __name__ == "__main__":
    unittest.main()
