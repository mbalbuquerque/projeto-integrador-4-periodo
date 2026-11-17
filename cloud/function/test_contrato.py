"""Testes de contrato do payload de telemetria. Rodar: python -m unittest -v"""

import unittest

from contrato import (
    classificar,
    faixa,
    filtros_de_leitura,
    id_leitura,
    lacunas_de_sequencia,
    mesma_leitura,
    validar,
)

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


class TestOrigem(unittest.TestCase):
    def test_ausente_continua_valido(self):
        self.assertEqual(validar(VALIDO), [])

    def test_valida(self):
        for valor in ("placa", "simulador"):
            self.assertEqual(validar({**VALIDO, "origem": valor}), [])

    def test_invalida(self):
        for valor in ("real", "Placa", "", None, 1, True):
            with self.subTest(origem=valor):
                self.assertIn("origem: use placa ou simulador",
                              validar({**VALIDO, "origem": valor}))


class TestSeq(unittest.TestCase):
    def test_ausente_continua_valido(self):
        # Placa com firmware antigo não manda seq.
        self.assertEqual(validar(VALIDO), [])

    def test_valido(self):
        self.assertEqual(validar({**VALIDO, "seq": 1}), [])
        self.assertEqual(validar({**VALIDO, "seq": 2**32 - 1}), [])

    def test_invalido(self):
        for valor in (0, -1, 2**32, 1.5, "7", True, None):
            with self.subTest(seq=valor):
                self.assertIn("seq: inteiro de 1 a 4294967295", validar({**VALIDO, "seq": valor}))


class TestLacunas(unittest.TestCase):
    @staticmethod
    def leitura(seq, minuto):
        item = {"medidoEm": f"2026-11-16T12:{minuto:02d}:00+00:00"}
        if seq is not None:
            item["seq"] = seq
        return item

    def test_sem_lacuna(self):
        itens = [self.leitura(s, s) for s in (12, 11, 10)]
        self.assertEqual(lacunas_de_sequencia(itens), [])

    def test_lacuna_no_meio(self):
        # Ordem da consulta: da mais nova para a mais antiga.
        itens = [self.leitura(15, 9), self.leitura(14, 8), self.leitura(11, 5), self.leitura(10, 4)]
        self.assertEqual(lacunas_de_sequencia(itens), [{"de": 12, "ate": 13, "faltam": 2}])

    def test_contador_zerado_nao_e_lacuna(self):
        itens = [self.leitura(40, 1), self.leitura(41, 2), self.leitura(1, 3), self.leitura(3, 4)]
        self.assertEqual(lacunas_de_sequencia(itens), [{"de": 2, "ate": 2, "faltam": 1}])

    def test_fora_de_ordem_nao_e_lacuna(self):
        # Caso real (coldtrack-0e0b2c, 17/11 03:30): a 266 saiu com o relógio
        # adiantado depois de um reinício e ficou com horário depois da 270.
        itens = [self.leitura(264, 28), self.leitura(265, 30), self.leitura(266, 32),
                 self.leitura(267, 31), self.leitura(268, 31), self.leitura(269, 31),
                 self.leitura(270, 32), self.leitura(271, 33)]
        itens[2]["medidoEm"] = "2026-11-16T12:32:24+00:00"
        itens[5]["medidoEm"] = "2026-11-16T12:31:57+00:00"
        itens[6]["medidoEm"] = "2026-11-16T12:32:17+00:00"
        self.assertEqual(lacunas_de_sequencia(itens), [])

    def test_fora_de_ordem_com_falta_de_verdade(self):
        itens = [self.leitura(10, 1), self.leitura(13, 2), self.leitura(11, 3),
                 self.leitura(15, 4)]
        self.assertEqual(lacunas_de_sequencia(itens), [{"de": 12, "ate": 12, "faltam": 1},
                                                       {"de": 14, "ate": 14, "faltam": 1}])

    def test_primeira_da_janela_fora_de_ordem(self):
        # A janela começa numa leitura atrasada: a 10 depois da 11 não é contador zerado
        # a ponto de dar a 11 (que está na resposta) como faltando.
        itens = [self.leitura(11, 1), self.leitura(10, 2), self.leitura(12, 3)]
        self.assertEqual(lacunas_de_sequencia(itens), [])

    def test_contador_zerado_com_numeros_repetidos(self):
        # Contagem nova reaproveita números da antiga: falta só o que ninguém trouxe.
        itens = [self.leitura(4, 1), self.leitura(5, 2), self.leitura(6, 3),
                 self.leitura(1, 4), self.leitura(5, 5), self.leitura(8, 6)]
        self.assertEqual(lacunas_de_sequencia(itens), [{"de": 2, "ate": 3, "faltam": 2},
                                                       {"de": 7, "ate": 7, "faltam": 1}])

    def test_salto_grande_nao_materializa(self):
        itens = [self.leitura(1, 1), self.leitura(2_000_000_000, 2)]
        self.assertEqual(lacunas_de_sequencia(itens),
                         [{"de": 2, "ate": 1_999_999_999, "faltam": 1_999_999_998}])

    def test_leitura_sem_seq_ignorada(self):
        itens = [self.leitura(None, 1), self.leitura(5, 2),
                 self.leitura(None, 3), self.leitura(6, 4)]
        self.assertEqual(lacunas_de_sequencia(itens), [])
        self.assertEqual(lacunas_de_sequencia([]), [])


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


class TestFiltros(unittest.TestCase):
    AGORA = 1_790_000_000

    def filtros(self, **params):
        return filtros_de_leitura(params, agora=self.AGORA)

    def test_sem_filtros(self):
        self.assertEqual(self.filtros(), ([], {"desde": None, "status": None}))

    def test_horas(self):
        erros, f = self.filtros(horas="24")
        self.assertEqual(erros, [])
        self.assertEqual(f["desde"], self.AGORA - 24 * 3600)

    def test_horas_invalidas(self):
        for valor in ("0", "169", "abc", "-5"):
            self.assertTrue(self.filtros(horas=valor)[0], valor)

    def test_status(self):
        erros, f = self.filtros(status="atencao, CRITICO")
        self.assertEqual(erros, [])
        self.assertEqual(f["status"], ["ATENCAO", "CRITICO"])

    def test_status_invalido(self):
        self.assertTrue(self.filtros(status="QUENTE")[0])
        self.assertTrue(self.filtros(status=",")[0])


class TestClassificar(unittest.TestCase):
    def test_faixas(self):
        self.assertEqual(classificar(15.0), "NORMAL")
        self.assertEqual(classificar(15.1), "ATENCAO")
        self.assertEqual(classificar(20.0), "ATENCAO")
        self.assertEqual(classificar(20.1), "CRITICO")
        self.assertEqual(classificar(-30.0), "NORMAL")  # demonstrativo não tem mínimo

    def test_perfil_manga(self):
        self.assertEqual(classificar(11.0, "manga"), "NORMAL")
        self.assertEqual(classificar(8.0, "manga"), "ATENCAO")   # frio demais: dano por frio
        self.assertEqual(classificar(15.5, "manga"), "ATENCAO")
        self.assertEqual(classificar(6.9, "manga"), "CRITICO")
        self.assertEqual(classificar(16.1, "manga"), "CRITICO")

    def test_perfil_uva(self):
        self.assertEqual(classificar(0.0, "uva"), "NORMAL")
        self.assertEqual(classificar(2.0, "uva"), "ATENCAO")
        self.assertEqual(classificar(2.5, "uva"), "CRITICO")

    def test_perfil_desconhecido_usa_padrao(self):
        self.assertEqual(faixa("banana"), faixa("demonstrativo"))


class TestLeituraDuplicada(unittest.TestCase):
    def test_id_deterministico_com_horario(self):
        self.assertEqual(id_leitura("coldtrack-0e0b2c", 1790000000), "coldtrack-0e0b2c~1790000000")
        self.assertEqual(id_leitura("coldtrack-0e0b2c", 1790000000.0),
                         "coldtrack-0e0b2c~1790000000")

    def test_sem_horario_nao_tem_id(self):
        self.assertIsNone(id_leitura("coldtrack-0e0b2c", None))

    def test_reenvio_igual(self):
        gravada = {"temperatura": 30.2, "umidade": 66.0, "rssi": -48}
        self.assertTrue(mesma_leitura(gravada, {"temperatura": 30.2, "umidade": 66.0, "rssi": -48}))
        self.assertTrue(mesma_leitura({**gravada, "rssi": None}, {**gravada, "rssi": None}))

    def test_valores_diferentes_nao_sao_reenvio(self):
        gravada = {"temperatura": 30.2, "umidade": 66.0, "rssi": -48}
        self.assertFalse(mesma_leitura(gravada, {**gravada, "temperatura": 12.0}))
        self.assertFalse(mesma_leitura(gravada, {**gravada, "umidade": 70.0}))
        self.assertFalse(mesma_leitura(gravada, {**gravada, "rssi": -60}))

    def test_seq_diferente_nao_e_reenvio(self):
        gravada = {"temperatura": 30.2, "umidade": 66.0, "rssi": -48, "seq": 7}
        self.assertTrue(mesma_leitura(gravada, dict(gravada)))
        self.assertFalse(mesma_leitura(gravada, {**gravada, "seq": 8}))


if __name__ == "__main__":
    unittest.main()
