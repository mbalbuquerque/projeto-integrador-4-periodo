"""Alertas Web Push: validação da inscrição, envio (lib simulada) e transição de faixa.

Nenhum teste usa rede: o envio é simulado trocando `push.webpush` ou o
`requests.post` da pywebpush (este último deixa a criptografia real rodar).
"""

import base64
import json
import os
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import http_ece
import pywebpush
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import function_app
import push
from test_rotas import BaseRotas, ContainerRotas

TELEMETRIA = function_app.telemetria.build().get_user_function()
CHAVE = function_app.push_chave.build().get_user_function()
INSCRICAO = function_app.push_inscricao.build().get_user_function()

P256DH = "B" + "A" * 86
AUTH = "A" * 22


def b64(dados):
    return base64.urlsafe_b64encode(dados).decode().rstrip("=")


def gerar_vapid():
    chave = ec.generate_private_key(ec.SECP256R1())
    privada = b64(chave.private_numbers().private_value.to_bytes(32, "big"))
    publica = b64(chave.public_key().public_bytes(serialization.Encoding.X962,
                                                  serialization.PublicFormat.UncompressedPoint))
    return publica, privada


VAPID_PUBLICA, VAPID_PRIVADA = gerar_vapid()
ENV_VAPID = {"VAPID_PUBLIC_KEY": VAPID_PUBLICA, "VAPID_PRIVATE_KEY": VAPID_PRIVADA,
             "VAPID_SUBJECT": "https://exemplo.invalido"}


def inscricao(sufixo="1", host="fcm.googleapis.com"):
    return {"endpoint": f"https://{host}/fcm/send/{sufixo}",
            "keys": {"p256dh": P256DH, "auth": AUTH}}


class RespostaFalsa:
    def __init__(self, status):
        self.status_code = status
        self.text = ""
        self.reason = "Gone" if status == 410 else "OK"
        self.headers = {}


# ------------------------------------------------------------ push.py

class TestValidacao(unittest.TestCase):
    def test_endpoint_dos_servicos_conhecidos(self):
        for url in ("https://fcm.googleapis.com/fcm/send/x",
                    "https://updates.push.services.mozilla.com/wpush/v2/x",
                    "https://web.push.apple.com/QG",
                    "https://wns2-by3p.notify.windows.com/w/?token=x",
                    "https://fcm.googleapis.com:443/fcm/send/x"):
            self.assertEqual(push.validar_endpoint(url), [], url)

    def test_endpoint_recusado(self):
        casos = {
            None: "até",
            "": "até",
            "x" * (push.ENDPOINT_MAX + 1): "até",
            "http://fcm.googleapis.com/fcm/send/x": "https",
            "https://fcm.googleapis.com:8443/x": "https",
            "https://fcm.googleapis.com:abc/x": "https",
            "https://[::1/x": "https",
            "https:///x": "https",
            "https://evil.com/fcm.googleapis.com": "não reconhecido",
            "https://fcm.googleapis.com.evil.com/x": "não reconhecido",
            "https://169.254.169.254/latest": "não reconhecido",
        }
        for url, trecho in casos.items():
            erros = push.validar_endpoint(url)
            self.assertEqual(len(erros), 1, url)
            self.assertIn(trecho, erros[0], url)

    def test_inscricao_valida_ignora_extras(self):
        dados = {**inscricao(), "expirationTime": None, "outro": 1}
        erros, doc = push.validar_inscricao(dados)
        self.assertEqual(erros, [])
        self.assertEqual(doc, inscricao())

    def test_inscricao_invalida(self):
        self.assertEqual(push.validar_inscricao([])[0], ["corpo deve ser um objeto JSON"])
        erros, doc = push.validar_inscricao({"endpoint": "https://fcm.googleapis.com/x"})
        self.assertIsNone(doc)
        self.assertIn("keys: objeto com p256dh e auth", erros)
        erros, _ = push.validar_inscricao({"endpoint": "ftp://x",
                                           "keys": {"p256dh": "curta", "auth": "a b"}})
        self.assertEqual(len(erros), 3)

    def test_remocao(self):
        self.assertEqual(push.validar_remocao({"endpoint": "https://a"}), ([], "https://a"))
        self.assertEqual(push.validar_remocao(None)[0], ["endpoint: obrigatório"])
        self.assertEqual(push.validar_remocao({"endpoint": 3})[0], ["endpoint: obrigatório"])
        self.assertIn("até", push.validar_remocao({"endpoint": ""})[0][0])

    def test_juntar_sem_repetir_e_com_teto(self):
        lista = [inscricao(str(i)) for i in range(push.MAX_POR_USUARIO)]
        nova = inscricao("0")
        juntas = push.juntar(lista, nova)
        self.assertEqual(len(juntas), push.MAX_POR_USUARIO)
        self.assertEqual(juntas[-1], nova)
        mais = push.juntar(juntas, inscricao("novo"))
        self.assertEqual(len(mais), push.MAX_POR_USUARIO)
        self.assertNotIn(inscricao("1"), mais)  # a mais antiga saiu
        self.assertEqual(push.juntar(None, nova), [nova])

    def test_sem(self):
        lista = [inscricao("1"), inscricao("2")]
        self.assertEqual(push.sem(lista, {inscricao("1")["endpoint"]}), [inscricao("2")])
        self.assertEqual(push.sem(None, {"x"}), [])

    def test_piorou(self):
        self.assertTrue(push.piorou("NORMAL", "ATENCAO"))
        self.assertTrue(push.piorou("NORMAL", "CRITICO"))
        self.assertTrue(push.piorou("ATENCAO", "CRITICO"))
        self.assertTrue(push.piorou(None, "ATENCAO"))
        self.assertFalse(push.piorou("ATENCAO", "ATENCAO"))
        self.assertFalse(push.piorou("CRITICO", "ATENCAO"))
        self.assertFalse(push.piorou("CRITICO", "NORMAL"))
        self.assertFalse(push.piorou(None, "NORMAL"))

    def test_mensagem(self):
        leitura = {"deviceId": "dev-01", "temperatura": 20.04, "perfil": "manga",
                   "status": "CRITICO"}
        m = push.mensagem(leitura, "CAM-01")
        self.assertEqual(m["titulo"], "Crítico: Veículo CAM-01")
        self.assertIn("20.0 °C", m["corpo"])
        self.assertIn("(Manga)", m["corpo"])
        self.assertEqual(m["url"], "/alertas?veiculo=CAM-01")
        self.assertEqual(m["tag"], "coldtrack-dev-01")
        sem_veiculo = push.mensagem({**leitura, "status": "ATENCAO", "perfil": "outro"})
        self.assertEqual(sem_veiculo["titulo"], "Atenção: Sensor dev-01")
        self.assertEqual(sem_veiculo["url"], "/alertas")
        self.assertIn("(outro)", sem_veiculo["corpo"])

    def test_mensagem_do_motorista_abre_a_tela_dele(self):
        leitura = {"deviceId": "dev-01", "temperatura": 20.0, "perfil": "manga",
                   "status": "CRITICO"}
        m = push.mensagem(leitura, "CAM-01", motorista=True)
        self.assertEqual(m["titulo"], "Crítico: Veículo CAM-01")
        self.assertEqual(m["url"], "/motorista")
        self.assertIn("Toque para ver a carga.", m["corpo"])
        self.assertEqual(m["tag"], "coldtrack-dev-01")

    def test_configurado(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(push.configurado())
            self.assertIsNone(push.chave_publica())
        with mock.patch.dict(os.environ, {"VAPID_PUBLIC_KEY": "x"}, clear=True):
            self.assertFalse(push.configurado())
        with mock.patch.dict(os.environ, ENV_VAPID):
            self.assertTrue(push.configurado())
            self.assertEqual(push.chave_publica(), VAPID_PUBLICA)


@mock.patch.dict(os.environ, ENV_VAPID)
class TestEnvio(unittest.TestCase):
    def test_ok_com_parametros(self):
        with mock.patch.object(push, "webpush") as webpush:
            self.assertEqual(push.enviar({**inscricao(), "criadaEm": "x"}, {"titulo": "Ação"}),
                             "ok")
        kw = webpush.call_args.kwargs
        self.assertEqual(kw["subscription_info"], inscricao())  # sem criadaEm
        self.assertEqual(json.loads(kw["data"]), {"titulo": "Ação"})
        self.assertEqual(kw["vapid_private_key"], VAPID_PRIVADA)
        self.assertEqual(kw["vapid_claims"], {"sub": "https://exemplo.invalido"})
        self.assertEqual((kw["ttl"], kw["timeout"]), (push.TTL_S, push.TIMEOUT_S))

    def test_expirada_404_e_410(self):
        for codigo in (404, 410):
            erro = pywebpush.WebPushException("x", response=RespostaFalsa(codigo))
            with mock.patch.object(push, "webpush", side_effect=erro):
                self.assertEqual(push.enviar(inscricao(), {}), "expirada")

    def test_falha_do_servico_e_de_rede(self):
        for erro in (pywebpush.WebPushException("x", response=RespostaFalsa(500)),
                     pywebpush.WebPushException("sem resposta"),
                     ConnectionError("rede"), ValueError("chave")):
            with mock.patch.object(push, "webpush", side_effect=erro):
                with self.assertLogs(level="WARNING") as log:
                    self.assertEqual(push.enviar(inscricao(), {}), "falha")
            self.assertNotIn("fcm.googleapis.com", "\n".join(log.output))


@mock.patch.dict(os.environ, ENV_VAPID)
class TestCriptografiaReal(unittest.TestCase):
    """A pywebpush cifra de verdade (RFC 8291); só o POST HTTP é simulado.

    O teste faz o papel do navegador: gera as chaves da inscrição e decifra o
    que a API mandaria ao serviço de push.
    """

    def setUp(self):
        self.navegador = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        publica = self.navegador.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.inscricao = {"endpoint": "https://fcm.googleapis.com/fcm/send/teste",
                          "keys": {"p256dh": b64(publica), "auth": b64(self.auth)}}
        self.assertEqual(push.validar_inscricao(self.inscricao)[0], [])

    def test_conteudo_chega_cifrado_e_decifravel(self):
        conteudo = {"titulo": "Crítico: Veículo CAM-01", "url": "/alertas?veiculo=CAM-01"}
        with mock.patch.object(pywebpush.requests, "post",
                               return_value=RespostaFalsa(201)) as post:
            self.assertEqual(push.enviar(self.inscricao, conteudo), "ok")
        (url,), kw = post.call_args
        self.assertEqual(url, self.inscricao["endpoint"])
        self.assertEqual(kw["headers"]["content-encoding"], "aes128gcm")
        self.assertTrue(kw["headers"]["authorization"].startswith("vapid t="))
        self.assertIn(f"k={VAPID_PUBLICA}", kw["headers"]["authorization"])
        self.assertNotIn(b"CAM-01", kw["data"])
        claro = http_ece.decrypt(kw["data"], private_key=self.navegador,
                                 auth_secret=self.auth, version="aes128gcm")
        self.assertEqual(json.loads(claro), conteudo)

    def test_servico_responde_410(self):
        with mock.patch.object(pywebpush.requests, "post", return_value=RespostaFalsa(410)):
            self.assertEqual(push.enviar(self.inscricao, {}), "expirada")


# ------------------------------------------------------------ rotas

class ContainerPush(ContainerRotas):
    """Falso com o filtro de leitura anterior (@antes) e a busca por endpoint."""

    def query_items(self, query, parameters=(), partition_key=None, **kwargs):
        p = {x["name"]: x["value"] for x in parameters}
        if "@endpoint" in p:
            return iter([{"id": i["id"], "push": i["push"]} for i in self.itens
                         if any(x.get("endpoint") == p["@endpoint"] for x in i.get("push") or [])])
        if "@antes" in p:
            guardados = self.itens
            self.itens = [i for i in guardados if i.get("medidoEm", "") < p["@antes"]]
            try:
                return iter(list(super().query_items(query, parameters, partition_key,
                                                     **kwargs)))
            finally:
                self.itens = guardados
        return super().query_items(query, parameters, partition_key, **kwargs)


class BasePush(BaseRotas):
    def setUp(self):
        super().setUp()
        self.containers = {n: ContainerPush(c.itens) for n, c in self.containers.items()}
        function_app.LIMITES.reiniciar()
        self.vapid = mock.patch.dict(os.environ, ENV_VAPID)
        self.vapid.start()

    def tearDown(self):
        self.vapid.stop()
        function_app.LIMITES.reiniciar()
        super().tearDown()

    def usuario(self, email):
        return self.containers["usuarios"].read_item(email, partition_key=email)


class TestRotaChave(BasePush):
    def test_chave_publica(self):
        status, corpo = self.chamar(CHAVE, "GET", "/api/push/chave")
        self.assertEqual((status, corpo), (200, {"chave": VAPID_PUBLICA}))

    def test_sem_configuracao_503(self):
        with mock.patch.dict(os.environ, {"VAPID_PRIVATE_KEY": ""}):
            status, corpo = self.chamar(CHAVE, "GET", "/api/push/chave")
        self.assertEqual(status, 503)
        self.assertEqual(corpo, {"erros": ["alertas push indisponíveis"]})


class TestRotaInscricao(BasePush):
    def test_exige_login(self):
        for metodo in ("POST", "DELETE"):
            self.assertEqual(self.chamar(INSCRICAO, metodo, "/api/push/inscricao",
                                         inscricao())[0], 401)

    def test_corpo_invalido(self):
        status, corpo = self.chamar(INSCRICAO, "POST", "/api/push/inscricao",
                                    corpo_raw=b"x", email="operador@a.com")
        self.assertEqual(status, 400)
        status, corpo = self.chamar(INSCRICAO, "POST", "/api/push/inscricao",
                                    inscricao(host="evil.com"), email="operador@a.com")
        self.assertEqual(status, 400)
        self.assertIn("endpoint: serviço de push não reconhecido", corpo["erros"])
        self.assertNotIn("push", self.usuario("operador@a.com"))

    def test_inscreve_sem_duplicar(self):
        status, corpo = self.chamar(INSCRICAO, "POST", "/api/push/inscricao",
                                    {**inscricao(), "expirationTime": None},
                                    email="operador@a.com")
        self.assertEqual((status, corpo), (201, {"inscricoes": 1}))
        status, corpo = self.chamar(INSCRICAO, "POST", "/api/push/inscricao", inscricao(),
                                    email="operador@a.com")
        self.assertEqual((status, corpo), (201, {"inscricoes": 1}))
        status, corpo = self.chamar(INSCRICAO, "POST", "/api/push/inscricao", inscricao("2"),
                                    email="operador@a.com")
        self.assertEqual((status, corpo), (201, {"inscricoes": 2}))
        gravadas = self.usuario("operador@a.com")["push"]
        self.assertEqual([g["endpoint"] for g in gravadas],
                         [inscricao()["endpoint"], inscricao("2")["endpoint"]])
        self.assertTrue(all("criadaEm" in g for g in gravadas))
        self.assertNotIn("expirationTime", gravadas[0])
        # Nenhum dado da inscrição sai nas rotas de usuário.
        self.assertNotIn("push", function_app.publico(self.usuario("operador@a.com")))

    def test_mesmo_aparelho_troca_de_conta(self):
        self.chamar(INSCRICAO, "POST", "/api/push/inscricao", inscricao(), email="gestor@b.com")
        self.chamar(INSCRICAO, "POST", "/api/push/inscricao", inscricao("outro"),
                    email="gestor@b.com")
        status, _ = self.chamar(INSCRICAO, "POST", "/api/push/inscricao", inscricao(),
                                email="operador@a.com")
        self.assertEqual(status, 201)
        restantes = [i["endpoint"] for i in self.usuario("gestor@b.com")["push"]]
        self.assertEqual(restantes, [inscricao("outro")["endpoint"]])

    def test_usuario_removido_no_meio(self):
        with mock.patch.object(function_app, "_patch_usuario", return_value=None):
            status, _ = self.chamar(INSCRICAO, "POST", "/api/push/inscricao", inscricao(),
                                    email="operador@a.com")
        self.assertEqual(status, 401)

    def test_remove(self):
        self.chamar(INSCRICAO, "POST", "/api/push/inscricao", inscricao(), email="operador@a.com")
        status, _ = self.chamar(INSCRICAO, "DELETE", "/api/push/inscricao",
                                {"endpoint": inscricao()["endpoint"]}, email="operador@a.com")
        self.assertEqual(status, 204)
        self.assertEqual(self.usuario("operador@a.com")["push"], [])
        # De novo (ou endpoint que não é dele): 204 sem escrever nada.
        escritas = len(self.containers["usuarios"].escritas)
        status, _ = self.chamar(INSCRICAO, "DELETE", "/api/push/inscricao",
                                {"endpoint": inscricao()["endpoint"]}, email="operador@a.com")
        self.assertEqual(status, 204)
        self.assertEqual(len(self.containers["usuarios"].escritas), escritas)

    def test_remove_corpo_invalido(self):
        status, corpo = self.chamar(INSCRICAO, "DELETE", "/api/push/inscricao", {},
                                    email="operador@a.com")
        self.assertEqual((status, corpo), (400, {"erros": ["endpoint: obrigatório"]}))


class TestTransicao(BasePush):
    """POST /telemetria do dev-01 (veículo CAM-01, manga: normal 10 a 13 °C, margem 3)."""

    def setUp(self):
        super().setUp()
        usuarios = self.containers["usuarios"]
        for email, sufixos in (("gestor@a.com", ["g1", "g2"]), ("operador@a.com", ["o1"]),
                               ("gestor@b.com", ["b1"])):
            usuarios._achar(email)["push"] = [inscricao(s) for s in sufixos]
        self.relogio = int(time.time()) - 30
        self.webpush = mock.patch.object(push, "webpush")
        self.envio = self.webpush.start()

    def tearDown(self):
        self.webpush.stop()
        super().tearDown()

    def ler(self, temperatura, atraso=0, medido=None):
        if medido is None:
            self.relogio += 20
            medido = self.relogio - atraso
        return self.chamar(TELEMETRIA, "POST", "/api/telemetria", {
            "deviceId": "dev-01", "temperatura": temperatura, "umidade": 80.0, "rssi": -60,
            "medidoEm": medido}, headers={"x-device-key": self.chave_dev1})

    def destinos(self):
        return sorted(c.kwargs["subscription_info"]["endpoint"].rsplit("/", 1)[-1]
                      for c in self.envio.call_args_list)

    def test_normal_para_critico_avisa_so_a_empresa(self):
        status, corpo = self.ler(20.0)
        self.assertEqual((status, corpo["status"]), (201, "CRITICO"))
        self.assertEqual(self.destinos(), ["g1", "g2", "o1"])  # sem o gestor da empresa B
        conteudo = json.loads(self.envio.call_args.kwargs["data"])
        self.assertEqual(conteudo["url"], "/alertas?veiculo=CAM-01")
        self.assertEqual(conteudo["status"], "CRITICO")

    def test_mesma_faixa_e_melhora_nao_avisam(self):
        self.ler(14.5)                       # NORMAL -> ATENCAO: avisa
        self.assertEqual(len(self.envio.call_args_list), 3)
        self.ler(14.8)                       # ATENCAO -> ATENCAO
        self.ler(12.0)                       # -> NORMAL
        self.assertEqual(len(self.envio.call_args_list), 3)
        self.ler(20.0)                       # NORMAL -> CRITICO: avisa
        self.ler(15.0)                       # CRITICO -> ATENCAO: melhorou
        self.assertEqual(len(self.envio.call_args_list), 6)

    def test_atencao_para_critico_avisa(self):
        self.ler(14.5)
        self.ler(20.0)
        self.assertEqual(len(self.envio.call_args_list), 6)

    def test_reenvio_duplicado_nao_avisa(self):
        self.ler(20.0)
        status, corpo = self.ler(20.0, medido=self.relogio)
        self.assertEqual((status, corpo.get("duplicada")), (200, True))
        self.assertEqual(len(self.envio.call_args_list), 3)

    def test_oscilando_na_borda_avisa_uma_vez_por_intervalo(self):
        for _ in range(3):
            self.ler(14.5)
            self.ler(12.0)
        self.assertEqual(len(self.envio.call_args_list), 3)

    def test_leitura_atrasada_da_fila_nao_avisa(self):
        status, _ = self.ler(20.0, atraso=push.IDADE_MAX_S + 60)
        self.assertEqual(status, 201)
        self.envio.assert_not_called()

    def test_normal_e_sem_configuracao_nao_consultam(self):
        self.ler(12.0)
        with mock.patch.dict(os.environ, {"VAPID_PUBLIC_KEY": ""}):
            self.ler(20.0)
        self.envio.assert_not_called()

    def test_ninguem_inscrito(self):
        for u in self.containers["usuarios"].itens:
            u.pop("push", None)
        self.assertEqual(self.ler(20.0)[0], 201)
        self.envio.assert_not_called()

    def test_inscricao_expirada_sai_e_falha_nao_quebra(self):
        def responder(subscription_info, **_):
            fim = subscription_info["endpoint"].rsplit("/", 1)[-1]
            if fim == "g1":
                raise pywebpush.WebPushException("x", response=RespostaFalsa(410))
            if fim == "o1":
                raise ConnectionError("rede")
        self.envio.side_effect = responder
        status, _ = self.ler(20.0)
        self.assertEqual(status, 201)
        self.assertEqual([i["endpoint"].rsplit("/", 1)[-1]
                          for i in self.usuario("gestor@a.com")["push"]], ["g2"])
        self.assertEqual(len(self.usuario("operador@a.com")["push"]), 1)  # falha não apaga

    def test_erro_inesperado_no_push_nao_quebra_a_gravacao(self):
        with mock.patch.object(function_app, "lista", side_effect=RuntimeError("banco")):
            with self.assertLogs(level="WARNING") as log:
                status, corpo = self.ler(20.0)
        self.assertEqual(status, 201)
        self.assertIn("RuntimeError", "\n".join(log.output))
        self.containers["leituras"].read_item(corpo["id"], partition_key="dev-01")

    def test_sensor_sem_veiculo_aponta_para_alertas(self):
        self.containers["veiculos"].itens.clear()
        self.ler(20.0)
        conteudo = json.loads(self.envio.call_args.kwargs["data"])
        self.assertEqual(conteudo["url"], "/alertas")
        self.assertEqual(conteudo["titulo"], "Atenção: Sensor dev-01")  # perfil demonstrativo

    def test_compara_pelo_horario_da_medicao(self):
        # Leitura nova chega antes de uma mais antiga: a antiga compara com a dela, não a nova.
        agora = datetime.now(timezone.utc)
        self.ler(20.0, medido=int(agora.timestamp()))
        anterior = int((agora - timedelta(seconds=40)).timestamp())
        self.ler(20.0, medido=anterior)  # anterior a ela é a NORMAL de maio: piorou
        self.assertEqual(len(self.envio.call_args_list), 3)  # mas o intervalo segura


class TestPushMotorista(BasePush):
    """Motorista se inscreve e só recebe o push do veículo vinculado a ele."""

    def setUp(self):
        super().setUp()
        usuarios = self.containers["usuarios"]
        hash_ = usuarios.itens[0]["senhaHash"]
        usuarios.itens += [
            {"id": "moto1@a.com", "nome": "Moto 1", "perfil": "motorista", "veiculo": "CAM-01",
             "empresaId": "E-A", "sessao": 0, "senhaHash": hash_},
            {"id": "moto2@a.com", "nome": "Moto 2", "perfil": "motorista", "veiculo": "CT-002",
             "empresaId": "E-A", "sessao": 0, "senhaHash": hash_},
            {"id": "moto3@a.com", "nome": "Moto 3", "perfil": "motorista",
             "empresaId": "E-A", "sessao": 0, "senhaHash": hash_},
            {"id": "estranho@a.com", "nome": "Sem perfil", "perfil": "visitante",
             "empresaId": "E-A", "sessao": 0, "senhaHash": hash_},
        ]
        self.containers["veiculos"].itens.append(
            {"id": "E-A~CT-002", "empresaId": "E-A", "deviceId": "dev-livre",
             "tipo": "Baú refrigerado", "perfil": "manga"})
        self.relogio = int(time.time()) - 30
        self.webpush = mock.patch.object(push, "webpush")
        self.envio = self.webpush.start()

    def tearDown(self):
        self.webpush.stop()
        super().tearDown()

    def inscrever_todos(self):
        usuarios = self.containers["usuarios"]
        for email, sufixo in (("gestor@a.com", "g1"), ("operador@a.com", "o1"),
                              ("moto1@a.com", "m1"), ("moto2@a.com", "m2"),
                              ("moto3@a.com", "m3"), ("estranho@a.com", "x1"),
                              ("gestor@b.com", "b1")):
            usuarios._achar(email)["push"] = [inscricao(sufixo)]

    def ler(self, temperatura):
        self.relogio += 20
        return self.chamar(TELEMETRIA, "POST", "/api/telemetria", {
            "deviceId": "dev-01", "temperatura": temperatura, "umidade": 80.0, "rssi": -60,
            "medidoEm": self.relogio}, headers={"x-device-key": self.chave_dev1})

    def enviados(self):
        """{sufixo do endpoint: url da notificação}."""
        return {c.kwargs["subscription_info"]["endpoint"].rsplit("/", 1)[-1]:
                json.loads(c.kwargs["data"])["url"] for c in self.envio.call_args_list}

    def test_motorista_inscreve_e_remove(self):
        status, corpo = self.chamar(INSCRICAO, "POST", "/api/push/inscricao", inscricao("m1"),
                                    email="moto1@a.com")
        self.assertEqual((status, corpo), (201, {"inscricoes": 1}))
        self.assertEqual(len(self.usuario("moto1@a.com")["push"]), 1)
        status, _ = self.chamar(INSCRICAO, "DELETE", "/api/push/inscricao",
                                {"endpoint": inscricao("m1")["endpoint"]}, email="moto1@a.com")
        self.assertEqual(status, 204)
        self.assertEqual(self.usuario("moto1@a.com")["push"], [])

    def test_so_o_motorista_do_veiculo_recebe_e_abre_a_tela_dele(self):
        self.inscrever_todos()
        status, corpo = self.ler(20.0)
        self.assertEqual((status, corpo["status"]), (201, "CRITICO"))
        # moto2 (outro veículo), moto3 (sem veículo), perfil desconhecido e empresa B: nada.
        self.assertEqual(self.enviados(), {"g1": "/alertas?veiculo=CAM-01",
                                           "o1": "/alertas?veiculo=CAM-01",
                                           "m1": "/motorista"})

    def test_troca_de_veiculo_troca_os_alertas(self):
        self.inscrever_todos()
        self.containers["usuarios"]._achar("moto1@a.com")["veiculo"] = "CT-002"
        self.containers["usuarios"]._achar("moto2@a.com")["veiculo"] = "CAM-01"
        self.ler(20.0)
        self.assertEqual(self.enviados(), {"g1": "/alertas?veiculo=CAM-01",
                                           "o1": "/alertas?veiculo=CAM-01",
                                           "m2": "/motorista"})

    def test_sensor_sem_veiculo_nao_avisa_motorista(self):
        self.inscrever_todos()
        self.containers["veiculos"].itens[:] = [
            v for v in self.containers["veiculos"].itens if v["id"] != "E-A~CAM-01"]
        self.ler(20.0)
        self.assertEqual(sorted(self.enviados()), ["g1", "o1"])

    def test_inscricao_expirada_do_motorista_sai(self):
        self.inscrever_todos()

        def responder(subscription_info, **_):
            if subscription_info["endpoint"].endswith("/m1"):
                raise pywebpush.WebPushException("x", response=RespostaFalsa(410))
        self.envio.side_effect = responder
        self.assertEqual(self.ler(20.0)[0], 201)
        self.assertEqual(self.usuario("moto1@a.com")["push"], [])
        self.assertEqual(len(self.usuario("gestor@a.com")["push"]), 1)

    def test_recebe_push(self):
        self.assertTrue(function_app.recebe_push({"perfil": "gestor"}, None))
        self.assertTrue(function_app.recebe_push({"perfil": "operador"}, "CAM-01"))
        self.assertTrue(function_app.recebe_push(
            {"perfil": "motorista", "veiculo": "CAM-01"}, "CAM-01"))
        self.assertFalse(function_app.recebe_push(
            {"perfil": "motorista", "veiculo": "CAM-01"}, "CT-002"))
        self.assertFalse(function_app.recebe_push({"perfil": "motorista"}, None))
        self.assertFalse(function_app.recebe_push({"perfil": "motorista"}, "CAM-01"))
        self.assertFalse(function_app.recebe_push({"veiculo": "CAM-01"}, "CAM-01"))


if __name__ == "__main__":
    unittest.main()
