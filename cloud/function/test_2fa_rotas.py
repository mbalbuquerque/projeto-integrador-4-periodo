"""Rotas do 2FA (#113): login em dois passos, /login/2fa e /2fa/iniciar|ativar|desativar.

Rodar em cloud/function: python -m unittest test_2fa_rotas -v
Um teste para cada linha do critério de aceite da issue #113, mais os casos de borda.
"""

import logging
import os
from unittest import mock

import pyotp

import function_app
from seguranca import gerar_desafio_2fa, gerar_hash, ler_token
from test_acesso import SEGREDO, SENHA, BaseAcesso

LOGIN = function_app.login.build().get_user_function()
LOGIN_2FA = function_app.login_2fa.build().get_user_function()
INICIAR = function_app.totp_iniciar.build().get_user_function()
ATIVAR = function_app.totp_ativar.build().get_user_function()
DESATIVAR = function_app.totp_desativar.build().get_user_function()
EU = function_app.eu.build().get_user_function()
DISPOSITIVOS = function_app.dispositivos.build().get_user_function()

SEGREDO_TOTP = pyotp.random_base32()
RECUPERACAO = ["a1b2c3d4", "e5f6a7b8"]
# scrypt é caro: os hashes dos códigos de recuperação são feitos uma vez só.
HASHES = [gerar_hash(c) for c in RECUPERACAO]
MSG = function_app.MSG_2FA_RECUSADO
CODIGO_MISSAO = "TESTE1"


class Base2FA(BaseAcesso):
    def setUp(self):
        super().setUp()
        self.missao = mock.patch.dict(os.environ, {"MISSAO_CODIGO": CODIGO_MISSAO})
        self.missao.start()
        # ana@a.com com 2FA ligado; bia@a.com sem 2FA. _etag como no Cosmos de verdade.
        self.containers["usuarios"]._achar("ana@a.com").update({
            "totpAtivo": True, "totpSecret": SEGREDO_TOTP, "totpContadorUsado": -1,
            "recoveryCodes": list(HASHES), "_etag": "etag-0"})

    def tearDown(self):
        self.missao.stop()
        super().tearDown()

    def codigo(self, passos=0, segredo=SEGREDO_TOTP):
        """Código do app autenticador agora (ou `passos` de 30 s antes/depois)."""
        return pyotp.TOTP(segredo).at(self.agora + passos * 30)

    def entrar(self, email="ana@a.com", ip="200.1.2.3"):
        return self.chamar(LOGIN, "POST", "/api/login", {"email": email, "senha": SENHA},
                           headers={"X-Azure-ClientIP": ip})

    def segundo_passo(self, corpo, ip="200.1.2.3"):
        return self.chamar(LOGIN_2FA, "POST", "/api/login/2fa", corpo,
                           headers={"X-Azure-ClientIP": ip})

    def desafio(self):
        status, corpo = self.entrar()
        self.assertEqual(status, 200)
        return corpo["desafio"]

    def recusado(self, corpo, ip="200.1.2.3"):
        """401 com a mensagem de sempre e `2fa bloqueado [<código>]` no log."""
        logging.disable(logging.NOTSET)
        with self.assertLogs(level="WARNING") as logs:
            status, resposta = self.segundo_passo(corpo, ip)
        logging.disable(logging.WARNING)
        self.assertEqual((status, resposta), (401, {"erros": [MSG]}))
        self.assertTrue(any(f"2fa bloqueado [{CODIGO_MISSAO}]" in m for m in logs.output))


class TestLoginEmDoisPassos(Base2FA):
    def test_senha_certa_sem_codigo_devolve_so_o_desafio(self):
        status, corpo = self.entrar()
        self.assertEqual(status, 200)
        self.assertEqual(set(corpo), {"exige2fa", "desafio"})
        self.assertTrue(corpo["exige2fa"])

    def test_desafio_nao_serve_como_token_de_acesso(self):
        bearer = {"Authorization": "Bearer " + self.desafio()}
        self.assertEqual(self.chamar(EU, "GET", "/api/eu", headers=bearer)[0], 401)
        self.assertEqual(self.chamar(DISPOSITIVOS, "GET", "/api/dispositivos",
                                     headers=bearer)[0], 401)
        self.assertEqual(self.chamar(INICIAR, "POST", "/api/2fa/iniciar", {},
                                     headers=bearer)[0], 401)

    def test_codigo_valido_devolve_o_token(self):
        status, corpo = self.segundo_passo({"desafio": self.desafio(), "codigo": self.codigo()})
        self.assertEqual(status, 200)
        self.assertEqual(ler_token(corpo["token"], SEGREDO)["sub"], "ana@a.com")
        self.assertEqual(corpo["usuario"]["empresa"], "Frutas do Vale")
        self.assertTrue(corpo["usuario"]["totpAtivo"])
        bearer = {"Authorization": "Bearer " + corpo["token"]}
        self.assertEqual(self.chamar(EU, "GET", "/api/eu", headers=bearer)[0], 200)

    def test_codigo_do_passo_anterior_ainda_vale(self):  # valid_window=1 (±30 s)
        corpo = {"desafio": self.desafio(), "codigo": self.codigo(-1)}
        self.assertEqual(self.segundo_passo(corpo)[0], 200)

    def test_codigo_errado(self):
        errado = "000000" if self.codigo() != "000000" else "111111"
        self.recusado({"desafio": self.desafio(), "codigo": errado})

    def test_codigo_vencido(self):  # de 2 minutos atrás
        self.recusado({"desafio": self.desafio(), "codigo": self.codigo(-4)})

    def test_codigo_em_formato_invalido_ou_ausente(self):
        desafio = self.desafio()
        self.recusado({"desafio": desafio, "codigo": "12ab56"})
        self.recusado({"desafio": desafio})

    def test_mesmo_codigo_de_novo_e_recusado(self):
        codigo = self.codigo()
        self.assertEqual(self.segundo_passo({"desafio": self.desafio(), "codigo": codigo})[0],
                         200)
        self.recusado({"desafio": self.desafio(), "codigo": codigo})

    def test_codigo_de_recuperacao_entra_uma_vez_so(self):
        corpo = {"desafio": self.desafio(), "recuperacao": "A1B2C3D4"}
        status, resposta = self.segundo_passo(corpo)
        self.assertEqual(status, 200)
        self.assertIn("token", resposta)
        self.assertEqual(self.doc("ana@a.com")["recoveryCodes"], HASHES[1:])
        self.recusado({"desafio": self.desafio(), "recuperacao": "a1b2c3d4"})
        self.recusado({"desafio": self.desafio(), "recuperacao": "zzzzzzzz"})

    def test_usuario_sem_2fa_entra_como_antes(self):
        status, corpo = self.entrar("bia@a.com")
        self.assertEqual(status, 200)
        self.assertEqual(ler_token(corpo["token"], SEGREDO)["sub"], "bia@a.com")
        self.assertFalse(corpo["usuario"]["totpAtivo"])
        self.assertNotIn("exige2fa", corpo)


class TestDesafio(Base2FA):
    def test_desafio_ausente_e_401(self):
        self.recusado({"codigo": self.codigo()})
        self.recusado({"desafio": "", "codigo": self.codigo()})

    def test_desafio_vencido(self):
        doc = self.doc("ana@a.com")
        velho = gerar_desafio_2fa(doc, SEGREDO, agora=self.agora - 301)
        self.recusado({"desafio": velho, "codigo": self.codigo()})

    def test_desafio_adulterado_ou_token_comum(self):
        doc = self.doc("ana@a.com")
        falso = gerar_desafio_2fa(doc, "outro-segredo-com-tamanho-suficiente-hs256")
        self.recusado({"desafio": falso, "codigo": self.codigo()})
        _, corpo = self.entrar("bia@a.com")  # token de acesso no lugar do desafio
        self.recusado({"desafio": corpo["token"], "codigo": self.codigo()})

    def test_corpo_que_nao_e_objeto(self):
        self.recusado(["desafio", "codigo"])
        status, _ = self.chamar(LOGIN_2FA, "POST", "/api/login/2fa")
        self.assertEqual(status, 400)  # corpo vazio não é JSON

    def test_conta_removida_sem_2fa_ou_em_espera_depois_do_desafio(self):
        desafio = self.desafio()
        doc = self.containers["usuarios"]._achar("ana@a.com")
        doc["bloqueadoAte"] = int(self.agora + 600)
        self.recusado({"desafio": desafio, "codigo": self.codigo()})
        doc["bloqueadoAte"] = 0
        doc["totpAtivo"] = False
        self.recusado({"desafio": desafio, "codigo": self.codigo()})
        self.containers["usuarios"].itens.remove(doc)
        self.recusado({"desafio": desafio, "codigo": self.codigo()})

    def test_sucesso_zera_falhas_de_senha(self):
        desafio = self.desafio()
        self.containers["usuarios"]._achar("ana@a.com").update({"falhas": 3})
        self.assertEqual(self.segundo_passo({"desafio": desafio, "codigo": self.codigo()})[0],
                         200)
        self.assertEqual(self.doc("ana@a.com")["falhas"], 0)


class TestReusoAoMesmoTempo(Base2FA):
    def test_dois_logins_com_o_mesmo_codigo_so_um_entra(self):
        # Outro login grava o mesmo passo entre a leitura e a gravação deste (etag muda).
        usuarios = self.containers["usuarios"]

        def outro_login_no_meio(item_id):
            usuarios.antes_do_patch = None
            usuarios.patch_item(item_id, item_id, [
                {"op": "set", "path": "/totpContadorUsado", "value": 0}])

        usuarios.antes_do_patch = outro_login_no_meio
        self.recusado({"desafio": self.desafio(), "codigo": self.codigo()})

    def test_patch_sem_etag_continua_funcionando(self):
        self.containers["usuarios"]._achar("ana@a.com").pop("_etag")
        corpo = {"desafio": self.desafio(), "codigo": self.codigo()}
        self.assertEqual(self.segundo_passo(corpo)[0], 200)


class TestTentativasDemais(Base2FA):
    def test_429_por_conta_mesmo_trocando_de_ip(self):
        desafio = self.desafio()
        for i in range(function_app.LOGIN_2FA_FALHAS_POR_CONTA):
            self.recusado({"desafio": desafio, "codigo": "000000"}, ip=f"201.0.0.{i}")
        logging.disable(logging.NOTSET)
        with self.assertLogs(level="WARNING") as logs:
            status, corpo = self.segundo_passo({"desafio": desafio, "codigo": self.codigo()},
                                               ip="201.0.0.99")
        self.assertEqual((status, corpo), (429, {"erros": [function_app.MSG_2FA_ESPERA]}))
        self.assertTrue(any(f"2fa bloqueado [{CODIGO_MISSAO}]" in m for m in logs.output))

    def test_429_por_ip(self):
        for _ in range(function_app.LOGIN_2FA_FALHAS_POR_IP):
            self.recusado({"desafio": "lixo", "codigo": "000000"})
        status, _ = self.segundo_passo({"desafio": self.desafio(), "codigo": self.codigo()})
        self.assertEqual(status, 429)
        # Outro IP continua podendo terminar o login.
        corpo = {"desafio": self.desafio(), "codigo": self.codigo()}
        self.assertEqual(self.segundo_passo(corpo, ip="200.9.9.9")[0], 200)


class TestAtivarEDesativar(Base2FA):
    def test_eu_mostra_totp_ativo(self):
        self.assertFalse(self.chamar(EU, "GET", "/api/eu", email="bia@a.com")[1]["totpAtivo"])
        self.assertTrue(self.chamar(EU, "GET", "/api/eu", email="ana@a.com")[1]["totpAtivo"])

    def test_iniciar_e_ativar(self):
        status, corpo = self.chamar(INICIAR, "POST", "/api/2fa/iniciar", {}, email="bia@a.com")
        self.assertEqual(status, 200)
        self.assertTrue(corpo["uri"].startswith("otpauth://totp/ColdTrack:bia%40a.com?"))
        self.assertIn("issuer=ColdTrack", corpo["uri"])
        doc = self.doc("bia@a.com")
        self.assertFalse(doc.get("totpAtivo"))
        segredo = doc["totpSecretTemp"]
        self.assertIn(f"secret={segredo}", corpo["uri"])

        status, corpo = self.chamar(ATIVAR, "POST", "/api/2fa/ativar",
                                    {"codigo": self.codigo(segredo=segredo)}, email="bia@a.com")
        self.assertEqual(status, 200)
        self.assertEqual(len(corpo["recuperacao"]), 10)
        self.assertTrue(all(len(c) == 8 for c in corpo["recuperacao"]))
        doc = self.doc("bia@a.com")
        self.assertTrue(doc["totpAtivo"])
        self.assertEqual(doc["totpSecret"], segredo)
        self.assertNotIn("totpSecretTemp", doc)
        # No banco ficam só os hashes, nunca os códigos.
        self.assertEqual(len(doc["recoveryCodes"]), 10)
        self.assertFalse(set(doc["recoveryCodes"]) & set(corpo["recuperacao"]))
        # E o próximo login pede o código.
        self.assertTrue(self.entrar("bia@a.com")[1]["exige2fa"])

    def test_ativar_recusa_codigo_errado_ausente_ou_sem_iniciar(self):
        self.assertEqual(self.chamar(ATIVAR, "POST", "/api/2fa/ativar", {"codigo": "123456"},
                                     email="bia@a.com")[0], 400)  # sem iniciar
        self.chamar(INICIAR, "POST", "/api/2fa/iniciar", {}, email="bia@a.com")
        for corpo in ({"codigo": "000000"}, {}):
            status, resposta = self.chamar(ATIVAR, "POST", "/api/2fa/ativar", corpo,
                                           email="bia@a.com")
            self.assertEqual((status, resposta), (401, {"erros": [MSG]}))
        self.assertEqual(self.chamar(ATIVAR, "POST", "/api/2fa/ativar", email="bia@a.com")[0],
                         400)  # corpo que não é JSON
        self.assertFalse(self.doc("bia@a.com").get("totpAtivo"))

    def test_iniciar_com_2fa_ligado_nao_desliga_ate_ativar(self):
        status, _ = self.chamar(INICIAR, "POST", "/api/2fa/iniciar", {}, email="ana@a.com")
        self.assertEqual(status, 200)
        doc = self.doc("ana@a.com")
        novo = doc["totpSecretTemp"]
        self.assertTrue(doc["totpAtivo"])
        self.assertEqual(doc["totpSecret"], SEGREDO_TOTP)
        # O celular antigo continua entrando até o novo ser confirmado...
        corpo = {"desafio": self.desafio(), "codigo": self.codigo(-1)}
        self.assertEqual(self.segundo_passo(corpo)[0], 200)
        # ...e depois do ativar só o novo vale.
        status, _ = self.chamar(ATIVAR, "POST", "/api/2fa/ativar",
                                {"codigo": self.codigo(segredo=novo)}, email="ana@a.com")
        self.assertEqual(status, 200)
        self.assertEqual(self.doc("ana@a.com")["totpSecret"], novo)
        self.recusado({"desafio": self.desafio(), "codigo": self.codigo(1)})
        corpo = {"desafio": self.desafio(), "codigo": self.codigo(1, segredo=novo)}
        self.assertEqual(self.segundo_passo(corpo)[0], 200)

    def test_desativar_com_senha_e_codigo(self):
        corpo = {"senha": SENHA, "codigo": self.codigo()}
        status, _ = self.chamar(DESATIVAR, "POST", "/api/2fa/desativar", corpo,
                                email="ana@a.com")
        self.assertEqual(status, 204)
        doc = self.doc("ana@a.com")
        self.assertFalse(doc["totpAtivo"])
        self.assertIsNone(doc["totpSecret"])
        self.assertEqual(doc["recoveryCodes"], [])
        status, corpo = self.entrar()
        self.assertEqual(status, 200)
        self.assertIn("token", corpo)

    def test_desativar_com_codigo_de_recuperacao(self):
        corpo = {"senha": SENHA, "recuperacao": RECUPERACAO[1]}
        self.assertEqual(self.chamar(DESATIVAR, "POST", "/api/2fa/desativar", corpo,
                                     email="ana@a.com")[0], 204)

    def test_desativar_recusa(self):
        casos = [{"senha": "errada-123", "codigo": self.codigo()},
                 {"senha": SENHA, "codigo": "000000"},
                 {"senha": SENHA, "codigo": "zzzzzzzz"},
                 {"senha": SENHA}]
        for corpo in casos:
            status, resposta = self.chamar(DESATIVAR, "POST", "/api/2fa/desativar", corpo,
                                           email="ana@a.com")
            self.assertEqual((status, resposta), (401, {"erros": [MSG]}), corpo)
        self.assertTrue(self.doc("ana@a.com")["totpAtivo"])
        self.assertEqual(self.chamar(DESATIVAR, "POST", "/api/2fa/desativar",
                                     email="ana@a.com")[0], 400)  # corpo que não é JSON
        self.assertEqual(self.chamar(DESATIVAR, "POST", "/api/2fa/desativar", casos[0],
                                     email="bia@a.com")[0], 400)  # 2FA não está ligado

    def test_rotas_do_2fa_exigem_login(self):
        for rota, url in ((INICIAR, "iniciar"), (ATIVAR, "ativar"), (DESATIVAR, "desativar")):
            self.assertEqual(self.chamar(rota, "POST", f"/api/2fa/{url}", {})[0], 401)
