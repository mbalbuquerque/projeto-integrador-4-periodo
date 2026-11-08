"""Testes do assistente do painel (sem rede: Cosmos e IA falsos). Rodar: python -m unittest -v"""

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import azure.functions as func

import assistente
import chat
import function_app
from seguranca import gerar_token
from test_chat import BASE, CONFIG, ClienteFalso
from test_falsos import ContainerFalso

SEGREDO = "segredo-de-teste-com-tamanho-suficiente-para-hs256"
AGORA = datetime.now(timezone.utc)


def iso(**delta):
    return (AGORA - timedelta(**delta)).isoformat()


def usuario(email, empresa, perfil):
    return {"id": email, "nome": email.split("@")[0].title(), "perfil": perfil,
            "empresaId": empresa, "sessao": 0, "senhaHash": "x"}


def banco():
    """Duas empresas no mesmo banco. Tudo da B tem a marca SEGREDO-B."""
    return {
        "empresas": [{"id": "E-A", "nome": "Frutas do Vale"},
                     {"id": "E-B", "nome": "SEGREDO-B Transportes"}],
        "usuarios": [usuario("gestor@a.com", "E-A", "gestor"),
                     usuario("operador@a.com", "E-A", "operador"),
                     usuario("gestor@b.com", "E-B", "gestor"),
                     usuario("segredo-b@b.com", "E-B", "operador")],
        "dispositivos": [
            {"id": "sensor-a", "empresaId": "E-A", "descricao": "Baú do CT-001",
             "criadoEm": iso(days=30)},
            {"id": "sensor-a2", "empresaId": "E-A", "descricao": "Reserva",
             "criadoEm": iso(days=5)},
            {"id": "sensor-b", "empresaId": "E-B", "descricao": "SEGREDO-B baú",
             "criadoEm": iso(days=3)},
        ],
        "veiculos": [
            {"id": "E-A~CT-001", "empresaId": "E-A", "tipo": "Caminhão baú",
             "perfil": "manga", "deviceId": "sensor-a", "dispositivo": ""},
            {"id": "E-B~CT-001", "empresaId": "E-B", "tipo": "SEGREDO-B carreta",
             "perfil": "uva", "deviceId": "sensor-b", "dispositivo": ""},
        ],
        "viagens": [
            {"id": "E-A~V-1", "empresaId": "E-A", "veiculo": "CT-001", "origem": "Petrolina",
             "destino": "Recife", "carga": "Manga Tommy", "inicio": iso(hours=5), "fim": None},
            {"id": "E-A~V-0", "empresaId": "E-A", "veiculo": "CT-001", "origem": "Juazeiro",
             "destino": "Salvador", "carga": "Manga", "inicio": iso(days=3),
             "fim": iso(days=2)},
            {"id": "E-B~V-9", "empresaId": "E-B", "veiculo": "CT-001",
             "origem": "SEGREDO-B origem", "destino": "x", "carga": "Uva",
             "inicio": iso(hours=1), "fim": None},
        ],
        "leituras": [
            {"id": "a1", "deviceId": "sensor-a", "empresaId": "E-A", "temperatura": 12.0,
             "umidade": 80.0, "rssi": -60, "status": "NORMAL", "medidoEm": iso(minutes=2),
             "recebidoEm": iso(minutes=2)},
            {"id": "a2", "deviceId": "sensor-a", "empresaId": "E-A", "temperatura": 14.5,
             "umidade": 79.0, "rssi": -61, "status": "ATENCAO", "medidoEm": iso(hours=2),
             "recebidoEm": iso(hours=2)},
            {"id": "a3", "deviceId": "sensor-a", "empresaId": "E-A", "temperatura": 18.5,
             "umidade": 78.0, "rssi": -62, "status": "CRITICO", "medidoEm": iso(hours=3),
             "recebidoEm": iso(hours=3)},
            {"id": "a-velha", "deviceId": "sensor-a", "empresaId": "E-A", "temperatura": 30.0,
             "umidade": 50.0, "rssi": -70, "status": "CRITICO", "medidoEm": iso(hours=30),
             "recebidoEm": iso(hours=30)},
            # Sensor reserva: só leitura de dois dias atrás (sem sinal).
            {"id": "a2-1", "deviceId": "sensor-a2", "empresaId": "E-A", "temperatura": 11.0,
             "umidade": 70.0, "rssi": None, "status": "NORMAL", "medidoEm": iso(days=2),
             "recebidoEm": iso(days=2)},
            # Leitura com a empresa B gravada na partição de um sensor da A.
            {"id": "intrusa", "deviceId": "sensor-a", "empresaId": "E-B", "temperatura": -99.0,
             "umidade": 1.0, "rssi": -1, "status": "CRITICO", "medidoEm": iso(minutes=1),
             "recebidoEm": iso(minutes=1)},
            {"id": "b1", "deviceId": "sensor-b", "empresaId": "E-B", "temperatura": 0.5,
             "umidade": 90.0, "rssi": -50, "status": "ATENCAO", "medidoEm": iso(minutes=1),
             "recebidoEm": iso(minutes=1)},
        ],
    }


ROTA = function_app.assistente_painel.build().get_user_function()


def pedido(corpo, email=None, empresa="E-A", perfil="gestor"):
    headers = {"Content-Type": "application/json"}
    if email:
        token = gerar_token(usuario(email, empresa, perfil), SEGREDO)
        headers["Authorization"] = f"Bearer {token}"
    dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
    return func.HttpRequest(method="POST", url="/api/assistente", body=dados, headers=headers)


class BaseRota(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {**CONFIG, "JWT_SECRET": SEGREDO})
        self.env.start()
        self.containers = {nome: ContainerFalso(itens) for nome, itens in banco().items()}
        self.containers["limites"] = ContainerFalso([])
        self.cosmos = mock.patch.object(
            function_app, "container",
            lambda nome=None: self.containers[nome or "leituras"])
        self.cosmos.start()
        self.falso = ClienteFalso(texto="O sensor-a marcou 12.0 °C às 14:00.")
        self.fabrica = mock.patch.object(chat, "fabrica_cliente", lambda: self.falso)
        self.fabrica.start()
        chat.reiniciar()
        chat._base = list(BASE)
        function_app.LIMITES.reiniciar()

    def tearDown(self):
        self.fabrica.stop()
        self.cosmos.stop()
        self.env.stop()
        chat.reiniciar()
        function_app.LIMITES.reiniciar()

    def chamar(self, corpo, email="gestor@a.com", perfil="gestor"):
        r = ROTA(pedido(corpo, email, perfil=perfil))
        return r.status_code, json.loads(r.get_body() or b"null")

    def mensagens(self):
        conversa = [kw for tipo, kw in self.falso.chamadas if tipo == "chat"]
        return conversa[-1]["messages"]

    def retrato(self):
        texto = self.mensagens()[1]["content"]
        return json.loads(texto.split("\n", 1)[1])


class TestRota(BaseRota):
    def test_resposta_com_fontes(self):
        status, corpo = self.chamar({"pergunta": "qual a temperatura do CT-001?"})
        self.assertEqual(status, 200)
        self.assertEqual(corpo, {"resposta": "O sensor-a marcou 12.0 °C às 14:00.",
                                 "fontes": ["dados da empresa", "README.md", "FAQ do site"],
                                 "origem": "ia"})

    def test_prompt_e_parametros(self):
        self.chamar({"pergunta": "e agora?", "historico": [
            {"papel": "usuario", "texto": "oi"}, {"papel": "assistente", "texto": "olá"}]})
        conversa = [kw for tipo, kw in self.falso.chamadas if tipo == "chat"][0]
        self.assertEqual(conversa["temperature"], 0.2)
        self.assertEqual(conversa["max_tokens"], 450)
        self.assertEqual(conversa["model"], "chat-teste")
        msgs = conversa["messages"]
        self.assertEqual([m["role"] for m in msgs],
                         ["system", "system", "system", "user", "assistant", "user"])
        self.assertEqual(msgs[0]["content"], assistente.SISTEMA)
        self.assertTrue(msgs[1]["content"].startswith("DADOS DA EMPRESA"))
        self.assertIn("[1] (README.md) Sensor ESP32-C3.", msgs[2]["content"])
        self.assertEqual(msgs[-1]["content"], "e agora?")

    def test_so_dados_da_propria_empresa(self):
        self.assertEqual(self.chamar({"pergunta": "resumo"})[0], 200)
        texto = self.mensagens()[1]["content"]
        self.assertNotIn("SEGREDO-B", texto)
        self.assertNotIn("sensor-b", texto)
        self.assertNotIn("-99", texto)  # leitura intrusa na partição do sensor da A
        self.assertNotIn("gestor@b.com", texto)
        dados = self.retrato()
        self.assertEqual(dados["empresa"], "Frutas do Vale")
        self.assertEqual([v["id"] for v in dados["veiculos"]], ["CT-001"])
        self.assertEqual({s["id"] for s in dados["sensores"]}, {"sensor-a", "sensor-a2"})
        self.assertEqual([v["origem"] for v in dados["viagens"]["emAndamento"]], ["Petrolina"])
        # Toda consulta por empresa levou a empresa do token.
        for nome in ("veiculos", "dispositivos", "viagens", "usuarios", "leituras"):
            for consulta in self.containers[nome].consultas:
                self.assertRegex(consulta, r"c\.empresaId = @e(mpresa)?\b", nome)

    def test_empresa_b_ve_so_a_b(self):
        r = ROTA(pedido({"pergunta": "resumo"}, "gestor@b.com", empresa="E-B"))
        self.assertEqual(r.status_code, 200)
        texto = self.mensagens()[1]["content"]
        self.assertNotIn("Frutas do Vale", texto)
        self.assertNotIn("sensor-a", texto)
        self.assertNotIn("Petrolina", texto)

    def test_gestor_ve_usuarios(self):
        self.chamar({"pergunta": "quem usa?"})
        dados = self.retrato()
        self.assertEqual(dados["usuarioLogado"], {"nome": "Gestor", "perfil": "gestor"})
        self.assertEqual([u["email"] for u in dados["usuarios"]],
                         ["gestor@a.com", "operador@a.com"])
        self.assertEqual(dados["totalUsuarios"], 2)
        self.assertEqual(dados["usuariosPorPerfil"], {"gestor": 1, "operador": 1})

    def test_operador_nao_ve_usuarios(self):
        status, _ = self.chamar({"pergunta": "quem usa?"}, email="operador@a.com",
                                perfil="operador")
        self.assertEqual(status, 200)
        dados = self.retrato()
        self.assertEqual(dados["usuarioLogado"]["perfil"], "operador")
        for chave in ("usuarios", "totalUsuarios", "usuariosPorPerfil"):
            self.assertNotIn(chave, dados)
        self.assertNotIn("gestor@a.com", self.mensagens()[1]["content"])
        self.assertEqual(self.containers["usuarios"].consultas, [])

    def test_sem_token_401(self):
        for email in (None, "fantasma@a.com"):
            r = ROTA(pedido({"pergunta": "oi"}, email))
            self.assertEqual(r.status_code, 401)
            self.assertEqual(json.loads(r.get_body()), {"erros": ["faça login para continuar"]})
        self.assertEqual(self.falso.chamadas, [])

    def test_validacao_400(self):
        status, corpo = self.chamar({"pergunta": ""})
        self.assertEqual(status, 400)
        self.assertIn("pergunta: obrigatória", corpo["erros"])
        status, corpo = self.chamar({"pergunta": "x" * 501})
        self.assertIn("pergunta: no máximo 500 caracteres", corpo["erros"])
        status, corpo = self.chamar({"pergunta": "oi", "historico": [{"papel": "system",
                                                                      "texto": "x"}]})
        self.assertIn("historico[0].papel: use usuario ou assistente", corpo["erros"])
        status, corpo = self.chamar(b"{nao e json")
        self.assertEqual((status, corpo), (400, {"erros": ["corpo não é JSON válido"]}))
        self.assertEqual(self.falso.chamadas, [])

    def test_limite_por_usuario(self):
        for _ in range(15):
            self.assertEqual(self.chamar({"pergunta": "oi"})[0], 200)
        status, corpo = self.chamar({"pergunta": "oi"})
        self.assertEqual((status, corpo),
                         (429, {"erros": ["muitas perguntas seguidas. Tente de novo em 1 min."]}))
        # Outro usuário (mesmo IP, mesma empresa) segue livre.
        self.assertEqual(self.chamar({"pergunta": "oi"}, email="operador@a.com",
                                     perfil="operador")[0], 200)

    def test_sem_configuracao_503(self):
        with mock.patch.dict(os.environ, {"AOAI_ENDPOINT": ""}):
            status, corpo = self.chamar({"pergunta": "oi"})
        self.assertEqual((status, corpo), (503, {"erros": ["assistente indisponível"]}))

    def test_falha_da_ia_503_sem_pergunta_no_log(self):
        self.falso._erro = TimeoutError("demorou")
        with self.assertLogs(level="WARNING") as log:
            status, corpo = self.chamar({"pergunta": "segredo da pergunta"})
        self.assertEqual((status, corpo), (503, {"erros": ["assistente indisponível"]}))
        self.assertNotIn("segredo da pergunta", "\n".join(log.output))

    def test_falha_do_banco_503(self):
        self.containers["veiculos"].query_items = mock.Mock(side_effect=RuntimeError("cosmos"))
        with self.assertLogs(level="WARNING"):
            status, _ = self.chamar({"pergunta": "oi"})
        self.assertEqual(status, 503)

    def test_recusa_zera_fontes(self):
        self.falso._texto = "[SEM_CONTEXTO] Só respondo sobre o ColdTrack."
        status, corpo = self.chamar({"pergunta": "receita de bolo?"})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["resposta"], "Só respondo sobre o ColdTrack.")
        self.assertEqual(corpo["fontes"], [])

    def test_resposta_vazia(self):
        self.falso._texto = None
        self.assertEqual(self.chamar({"pergunta": "oi"})[1]["resposta"], assistente.SEM_RESPOSTA)

    def test_base_vazia_mantem_dados(self):
        chat._base = []
        status, corpo = self.chamar({"pergunta": "oi"})
        self.assertEqual((status, corpo["fontes"]), (200, ["dados da empresa"]))
        self.assertEqual([c[0] for c in self.falso.chamadas], ["chat"])


class TestRetrato(BaseRota):
    def test_sensor_com_resumo_de_24h(self):
        self.chamar({"pergunta": "oi"})
        sensor = next(s for s in self.retrato()["sensores"] if s["id"] == "sensor-a")
        self.assertEqual(sensor["veiculo"], "CT-001")
        ultima = sensor["ultimaLeitura"]
        self.assertEqual((ultima["temperatura"], ultima["status"], ultima["rssi"]),
                         ("12.0 °C", "NORMAL", "-60 dBm"))
        self.assertNotIn("semSinalHa", ultima)
        resumo = sensor["ultimas24h"]
        # A leitura de 30 h atrás fica fora do resumo.
        self.assertEqual(resumo["leituras"], 3)
        self.assertEqual((resumo["tempMin"], resumo["tempMax"], resumo["tempMedia"]),
                         ("12.0 °C", "18.5 °C", "15.0 °C"))
        self.assertEqual((resumo["emAtencao"], resumo["emCritico"]), (1, 1))
        self.assertEqual(resumo["ultimaForaDaFaixa"], assistente.hora_local(iso(hours=2)))

    def test_sensor_sem_sinal(self):
        self.chamar({"pergunta": "oi"})
        sensor = next(s for s in self.retrato()["sensores"] if s["id"] == "sensor-a2")
        self.assertIsNone(sensor["veiculo"])
        self.assertEqual(sensor["ultimaLeitura"]["semSinalHa"], "2 dias")
        self.assertIsNone(sensor["ultimaLeitura"]["rssi"])
        self.assertEqual(sensor["ultimas24h"], {"leituras": 0})

    def test_viagens_e_perfis(self):
        self.chamar({"pergunta": "oi"})
        dados = self.retrato()
        viagens = dados["viagens"]
        self.assertEqual(viagens["totalEmAndamento"], 1)
        self.assertEqual(viagens["ultimasFinalizadas"][0]["destino"], "Salvador")
        self.assertEqual({p["id"] for p in dados["perfisDeCarga"]},
                         {"demonstrativo", "manga", "uva"})
        manga = next(p for p in dados["perfisDeCarga"] if p["id"] == "manga")
        self.assertEqual(manga["normal"], "10.0 a 13.0 °C")


class FonteFalsa:
    def __init__(self, veiculos=0, sensores=0, viagens=0, usuarios=0, texto=""):
        self.n = SimpleNamespace(veiculos=veiculos, sensores=sensores, viagens=viagens,
                                 usuarios=usuarios)
        self.texto = texto
        self.pedidas = []

    def empresa(self):
        return {"nome": "Teste"}

    def veiculos(self):
        return [{"id": f"CT-{i:03}", "tipo": "Caminhão " + self.texto, "perfil": "manga",
                 "deviceId": f"s{i}"} for i in range(self.n.veiculos)]

    def dispositivos(self):
        return [{"id": f"s{i}", "descricao": self.texto, "criadoEm": iso(days=i)}
                for i in range(self.n.sensores)]

    def viagens(self):
        return [{"id": f"V-{i}", "veiculo": "CT-001", "origem": "A" + self.texto,
                 "destino": "B", "carga": "Manga", "inicio": iso(days=i + 2),
                 "fim": iso(days=i + 1)} for i in range(self.n.viagens)]

    def usuarios(self):
        return [{"id": f"u{i}@x.com", "nome": "U" + self.texto, "perfil": "operador"}
                for i in range(self.n.usuarios)]

    def leituras(self, device, limite, desde=None):
        self.pedidas.append(device)
        return []


class TestLimites(unittest.TestCase):
    def test_listas_com_teto(self):
        fonte = FonteFalsa(veiculos=50, sensores=15, viagens=20, usuarios=40)
        dados = assistente.montar_dados({"nome": "G", "perfil": "gestor"}, fonte, AGORA)
        self.assertEqual(len(dados["veiculos"]), assistente.VEICULOS_MAX)
        self.assertEqual(dados["totalVeiculos"], 50)
        self.assertEqual(len(dados["sensores"]), assistente.DISPOSITIVOS_MAX)
        self.assertEqual(dados["totalSensores"], 15)
        # No máximo 2 consultas de leitura por sensor (24 h e, se vazia, a última).
        self.assertLessEqual(len(fonte.pedidas), 2 * assistente.DISPOSITIVOS_MAX)
        self.assertEqual(len(dados["viagens"]["ultimasFinalizadas"]), 5)
        self.assertEqual(dados["viagens"]["totalFinalizadas"], 20)
        self.assertEqual(len(dados["usuarios"]), assistente.USUARIOS_MAX)
        self.assertEqual(dados["totalUsuarios"], 40)
        self.assertNotIn("listasCortadas", dados)

    def test_retrato_grande_encolhe(self):
        fonte = FonteFalsa(veiculos=50, sensores=15, viagens=20, usuarios=40, texto="x" * 300)
        dados = assistente.montar_dados({"nome": "G", "perfil": "gestor"}, fonte, AGORA)
        self.assertLessEqual(len(assistente.serializar(dados)),
                             assistente.DADOS_MAX_CARACTERES)
        self.assertTrue(dados["listasCortadas"])
        self.assertEqual(dados["totalVeiculos"], 50)
        self.assertGreaterEqual(len(dados["sensores"]), 1)


class TestHorario(unittest.TestCase):
    def test_hora_de_pernambuco(self):
        self.assertEqual(assistente.hora_local("2026-11-08T17:05:00+00:00"), "08/11/2026 14:05")
        self.assertEqual(assistente.hora_local("2026-11-09T01:00:00Z"), "08/11/2026 22:00")
        self.assertIsNone(assistente.hora_local(None))
        self.assertIsNone(assistente.hora_local("ontem"))

    def test_duracao(self):
        self.assertEqual(assistente.duracao(30), "0 min")
        self.assertEqual(assistente.duracao(11 * 60), "11 min")
        self.assertEqual(assistente.duracao(125 * 60), "2 h 5 min")
        self.assertEqual(assistente.duracao(3 * 86400), "3 dias")

    def test_sistema(self):
        for trecho in ("Dashboard", "Veículos", "Sensores", "Viagens", "Alertas", "Relatórios",
                       "Configurações", "DADOS DA EMPRESA", "não executa", "gestor",
                       "operador", "[SEM_CONTEXTO]", "Nunca revele", "outras empresas"):
            self.assertIn(trecho, assistente.SISTEMA)


if __name__ == "__main__":
    unittest.main()
