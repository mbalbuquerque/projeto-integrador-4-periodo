"""Testes do perfil motorista e da rota GET /api/motorista (Cosmos falso).

Rodar: python -m pytest test_motorista.py
"""

import unittest
from datetime import datetime, timedelta, timezone

import function_app
from cadastros import validar_usuario, validar_vinculo
from test_rotas import SENHA, BaseRotas

MOTORISTA = function_app.motorista.build().get_user_function()
USUARIOS = function_app.usuarios.build().get_user_function()
LOGIN = function_app.login.build().get_user_function()
EU = function_app.eu.build().get_user_function()
SAIR = function_app.sair.build().get_user_function()
SENHA_ROTA = function_app.senha.build().get_user_function()

# Rotas do painel que o motorista NÃO pode chamar: (função, método, url, parâmetros da rota).
ROTAS_NEGADAS = [
    (function_app.leituras, "GET", "/api/leituras", {}),
    (function_app.predict, "GET", "/api/predict", {}),
    (function_app.assistente_painel, "POST", "/api/assistente", {}),
    (function_app.dispositivos, "GET", "/api/dispositivos", {}),
    (function_app.dispositivos, "POST", "/api/dispositivos", {}),
    (function_app.dispositivos, "PUT", "/api/dispositivos/dev-01", {"id": "dev-01"}),
    (function_app.dispositivos, "DELETE", "/api/dispositivos/dev-01", {"id": "dev-01"}),
    (function_app.veiculos, "GET", "/api/veiculos", {}),
    (function_app.veiculos, "POST", "/api/veiculos", {}),
    (function_app.veiculos, "PUT", "/api/veiculos/CAM-01", {"id": "CAM-01"}),
    (function_app.veiculos, "DELETE", "/api/veiculos/CAM-01", {"id": "CAM-01"}),
    (function_app.viagens, "GET", "/api/viagens", {}),
    (function_app.viagens, "POST", "/api/viagens", {}),
    (function_app.viagens, "PUT", "/api/viagens/V-001", {"id": "V-001"}),
    (function_app.viagens, "DELETE", "/api/viagens/V-001", {"id": "V-001"}),
    (function_app.usuarios, "GET", "/api/usuarios", {}),
    (function_app.usuarios, "POST", "/api/usuarios", {}),
    (function_app.usuarios, "PUT", "/api/usuarios/operador@a.com", {"id": "operador@a.com"}),
    (function_app.usuarios, "DELETE", "/api/usuarios/operador@a.com", {"id": "operador@a.com"}),
]


def iso(delta_s):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).isoformat()


class BaseMotorista(BaseRotas):
    def setUp(self):
        super().setUp()
        c = self.containers
        c["usuarios"].itens += [
            {"id": "moto@a.com", "nome": "Moto A", "perfil": "motorista", "veiculo": "CT-002",
             "empresaId": "E-A", "sessao": 0, "senhaHash": c["usuarios"].itens[0]["senhaHash"]},
        ]
        c["veiculos"].itens += [
            {"id": "E-A~CT-002", "empresaId": "E-A", "deviceId": "dev-livre",
             "tipo": "Baú refrigerado", "perfil": "manga"},
            {"id": "E-A~CT-SEM", "empresaId": "E-A", "deviceId": "dev-livre2",
             "tipo": "Van", "perfil": "uva"},
            {"id": "E-B~CT-B01", "empresaId": "E-B", "deviceId": "dev-b",
             "tipo": "Carreta", "perfil": "manga"},
        ]
        c["leituras"].itens += [
            {"id": "dev-livre~1", "deviceId": "dev-livre", "empresaId": "E-A",
             "temperatura": 11.8, "umidade": 87.0, "rssi": -60, "perfil": "manga",
             "status": "NORMAL", "medidoEm": iso(-600), "recebidoEm": iso(-600)},
            {"id": "dev-livre~2", "deviceId": "dev-livre", "empresaId": "E-A",
             "temperatura": 17.5, "umidade": 80.0, "rssi": -60, "perfil": "manga",
             "status": "CRITICO", "medidoEm": iso(-90), "recebidoEm": iso(-89)},
            # Leitura de outro sensor da mesma empresa: não pode aparecer.
            {"id": "dev-b~9", "deviceId": "dev-b", "empresaId": "E-B",
             "temperatura": 30.0, "umidade": 50.0, "rssi": -60, "perfil": "manga",
             "status": "CRITICO", "medidoEm": iso(-10), "recebidoEm": iso(-10)},
        ]
        c["viagens"].itens += [
            {"id": "E-A~V-ENC", "empresaId": "E-A", "veiculo": "CT-002", "origem": "Juazeiro",
             "destino": "Salvador", "carga": "Uva", "inicio": iso(-90000), "fim": iso(-3600)},
            {"id": "E-A~V-ATV", "empresaId": "E-A", "veiculo": "CT-002", "origem": "Petrolina",
             "destino": "Suape", "carga": "Manga Tommy", "inicio": iso(-7200), "fim": None},
            {"id": "E-A~V-FUT", "empresaId": "E-A", "veiculo": "CT-002", "origem": "Petrolina",
             "destino": "Recife", "carga": "Manga", "inicio": iso(86400), "fim": None},
        ]

    def painel(self, email="moto@a.com"):
        return self.chamar(MOTORISTA, "GET", "/api/motorista", email=email)


class TestRotaMotorista(BaseMotorista):
    def test_motorista_ve_so_o_proprio_veiculo(self):
        status, corpo = self.painel()
        self.assertEqual(status, 200)
        self.assertEqual(corpo["veiculo"], {"id": "CT-002", "tipo": "Baú refrigerado",
                                            "perfil": "manga"})
        self.assertEqual(corpo["faixa"], {"nome": "Manga", "min": 10.0, "max": 13.0,
                                          "margem": 3.0})
        self.assertEqual(corpo["leitura"]["temperatura"], 17.5)
        self.assertEqual(corpo["leitura"]["status"], "CRITICO")
        self.assertEqual(set(corpo["leitura"]), {"temperatura", "umidade", "status", "medidoEm"})
        self.assertEqual(corpo["status"], "CRITICO")
        self.assertEqual(corpo["minutosSemLeitura"], 1)
        self.assertEqual(corpo["viagem"]["origem"], "Petrolina")
        self.assertEqual(corpo["viagem"]["destino"], "Suape")
        self.assertIsNone(corpo["viagem"]["fim"])

    def test_historico_da_ultima_hora_do_mais_antigo_ao_mais_novo(self):
        self.containers["leituras"].itens.append(
            {"id": "dev-livre~0", "deviceId": "dev-livre", "empresaId": "E-A",
             "temperatura": 9.0, "umidade": 90.0, "rssi": -60, "perfil": "manga",
             "status": "ATENCAO", "medidoEm": iso(-7200), "recebidoEm": iso(-7200)})
        status, corpo = self.painel()
        self.assertEqual(status, 200)
        # Só a última hora (a de 2 h atrás fica fora), mais antiga primeiro, sem campos internos.
        self.assertEqual([h["temperatura"] for h in corpo["historico"]], [11.8, 17.5])
        self.assertEqual(set(corpo["historico"][0]), {"temperatura", "status", "medidoEm"})
        self.assertEqual(corpo["historico"][1]["status"], "CRITICO")

    def test_historico_vazio_sem_sensor(self):
        self.containers["usuarios"]._achar("moto@a.com")["veiculo"] = "CT-SEM"
        status, corpo = self.painel()
        self.assertEqual(status, 200)
        self.assertEqual(corpo["historico"], [])

    def test_operador_e_gestor_recebem_403(self):
        for email in ("operador@a.com", "gestor@a.com"):
            self.assertEqual(self.painel(email)[0], 403, email)

    def test_sem_token_401(self):
        self.assertEqual(self.chamar(MOTORISTA, "GET", "/api/motorista")[0], 401)

    def test_leitura_velha_vira_sem_leitura_e_mantem_o_valor(self):
        for i in self.containers["leituras"].itens:
            if i["id"] == "dev-livre~2":
                i["medidoEm"] = iso(-400)
        status, corpo = self.painel()
        self.assertEqual(status, 200)
        self.assertEqual(corpo["status"], "SEM_LEITURA")
        self.assertEqual(corpo["minutosSemLeitura"], 6)
        self.assertEqual(corpo["leitura"]["temperatura"], 17.5)

    def test_sensor_que_nunca_enviou(self):
        self.containers["usuarios"]._achar("moto@a.com")["veiculo"] = "CT-SEM"
        status, corpo = self.painel()
        self.assertEqual(status, 200)
        self.assertIsNone(corpo["leitura"])
        self.assertIsNone(corpo["minutosSemLeitura"])
        self.assertEqual(corpo["status"], "SEM_LEITURA")
        self.assertIsNone(corpo["viagem"])
        self.assertEqual(corpo["faixa"]["nome"], "Uva de mesa")

    def test_veiculo_sem_sensor(self):
        veiculo = self.containers["veiculos"]._achar("E-A~CT-002")
        del veiculo["deviceId"]
        status, corpo = self.painel()
        self.assertEqual((status, corpo["leitura"], corpo["status"]), (200, None, "SEM_LEITURA"))

    def test_horario_quebrado_no_banco_nao_derruba(self):
        for i in self.containers["leituras"].itens:
            if i["id"] == "dev-livre~2":
                i["medidoEm"] = "zzz"  # ordena depois das datas: vira a "mais nova"
        status, corpo = self.painel()
        self.assertEqual(status, 200)
        self.assertEqual(corpo["status"], "SEM_LEITURA")
        self.assertIsNone(corpo["minutosSemLeitura"])

    def test_viagem_encerrada_nao_conta(self):
        self.containers["viagens"].itens = [
            v for v in self.containers["viagens"].itens if v["id"] != "E-A~V-ATV"]
        self.assertIsNone(self.painel()[1]["viagem"])

    def test_viagem_com_fim_no_futuro_esta_em_curso(self):
        self.containers["viagens"]._achar("E-A~V-ATV")["fim"] = iso(3600)
        self.assertEqual(self.painel()[1]["viagem"]["destino"], "Suape")

    def test_duas_em_curso_vale_a_mais_recente(self):
        self.containers["viagens"].itens.append(
            {"id": "E-A~V-NOVA", "empresaId": "E-A", "veiculo": "CT-002", "origem": "Petrolina",
             "destino": "Fortaleza", "carga": "Uva", "inicio": iso(-60), "fim": None})
        self.containers["viagens"].itens.append(
            {"id": "E-A~V-RUIM", "empresaId": "E-A", "veiculo": "CT-002", "origem": "x",
             "destino": "y", "carga": "z", "inicio": "data-quebrada", "fim": None})
        self.assertEqual(self.painel()[1]["viagem"]["destino"], "Fortaleza")

    def test_viagem_de_outro_veiculo_nao_aparece(self):
        self.containers["viagens"]._achar("E-A~V-ATV")["veiculo"] = "CAM-01"
        self.assertIsNone(self.painel()[1]["viagem"])

    def test_veiculo_removido_da_frota_404(self):
        self.containers["veiculos"].delete_item("E-A~CT-002", "E-A~CT-002")
        status, corpo = self.painel()
        self.assertEqual(status, 404)
        self.assertIn("fale com o gestor", corpo["erros"][0])

    def test_motorista_sem_veiculo_no_cadastro_404(self):
        del self.containers["usuarios"]._achar("moto@a.com")["veiculo"]
        self.assertEqual(self.painel()[0], 404)

    def test_limite_por_minuto(self):
        for _ in range(function_app.MOTORISTA_POR_MINUTO):
            self.assertEqual(self.painel()[0], 200)
        status, corpo = self.painel()
        self.assertEqual(status, 429)
        self.assertIn("1 min", corpo["erros"][0])


class TestPerfilMotorista(BaseMotorista):
    def test_motorista_recebe_403_em_toda_rota_do_painel(self):
        for rota, metodo, url, params in ROTAS_NEGADAS:
            funcao = rota.build().get_user_function()
            with self.subTest(rota=f"{metodo} {url}"):
                status, corpo = self.chamar(funcao, metodo, url, corpo={},
                                            email="moto@a.com", route_params=params)
                self.assertEqual((status, corpo),
                                 (403, {"erros": ["seu perfil não tem acesso a esta ação"]}))

    def test_login_e_eu_devolvem_perfil_e_veiculo(self):
        status, corpo = self.chamar(LOGIN, "POST", "/api/login",
                                    {"email": "moto@a.com", "senha": SENHA})
        self.assertEqual(status, 200)
        self.assertEqual((corpo["usuario"]["perfil"], corpo["usuario"]["veiculo"]),
                         ("motorista", "CT-002"))
        status, corpo = self.chamar(EU, "GET", "/api/eu", email="moto@a.com")
        self.assertEqual((status, corpo["veiculo"], corpo["empresa"]), (200, "CT-002", "Frutas A"))
        # Operador continua sem o campo.
        self.assertNotIn("veiculo", self.chamar(EU, "GET", "/api/eu", email="operador@a.com")[1])

    def test_motorista_sai_e_troca_a_propria_senha(self):
        status, _ = self.chamar(SENHA_ROTA, "POST", "/api/senha",
                                {"atual": SENHA, "nova": "nova-senha-456"}, email="moto@a.com")
        self.assertEqual(status, 200)
        self.assertEqual(self.chamar(SAIR, "POST", "/api/sair", email="moto@a.com")[0], 204)

    def test_gestor_cria_motorista_com_veiculo(self):
        status, corpo = self.chamar(USUARIOS, "POST", "/api/usuarios",
                                    {"email": "Novo@A.com", "nome": "Novo", "perfil": "motorista",
                                     "veiculo": " ct-sem ", "senha": "senha-nova-123"},
                                    email="gestor@a.com")
        self.assertEqual(status, 201)
        self.assertEqual((corpo["perfil"], corpo["veiculo"]), ("motorista", "CT-SEM"))
        gravado = self.containers["usuarios"].read_item("novo@a.com", "novo@a.com")
        self.assertEqual(gravado["veiculo"], "CT-SEM")
        _, lista = self.chamar(USUARIOS, "GET", "/api/usuarios", email="gestor@a.com")
        self.assertIn({"id": "novo@a.com", "nome": "Novo", "perfil": "motorista",
                       "veiculo": "CT-SEM"}, lista["usuarios"])

    def criar(self, **campos):
        corpo = {"email": "x@a.com", "nome": "X", "perfil": "motorista",
                 "senha": "senha-nova-123", **campos}
        return self.chamar(USUARIOS, "POST", "/api/usuarios", corpo, email="gestor@a.com")

    def test_criar_motorista_recusa_veiculo_ruim(self):
        casos = {
            None: "veiculo: obrigatório para o perfil motorista",
            "CT-999": "veiculo: CT-999 não está cadastrado na frota",
            "CT-B01": "veiculo: CT-B01 não está cadastrado na frota",  # de outra empresa
            "c t/1": "veiculo: 3 a 20 letras, números ou hífen (ex.: CT-001)",
        }
        for veiculo, erro in casos.items():
            with self.subTest(veiculo=veiculo):
                campos = {} if veiculo is None else {"veiculo": veiculo}
                self.assertEqual(self.criar(**campos), (400, {"erros": [erro]}))
        self.assertNotIn("x@a.com", [u["id"] for u in self.containers["usuarios"].itens])

    def test_operador_com_veiculo_recusado(self):
        status, corpo = self.criar(perfil="operador", veiculo="CT-002")
        self.assertEqual((status, corpo),
                         (400, {"erros": ["veiculo: só o perfil motorista tem veículo vinculado"]}))

    def editar(self, email, corpo):
        return self.chamar(USUARIOS, "PUT", f"/api/usuarios/{email}", corpo,
                           email="gestor@a.com", route_params={"id": email})

    def test_gestor_troca_o_veiculo_do_motorista_sem_mexer_na_senha(self):
        antes = self.containers["usuarios"].read_item("moto@a.com", "moto@a.com")
        status, corpo = self.editar("moto@a.com", {"veiculo": "ct-sem"})
        self.assertEqual((status, corpo["veiculo"]), (200, "CT-SEM"))
        depois = self.containers["usuarios"].read_item("moto@a.com", "moto@a.com")
        self.assertEqual((depois["senhaHash"], depois["sessao"]),
                         (antes["senhaHash"], antes["sessao"]))
        self.assertEqual(self.painel()[1]["veiculo"]["id"], "CT-SEM")

    def test_troca_veiculo_e_senha_juntos(self):
        status, _ = self.editar("moto@a.com", {"veiculo": "CT-SEM", "senha": "outra-senha-123"})
        self.assertEqual(status, 200)
        doc = self.containers["usuarios"].read_item("moto@a.com", "moto@a.com")
        self.assertEqual((doc["veiculo"], doc["sessao"]), ("CT-SEM", 1))

    def test_troca_veiculo_recusada(self):
        self.assertEqual(self.editar("moto@a.com", {"veiculo": "CT-B01"}),
                         (400, {"erros": ["veiculo: CT-B01 não está cadastrado na frota"]}))
        self.assertEqual(self.editar("moto@a.com", {"veiculo": ""}),
                         (400, {"erros": ["veiculo: obrigatório para o perfil motorista"]}))
        self.assertEqual(self.editar("operador@a.com", {"veiculo": "CT-002"}),
                         (400, {"erros": ["veiculo: só o perfil motorista tem veículo vinculado"]}))
        self.assertEqual(self.containers["usuarios"].read_item("moto@a.com", "x")["veiculo"],
                         "CT-002")

    def test_put_sem_campo_pede_senha(self):
        self.assertEqual(self.editar("moto@a.com", [1, 2]),
                         (400, {"erros": ["senha: no mínimo 8 caracteres"]}))


class TestValidarVinculo(unittest.TestCase):
    def test_regras(self):
        erros = []
        self.assertEqual(validar_vinculo({"veiculo": "ct-001"}, "motorista", erros), "CT-001")
        self.assertEqual(erros, [])
        self.assertIsNone(validar_vinculo({"veiculo": 12}, "motorista", erros))
        self.assertEqual(erros, ["veiculo: obrigatório para o perfil motorista"])
        erros = []
        self.assertIsNone(validar_vinculo({"veiculo": "  "}, "gestor", erros))
        self.assertEqual(erros, [])

    def test_validar_usuario_motorista(self):
        erros, doc = validar_usuario({"email": "m@a.com", "nome": "M", "perfil": "motorista",
                                      "veiculo": "CT-001", "senha": "12345678"})
        self.assertEqual((erros, doc["veiculo"]), ([], "CT-001"))
        erros, doc = validar_usuario({"email": "m@a.com", "nome": "M", "perfil": "operador",
                                      "senha": "12345678"})
        self.assertNotIn("veiculo", doc)


if __name__ == "__main__":
    unittest.main()
