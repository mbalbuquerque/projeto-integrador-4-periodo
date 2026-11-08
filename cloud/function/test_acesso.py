"""Testes de login, sessão e permissões nas rotas (Cosmos falso). Rodar: python -m unittest -v"""

import json
import logging
import os
import time
import unittest
from unittest import mock

import azure.functions as func

import function_app
from seguranca import gerar_hash, gerar_token, ler_token
from test_falsos import ContainerFalso

SEGREDO = "segredo-de-teste-com-tamanho-suficiente-para-hs256"
SENHA = "senha-certa-123"
HASH = gerar_hash(SENHA)  # scrypt é caro: um hash só para todos os testes
MSG = function_app.MSG_LOGIN_RECUSADO

LOGIN = function_app.login.build().get_user_function()
EU = function_app.eu.build().get_user_function()
SAIR = function_app.sair.build().get_user_function()
SENHA_ROTA = function_app.senha.build().get_user_function()
USUARIOS = function_app.usuarios.build().get_user_function()


def usuario(email, perfil="gestor", empresa="E-A", **extra):
    return {"id": email, "nome": email.split("@")[0].title(), "perfil": perfil,
            "empresaId": empresa, "sessao": 0, "senhaHash": HASH, **extra}


class BaseAcesso(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"JWT_SECRET": SEGREDO})
        self.env.start()
        self.containers = {
            "usuarios": ContainerFalso([usuario("ana@a.com"), usuario("bia@a.com", "operador"),
                                        usuario("caio@b.com", empresa="E-B")]),
            "empresas": ContainerFalso([{"id": "E-A", "nome": "Frutas do Vale"},
                                        {"id": "E-B", "nome": "Outra"}]),
            "limites": ContainerFalso([]),
        }
        self.cosmos = mock.patch.object(function_app, "container",
                                        lambda nome=None: self.containers[nome])
        self.cosmos.start()
        function_app.LIMITES.reiniciar()
        self.agora = time.time()
        self.relogio = mock.patch("time.time", lambda: self.agora)
        self.relogio.start()
        # scrypt de verdade fica em test_seguranca; aqui a conferência é instantânea.
        self.senha = mock.patch.object(function_app, "conferir_senha",
                                       lambda s, h: h == HASH and s == SENHA)
        self.senha.start()
        logging.disable(logging.WARNING)  # sem poluir a saída; quem testa log liga de novo

    def tearDown(self):
        logging.disable(logging.NOTSET)
        self.senha.stop()
        self.relogio.stop()
        self.cosmos.stop()
        self.env.stop()
        function_app.LIMITES.reiniciar()

    def doc(self, email):
        return self.containers["usuarios"].read_item(email, partition_key=email)

    def chamar(self, rota, metodo, url, corpo=None, email=None, headers=None, **rota_params):
        h = {"Content-Type": "application/json", **(headers or {})}
        if email:
            h["Authorization"] = "Bearer " + gerar_token(self.doc(email), SEGREDO)
        dados = json.dumps(corpo).encode() if corpo is not None else b""
        r = rota(func.HttpRequest(method=metodo, url=url, body=dados, headers=h,
                                  route_params=rota_params))
        return r.status_code, json.loads(r.get_body() or b"null")


class TestLogin(BaseAcesso):
    def entrar(self, email, senha, ip="200.1.2.3"):
        return self.chamar(LOGIN, "POST", "/api/login", {"email": email, "senha": senha},
                           headers={"X-Azure-ClientIP": ip})

    def test_sucesso(self):
        status, corpo = self.entrar("Ana@A.com", SENHA)
        self.assertEqual(status, 200)
        self.assertEqual(ler_token(corpo["token"], SEGREDO)["sub"], "ana@a.com")
        self.assertEqual(corpo["usuario"]["empresa"], "Frutas do Vale")

    def test_mesma_resposta_para_inexistente_errada_e_espera(self):
        inexistente = self.entrar("ninguem@a.com", SENHA)
        errada = self.entrar("ana@a.com", "errada-123")
        for _ in range(4):
            self.entrar("ana@a.com", "errada-123")
        self.assertGreater(self.doc("ana@a.com")["bloqueadoAte"], self.agora)
        em_espera = self.entrar("ana@a.com", SENHA)  # senha certa durante a espera
        self.assertEqual(inexistente, (401, {"erros": [MSG]}))
        self.assertEqual(errada, inexistente)
        self.assertEqual(em_espera, inexistente)

    def test_espera_cresce_e_libera_com_a_senha_certa(self):
        for _ in range(5):
            self.entrar("ana@a.com", "errada-123")
        self.assertEqual(self.doc("ana@a.com")["bloqueadoAte"], int(self.agora + 60))
        self.agora += 61
        self.entrar("ana@a.com", "errada-123")  # 6ª falha: espera dobra
        self.assertEqual(self.doc("ana@a.com")["falhas"], 6)
        self.assertEqual(self.doc("ana@a.com")["bloqueadoAte"], int(self.agora + 120))
        self.agora += 121
        self.assertEqual(self.entrar("ana@a.com", SENHA)[0], 200)
        doc = self.doc("ana@a.com")
        self.assertEqual((doc["falhas"], doc["bloqueadoAte"]), (0, 0))

    def test_tentativa_na_espera_nao_estende_a_espera(self):
        for _ in range(5):
            self.entrar("ana@a.com", "errada-123")
        antes = self.doc("ana@a.com")
        self.agora += 30
        for _ in range(5):
            self.entrar("ana@a.com", "errada-123", ip="201.0.0.9")
        depois = self.doc("ana@a.com")
        self.assertEqual((depois["falhas"], depois["bloqueadoAte"]),
                         (antes["falhas"], antes["bloqueadoAte"]))

    def test_falha_usa_patch_e_nao_desfaz_troca_de_senha(self):
        # Outra chamada troca a senha e a sessão entre a leitura e a gravação da falha.
        usuarios = self.containers["usuarios"]

        def troca_concorrente(item_id):
            doc = usuarios._achar(item_id)
            doc.update({"senhaHash": "hash-novo", "sessao": 7})

        usuarios.antes_do_patch = troca_concorrente
        self.assertEqual(self.entrar("ana@a.com", "errada-123")[0], 401)
        doc = self.doc("ana@a.com")
        self.assertEqual((doc["senhaHash"], doc["sessao"], doc["falhas"]), ("hash-novo", 7, 1))
        tipos = {t for t, _, _ in usuarios.escritas}
        self.assertEqual(tipos, {"patch"})
        caminhos = {o["path"] for _, _, ops in usuarios.escritas for o in ops}
        self.assertEqual(caminhos, {"/falhas", "/ultimaFalha"})

    def test_falhas_concorrentes_somam(self):
        # Duas instâncias leram falhas=3; a soma é no banco, então vira 5 e entra em espera.
        self.containers["usuarios"]._achar("ana@a.com").update(
            {"falhas": 3, "ultimaFalha": int(self.agora)})
        lido = self.doc("ana@a.com")
        function_app._registrar_falha(lido, self.agora)
        function_app._registrar_falha(lido, self.agora)
        doc = self.doc("ana@a.com")
        self.assertEqual(doc["falhas"], 5)
        self.assertEqual(doc["bloqueadoAte"], int(self.agora + 60))

    def test_sucesso_zera_com_patch(self):
        self.entrar("ana@a.com", "errada-123")
        usuarios = self.containers["usuarios"]
        usuarios.escritas.clear()
        self.assertEqual(self.entrar("ana@a.com", SENHA)[0], 200)
        (tipo, _, ops), = usuarios.escritas
        self.assertEqual(tipo, "patch")
        self.assertEqual({o["path"] for o in ops}, {"/falhas", "/bloqueadoAte"})

    def test_usuario_removido_no_meio(self):
        usuarios = self.containers["usuarios"]
        usuarios.antes_do_patch = lambda item_id: usuarios.delete_item(item_id, item_id)
        self.assertEqual(self.entrar("ana@a.com", "errada-123"), (401, {"erros": [MSG]}))

    def test_limite_por_ip(self):
        for n in range(function_app.LOGIN_FALHAS_POR_IP):
            self.assertEqual(self.entrar(f"x{n}@a.com", "errada-123")[0], 401)
        status, corpo = self.entrar("bia@a.com", SENHA)
        self.assertEqual((status, corpo), (429, {"erros": [function_app.MSG_IP_EM_ESPERA]}))
        # As contas não entraram em espera: de outro IP, a senha certa entra.
        self.assertEqual(self.entrar("bia@a.com", SENHA, ip="201.0.0.9")[0], 200)
        # A janela acaba e o IP volta.
        self.agora += function_app.LOGIN_JANELA_IP_S
        self.assertEqual(self.entrar("bia@a.com", SENHA)[0], 200)

    def test_ip_pelo_ultimo_salto(self):
        # Trocar o primeiro item do X-Forwarded-For não dá um IP novo a cada tentativa.
        for n in range(function_app.LOGIN_FALHAS_POR_IP):
            self.chamar(LOGIN, "POST", "/api/login", {"email": "x@a.com", "senha": "e"},
                        headers={"X-Forwarded-For": f"10.0.0.{n}, 200.9.9.9:1234"})
        status, _ = self.chamar(LOGIN, "POST", "/api/login", {"email": "bia@a.com",
                                                              "senha": SENHA},
                                headers={"X-Forwarded-For": "10.9.9.9, 200.9.9.9:999"})
        self.assertEqual(status, 429)

    def test_log_sem_email_completo(self):
        logging.disable(logging.NOTSET)
        with self.assertLogs(level="WARNING") as log:
            self.entrar("ana.souza@vale.com", "errada-123")
        texto = "\n".join(log.output)
        self.assertNotIn("ana.souza", texto)
        self.assertIn("a***@vale.com", texto)



class TestSessao(BaseAcesso):
    def token(self, email):
        return gerar_token(self.doc(email), SEGREDO)

    def com_token(self, rota, metodo, url, token, corpo=None, **rota_params):
        h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        dados = json.dumps(corpo).encode() if corpo is not None else b""
        r = rota(func.HttpRequest(method=metodo, url=url, body=dados, headers=h,
                                  route_params=rota_params))
        return r.status_code, json.loads(r.get_body() or b"null")

    def test_sair_derruba_todos_os_tokens(self):
        celular, notebook = self.token("ana@a.com"), self.token("ana@a.com")
        self.assertEqual(self.com_token(EU, "GET", "/api/eu", notebook)[0], 200)
        self.assertEqual(self.com_token(SAIR, "POST", "/api/sair", celular), (204, None))
        for token in (celular, notebook):
            self.assertEqual(self.com_token(EU, "GET", "/api/eu", token),
                             (401, {"erros": ["faça login para continuar"]}))
        self.assertEqual(self.doc("ana@a.com")["sessao"], 1)
        # Outro usuário não é afetado.
        self.assertEqual(self.chamar(EU, "GET", "/api/eu", email="bia@a.com")[0], 200)

    def test_sair_usa_patch_e_operador_pode(self):
        status, _ = self.chamar(SAIR, "POST", "/api/sair", email="bia@a.com")
        self.assertEqual(status, 204)
        (tipo, item, ops), = self.containers["usuarios"].escritas
        self.assertEqual((tipo, item, ops),
                         ("patch", "bia@a.com", [{"op": "incr", "path": "/sessao", "value": 1}]))

    def test_sair_sem_token(self):
        self.assertEqual(self.chamar(SAIR, "POST", "/api/sair")[0], 401)
        self.assertEqual(self.containers["usuarios"].escritas, [])

    def test_trocar_senha_com_patch(self):
        antigo = self.token("ana@a.com")
        status, corpo = self.com_token(SENHA_ROTA, "POST", "/api/senha", antigo,
                                       {"atual": SENHA, "nova": "nova-senha-456"})
        self.assertEqual(status, 200)
        doc = self.doc("ana@a.com")
        self.assertEqual(doc["sessao"], 1)
        self.assertNotEqual(doc["senhaHash"], HASH)
        self.assertEqual(ler_token(corpo["token"], SEGREDO)["ver"], 1)
        self.assertEqual(self.com_token(EU, "GET", "/api/eu", antigo)[0], 401)
        self.assertEqual(self.com_token(EU, "GET", "/api/eu", corpo["token"])[0], 200)
        self.assertEqual({t for t, _, _ in self.containers["usuarios"].escritas}, {"patch"})

    def test_gestor_nao_redefine_a_propria_senha(self):
        status, corpo = self.chamar(USUARIOS, "PUT", "/api/usuarios/ana@a.com",
                                    {"senha": "tomada-123"}, email="ana@a.com",
                                    id="ana@a.com")
        self.assertEqual((status, corpo), (400, {"erros": [
            "para trocar a própria senha use Configurações → Trocar senha"]}))
        self.assertEqual(self.doc("ana@a.com")["senhaHash"], HASH)
        self.assertEqual(self.containers["usuarios"].escritas, [])

    def test_gestor_redefine_senha_de_outro_com_patch(self):
        self.containers["usuarios"]._achar("bia@a.com").update(
            {"falhas": 7, "bloqueadoAte": int(self.agora + 600), "telefone": "guardado"})
        status, corpo = self.chamar(USUARIOS, "PUT", "/api/usuarios/bia@a.com",
                                    {"senha": "nova-senha-789"}, email="ana@a.com",
                                    id="bia@a.com")
        self.assertEqual(status, 200)
        self.assertEqual(corpo, {"id": "bia@a.com", "nome": "Bia", "perfil": "operador",
                                 "empresaId": "E-A"})
        doc = self.doc("bia@a.com")
        self.assertEqual((doc["falhas"], doc["bloqueadoAte"], doc["sessao"]), (0, 0, 1))
        self.assertEqual(doc["telefone"], "guardado")
        self.assertEqual({t for t, _, _ in self.containers["usuarios"].escritas}, {"patch"})

    def test_gestor_nao_redefine_de_outra_empresa(self):
        status, _ = self.chamar(USUARIOS, "PUT", "/api/usuarios/caio@b.com",
                                {"senha": "nova-senha-789"}, email="ana@a.com",
                                id="caio@b.com")
        self.assertEqual(status, 404)

    def test_logs_de_usuarios_sem_email_completo(self):
        logging.disable(logging.NOTSET)
        with self.assertLogs(level="INFO") as log:
            self.chamar(USUARIOS, "POST", "/api/usuarios",
                        {"email": "carla.dias@a.com", "nome": "Carla", "perfil": "operador",
                         "senha": "senha-nova-123"}, email="ana@a.com")
            self.chamar(USUARIOS, "PUT", "/api/usuarios/carla.dias@a.com",
                        {"senha": "outra-senha-123"}, email="ana@a.com", id="carla.dias@a.com")
            self.chamar(USUARIOS, "DELETE", "/api/usuarios/carla.dias@a.com",
                        email="ana@a.com", id="carla.dias@a.com")
            self.chamar(SAIR, "POST", "/api/sair", email="ana@a.com")
        texto = "\n".join(log.output)
        self.assertEqual(len(log.output), 4)
        self.assertNotIn("carla.dias", texto)
        self.assertNotIn("ana@a.com", texto)
        self.assertIn("c***@a.com", texto)

    def test_cadastro_sem_perfil_nega(self):
        token = self.token("ana@a.com")
        del self.containers["usuarios"]._achar("ana@a.com")["perfil"]
        self.assertEqual(self.com_token(EU, "GET", "/api/eu", token),
                         (403, {"erros": ["seu perfil não tem acesso a esta ação"]}))
        status, _ = self.com_token(USUARIOS, "GET", "/api/usuarios", token)
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
