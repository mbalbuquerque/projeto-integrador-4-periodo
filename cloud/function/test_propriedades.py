"""Testes de propriedades (Hypothesis) e controle temporal (time-machine).

Demonstra testes avançados sem mocks manuais de sistema:
- Fuzzing de payload com Hypothesis garantindo que o contrato nunca quebra.
- Viagem no tempo com time-machine para expiração de tokens e janelas de espera.
"""

from datetime import datetime, timedelta, timezone

import time_machine
from hypothesis import given
from hypothesis import strategies as st

import contrato
import seguranca

SEGREDO = "segredo-de-teste-com-tamanho-suficiente-para-hs256"


# ------------------------------------------------------------ Hypothesis (Property-Based)

class TestPropriedadesContrato:
    @given(
        temp=st.floats(allow_nan=True, allow_infinity=True),
        perfil=st.sampled_from(["manga", "uva", "demonstrativo", "outro_qualquer"])
    )
    def test_classificar_sempre_devolve_status_valido(self, temp, perfil):
        """Para qualquer float ou valor especial (NaN/Inf), o status é previsível."""
        status = contrato.classificar(temp, perfil)
        assert status in ("NORMAL", "ATENCAO", "CRITICO")

    @given(
        device_id=st.text(min_size=1, max_size=50),
        temp=st.floats(min_value=-40.0, max_value=85.0),
        umid=st.floats(min_value=0.0, max_value=100.0),
        rssi=st.integers(min_value=-140, max_value=0)
    )
    def test_payload_fuzzing_nunca_lanca_excecao(self, device_id, temp, umid, rssi):
        """Garante robustez total: validar() nunca dispara exceção não tratada."""
        payload = {
            "deviceId": device_id,
            "temperatura": temp,
            "umidade": umid,
            "rssi": rssi
        }
        erros = contrato.validar(payload)
        assert isinstance(erros, list)

    @given(
        texto=st.text(max_size=200)
    )
    def test_mascarar_email_invariante(self, texto):
        """A máscara nunca quebra e nunca expõe o e-mail completo se for válido."""
        mascarado = seguranca.mascarar_email(texto)
        assert isinstance(mascarado, str)
        if "@" in texto and "." in texto.split("@")[-1]:
            assert "***" in mascarado or texto == ""


# ------------------------------------------------------------ time-machine (Temporal)

class TestControleTemporal:
    def test_expiracao_de_token_com_viagem_no_tempo(self):
        usuario = {"id": "ana@a.com", "nome": "Ana", "perfil": "gestor",
                   "empresaId": "E-A", "sessao": 0}

        # Congela o tempo em um instante exato
        with time_machine.travel("2026-06-01 12:00:00 +0000", tick=False) as traveller:
            token = seguranca.gerar_token(usuario, SEGREDO)

            # Dentro do prazo (7 horas depois), o token é válido
            traveller.shift(timedelta(hours=7))
            carga = seguranca.ler_token(token, SEGREDO)
            assert carga is not None
            assert carga["sub"] == "ana@a.com"

            # 8 horas e 1 segundo depois: expirado automaticamente
            traveller.shift(timedelta(hours=1, seconds=1))
            assert seguranca.ler_token(token, SEGREDO) is None

    def test_janela_de_leitura_com_viagem_no_tempo(self):
        # Medição realizada em 2026-06-01
        with time_machine.travel("2026-06-01 10:00:00 +0000", tick=False) as traveller:
            medido_em = int(datetime.now(timezone.utc).timestamp())
            payload = {"deviceId": "dev-01", "temperatura": 12.0, "umidade": 80.0,
                       "rssi": -60, "medidoEm": medido_em}

            # 6 dias depois: ainda aceita
            traveller.shift(timedelta(days=6))
            erros = contrato.validar(payload)
            assert erros == []

            # 7 dias e 1 hora depois: mais de 7 dias rejeitado
            traveller.shift(timedelta(days=1, hours=1))
            erros_tarde = contrato.validar(payload)
            assert any("mais antigo que 7 dias" in e for e in erros_tarde)
