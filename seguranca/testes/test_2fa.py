#!/usr/bin/env python3
"""Testes de 2FA (TOTP + Recovery Codes) — roda com: python -m unittest seguranca_mod.testes.test_2fa"""

import os
import sys
import time
import unittest
from unittest import mock

# Adiciona o diretório cloud/function ao path (onde está seguranca_mod.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'cloud', 'function'))

# Importa o módulo seguranca do cloud/function
import seguranca as seguranca_mod


class TestTOTP(unittest.TestCase):
    def setUp(self):
        self.segredo = seguranca_mod.gerar_totp_secret()
        self.contador_inicial = -1

    def test_gerar_totp_secret_formato_base32(self):
        self.assertEqual(len(self.segredo), 32)  # base32 de 160 bits = 32 chars
        # Só caracteres válidos base32
        self.assertTrue(all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in self.segredo))

    def test_totp_uri_contem_segredo_e_emissor(self):
        uri = seguranca_mod.totp_uri(self.segredo, "teste@coldtrack.dev")
        self.assertIn("otpauth://totp/", uri)
        self.assertIn("secret=", uri)
        self.assertIn("issuer=ColdTrack", uri)
        self.assertIn("teste%40coldtrack.dev", uri)  # email URL-encoded

    def test_verificar_totp_codigo_valido(self):
        totp = __import__('pyotp').TOTP(self.segredo)
        # Usa tempo fixo para evitar flakiness
        agora = 1_700_000_000
        contador = totp.timecode(agora)
        codigo = totp.at(contador)

        # Mock time.time to return our fixed time
        with mock.patch('time.time', return_value=agora):
            valido, novo = seguranca_mod.verificar_totp(self.segredo, codigo, self.contador_inicial)
        self.assertTrue(valido)
        # pyotp timecode can vary by 1 depending on exact timing; accept ±1
        self.assertIn(novo, (contador - 1, contador, contador + 1))

    def test_verificar_totp_replay_bloqueado(self):
        totp = __import__('pyotp').TOTP(self.segredo)
        agora = int(time.time())
        contador = totp.timecode(agora)
        codigo = totp.at(contador)

        # Primeira vez: passa
        valido, novo = seguranca_mod.verificar_totp(self.segredo, codigo, self.contador_inicial)
        self.assertTrue(valido)

        # Segunda vez com mesmo contador: falha (replay)
        valido2, novo2 = seguranca_mod.verificar_totp(self.segredo, codigo, novo)
        self.assertFalse(valido2)
        self.assertEqual(novo2, novo)  # contador não muda

    def test_verificar_totp_codigo_errado(self):
        self.assertFalse(seguranca_mod.verificar_totp(self.segredo, "000000", self.contador_inicial)[0])

    def test_verificar_totp_formato_invalido(self):
        self.assertFalse(seguranca_mod.verificar_totp(self.segredo, "abc", self.contador_inicial)[0])
        self.assertFalse(seguranca_mod.verificar_totp(self.segredo, "12345", self.contador_inicial)[0])
        self.assertFalse(seguranca_mod.verificar_totp(self.segredo, "1234567", self.contador_inicial)[0])

    def test_verificar_totp_janela_adjacente(self):
        totp = __import__('pyotp').TOTP(self.segredo)
        agora = int(time.time())
        contador = totp.timecode(agora)
        # Código do passo anterior (contador - 1)
        codigo_anterior = totp.at(contador - 1)
        valido, novo = seguranca_mod.verificar_totp(self.segredo, codigo_anterior, self.contador_inicial, janela=1)
        self.assertTrue(valido)
        self.assertEqual(novo, contador - 1)


class TestRecoveryCodes(unittest.TestCase):
    def test_gerar_recovery_codes_qtd_e_formato(self):
        codigos = seguranca_mod.gerar_recovery_codes(qtd=10, tam=8)
        self.assertEqual(len(codigos), 10)
        for c in codigos:
            self.assertEqual(len(c), 8)
            self.assertTrue(all(ch in "abcdefghijklmnopqrstuvwxyz0123456789" for ch in c))

    def test_hash_recovery_codes_todos_diferentes(self):
        codigos = ["a1b2c3d4", "e5f6g7h8", "i9j0k1l2"]
        hashes = seguranca_mod.hash_recovery_codes(codigos)
        self.assertEqual(len(hashes), 3)
        self.assertEqual(len(set(hashes)), 3)  # todos únicos (sal aleatório)

    def test_verificar_recovery_code_sucesso_e_invalida(self):
        codigos = ["a1b2c3d4", "e5f6g7h8"]
        hashes = seguranca_mod.hash_recovery_codes(codigos)

        # Primeiro código: válido
        valido, restantes = seguranca_mod.verificar_recovery_code("a1b2c3d4", hashes)
        self.assertTrue(valido)
        self.assertEqual(len(restantes), 1)

        # Mesmo código de novo: inválido (já removido)
        valido2, restantes2 = seguranca_mod.verificar_recovery_code("a1b2c3d4", restantes)
        self.assertFalse(valido2)
        self.assertEqual(len(restantes2), 1)

        # Segundo código: válido
        valido3, restantes3 = seguranca_mod.verificar_recovery_code("e5f6g7h8", restantes)
        self.assertTrue(valido3)
        self.assertEqual(len(restantes3), 0)

    def test_verificar_recovery_code_case_insensitive(self):
        codigos = ["A1B2C3D4"]
        hashes = seguranca_mod.hash_recovery_codes(codigos)
        valido, _ = seguranca_mod.verificar_recovery_code("a1b2c3d4", hashes)
        self.assertTrue(valido)

    def test_verificar_recovery_code_inexistente(self):
        hashes = seguranca_mod.hash_recovery_codes(["a1b2c3d4"])
        valido, restantes = seguranca_mod.verificar_recovery_code("zzzzzzzz", hashes)
        self.assertFalse(valido)
        self.assertEqual(len(restantes), 1)


class TestDesafio2FA(unittest.TestCase):
    def test_gerar_e_ler_desafio_2fa(self):
        usuario = {"id": "teste@coldtrack.dev", "empresaId": "E-TESTE"}
        segredo_jwt = "segredo-de-teste-com-tamanho-suficiente-32b"
        desafio = seguranca_mod.gerar_desafio_2fa(usuario, segredo_jwt)
        email = seguranca_mod.ler_desafio_2fa(desafio, segredo_jwt)
        self.assertEqual(email, "teste@coldtrack.dev")

    def test_desafio_2fa_expira(self):
        usuario = {"id": "teste@coldtrack.dev", "empresaId": "E-TESTE"}
        segredo_jwt = "segredo-de-teste-com-tamanho-suficiente-32b"
        # Gera desafio no passado (6 min atrás)
        desafio = seguranca_mod.gerar_desafio_2fa(usuario, segredo_jwt, agora=int(time.time()) - 360)
        email = seguranca_mod.ler_desafio_2fa(desafio, segredo_jwt)
        self.assertIsNone(email)


class TestLog2FA(unittest.TestCase):
    @mock.patch.dict(os.environ, {"MISSAO_CODIGO": "ABC123"})
    @mock.patch("logging.warning")
    def test_log_2fa_bloqueado_formato(self, mock_warning):
        seguranca_mod.log_2fa_bloqueado("totp_invalido", "usuario@teste.com")
        mock_warning.assert_called_once()
        # logging.warning is called with format string and args separately
        args, kwargs = mock_warning.call_args
        format_string = args[0]
        format_args = args[1:]
        self.assertEqual(format_string, "2fa bloqueado [%s] - %s - %s")
        self.assertEqual(format_args[0], "ABC123")
        self.assertEqual(format_args[1], "totp_invalido")
        self.assertEqual(format_args[2], "u***@teste.com")


if __name__ == "__main__":
    unittest.main()