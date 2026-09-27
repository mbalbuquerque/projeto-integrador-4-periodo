"""Testes de senha, token e cadastros. Rodar: python -m unittest -v"""

import time
import unittest

import jwt

from cadastros import validar_usuario, validar_veiculo, validar_viagem
from seguranca import (conferir_senha, gerar_hash, gerar_token, ler_token,
                       token_do_cabecalho)

SEGREDO = "segredo-de-teste-com-tamanho-suficiente-32b"
USUARIO = {"id": "gestor@coldtrack.dev", "nome": "Gestor", "perfil": "gestor"}


class TestSenha(unittest.TestCase):
    def test_senha_certa(self):
        self.assertTrue(conferir_senha("senha-forte-1", gerar_hash("senha-forte-1")))

    def test_senha_errada(self):
        self.assertFalse(conferir_senha("senha-errada", gerar_hash("senha-forte-1")))

    def test_hash_nao_guarda_a_senha(self):
        self.assertNotIn("senha-forte-1", gerar_hash("senha-forte-1"))

    def test_mesma_senha_gera_hash_diferente(self):
        # Sal aleatório: dois usuários com a mesma senha não têm o mesmo hash.
        self.assertNotEqual(gerar_hash("igual-123"), gerar_hash("igual-123"))

    def test_hash_corrompido(self):
        self.assertFalse(conferir_senha("x", "lixo"))
        self.assertFalse(conferir_senha("x", None))


class TestToken(unittest.TestCase):
    def test_token_valido(self):
        dados = ler_token(gerar_token(USUARIO, SEGREDO), SEGREDO)
        self.assertEqual(dados["sub"], USUARIO["id"])
        self.assertEqual(dados["perfil"], "gestor")

    def test_outro_segredo(self):
        self.assertIsNone(ler_token(gerar_token(USUARIO, SEGREDO), "outro-segredo-qualquer-com-32-bytes"))

    def test_token_adulterado(self):
        token = gerar_token({**USUARIO, "perfil": "operador"}, SEGREDO)
        cabecalho, carga, assinatura = token.split(".")
        falso = jwt.encode({"sub": USUARIO["id"], "perfil": "gestor",
                            "exp": int(time.time()) + 60}, "chute", algorithm="HS256")
        self.assertIsNone(ler_token(falso, SEGREDO))
        self.assertIsNone(ler_token(f"{cabecalho}.{carga}x.{assinatura}", SEGREDO))

    def test_token_vencido(self):
        antigo = gerar_token(USUARIO, SEGREDO, agora=time.time() - 9 * 3600)
        self.assertIsNone(ler_token(antigo, SEGREDO))

    def test_algoritmo_none_rejeitado(self):
        sem_assinatura = jwt.encode({"sub": "x", "perfil": "gestor",
                                     "exp": int(time.time()) + 60}, None, algorithm="none")
        self.assertIsNone(ler_token(sem_assinatura, SEGREDO))

    def test_perfil_desconhecido(self):
        token = jwt.encode({"sub": "x", "perfil": "admin", "exp": int(time.time()) + 60},
                           SEGREDO, algorithm="HS256")
        self.assertIsNone(ler_token(token, SEGREDO))

    def test_cabecalho(self):
        self.assertEqual(token_do_cabecalho("Bearer abc"), "abc")
        self.assertIsNone(token_do_cabecalho("abc"))
        self.assertIsNone(token_do_cabecalho(None))
        self.assertIsNone(token_do_cabecalho("Bearer "))


class TestCadastros(unittest.TestCase):
    def test_usuario_valido(self):
        erros, doc = validar_usuario({"email": "Ana@Empresa.com", "nome": "Ana",
                                      "perfil": "operador", "senha": "12345678"})
        self.assertEqual(erros, [])
        self.assertEqual(doc["id"], "ana@empresa.com")

    def test_usuario_invalido(self):
        erros, _ = validar_usuario({"email": "sem-arroba", "nome": "",
                                    "perfil": "admin", "senha": "123"})
        self.assertEqual(len(erros), 4)

    def test_veiculo(self):
        erros, doc = validar_veiculo({"id": "ct-002", "tipo": "Baú", "deviceId": "coldtrack-02"})
        self.assertEqual(erros, [])
        self.assertEqual(doc["id"], "CT-002")
        self.assertEqual(doc["perfil"], "demonstrativo")
        self.assertTrue(validar_veiculo({"id": "a b", "tipo": "x", "deviceId": "ok-1",
                                         "perfil": "banana"})[0])

    def test_opcional_vazio_do_formulario(self):
        erros, doc = validar_veiculo({"id": "CT-003", "tipo": "Baú", "deviceId": "ct-03",
                                      "dispositivo": "", "perfil": "demonstrativo"})
        self.assertEqual(erros, [])
        self.assertEqual(doc["dispositivo"], "")
        erros, doc = validar_viagem({"veiculo": "CT-003", "origem": "A", "destino": "B",
                                     "carga": "c", "inicio": "2026-09-26T21:00:00Z", "fim": ""})
        self.assertEqual(erros, [])
        self.assertIsNone(doc["fim"])

    def test_viagem(self):
        base = {"veiculo": "ct-001", "origem": "Petrolina/PE", "destino": "Suape/PE",
                "carga": "Manga", "inicio": "2026-09-26T21:00:00Z"}
        erros, doc = validar_viagem(base)
        self.assertEqual(erros, [])
        self.assertIsNone(doc["fim"])
        self.assertTrue(validar_viagem({**base, "fim": "2026-09-26T20:00:00Z"})[0])
        self.assertTrue(validar_viagem({**base, "inicio": "2026-09-26T21:00:00"})[0])
        self.assertTrue(validar_viagem({**base, "inicio": "ontem"})[0])


if __name__ == "__main__":
    unittest.main()
