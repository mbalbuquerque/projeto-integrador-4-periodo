"""POST /api/heartbeat e o estado do sensor em GET /dispositivos e GET /motorista (R7).

Rodar: python -m pytest test_heartbeat.py
"""

import unittest
from datetime import datetime, timedelta, timezone

import function_app
from contrato import validar_heartbeat
from test_motorista import MOTORISTA, BaseMotorista
from test_rotas import DISPOSITIVOS, TELEMETRIA, BaseRotas

HEARTBEAT = function_app.heartbeat.build().get_user_function()


def iso(delta_s):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_s)).isoformat()


def corpo(**extra):
    base = {"deviceId": "dev-livre", "motivo": "sensor_falha", "fw": "2026.11.17.2"}
    base.update(extra)
    return base


class TestContratoHeartbeat(unittest.TestCase):
    def test_minimo_valido(self):
        self.assertEqual(validar_heartbeat(corpo()), [])

    def test_completo_valido(self):
        self.assertEqual(validar_heartbeat(corpo(rssi=-60, seq=42)), [])
        self.assertEqual(validar_heartbeat(corpo(rssi=None)), [])

    def test_nao_objeto(self):
        self.assertEqual(validar_heartbeat([1]), ["corpo deve ser um objeto JSON"])

    def test_campos_invalidos(self):
        erros = validar_heartbeat({"deviceId": "x", "motivo": "outro", "fw": "",
                                   "rssi": 5, "seq": 0, "temperatura": 1})
        self.assertEqual(len(erros), 6)
        self.assertTrue(erros[0].startswith("deviceId"))
        self.assertIn("motivo: use sensor_falha", erros)
        self.assertTrue(any(e.startswith("fw") for e in erros))
        self.assertTrue(any(e.startswith("rssi") for e in erros))
        self.assertTrue(any(e.startswith("seq") for e in erros))
        self.assertIn("campos não previstos: temperatura", erros)

    def test_tipos_trocados(self):
        erros = validar_heartbeat(corpo(rssi=True, seq=True, fw=12))
        self.assertEqual(len(erros), 3)
        self.assertTrue(validar_heartbeat(corpo(rssi=-60.5)))
        self.assertTrue(validar_heartbeat(corpo(fw="a b")))


class BaseHeartbeat(BaseRotas):
    def bater(self, dados=None, chave=None):
        chave = self.chave_dev2 if chave is None else chave
        return self.chamar(HEARTBEAT, "POST", "/api/heartbeat", dados or corpo(),
                           headers={"x-device-key": chave})

    def disp(self, device="dev-livre"):
        return self.containers["dispositivos"].read_item(device, partition_key=device)

    def listar(self):
        status, resp = self.chamar(DISPOSITIVOS, "GET", "/api/dispositivos",
                                   email="operador@a.com")
        self.assertEqual(status, 200)
        return {d["id"]: d for d in resp["dispositivos"]}


class TestRotaHeartbeat(BaseHeartbeat):
    def test_grava_estado_sem_criar_leitura(self):
        leituras_antes = len(self.containers["leituras"].itens)
        status, resp = self.bater(corpo(rssi=-61, seq=7))
        self.assertEqual(status, 200)
        self.assertEqual(resp["sensor"], "falha")
        self.assertEqual(len(self.containers["leituras"].itens), leituras_antes)
        d = self.disp()
        self.assertEqual(d["heartbeatMotivo"], "sensor_falha")
        self.assertEqual(d["sensorFalhaDesde"], resp["sensorFalhaDesde"])
        self.assertEqual(d["heartbeatEm"], resp["sensorFalhaDesde"])
        self.assertEqual(d["fw"], "2026.11.17.2")
        self.assertEqual(d["heartbeatRssi"], -61)
        self.assertEqual(d["ultimaSeq"], 7)
        # A chave não muda com o heartbeat.
        self.assertEqual(d["chaveHash"], self.chave_hash_dev2)

    def test_sem_seq_nao_grava_ultima_seq(self):
        self.assertEqual(self.bater()[0], 200)
        self.assertNotIn("ultimaSeq", self.disp())
        self.assertIsNone(self.disp()["heartbeatRssi"])

    def test_falha_seguida_mantem_o_inicio(self):
        _, primeiro = self.bater()
        inicio = primeiro["sensorFalhaDesde"]
        _, segundo = self.bater()
        self.assertEqual(segundo["sensorFalhaDesde"], inicio)
        self.assertGreaterEqual(self.disp()["heartbeatEm"], inicio)

    def test_leitura_valida_no_meio_reinicia_a_falha(self):
        self.containers["dispositivos"]._achar("dev-livre")["sensorFalhaDesde"] = iso(-600)
        self.containers["leituras"].itens.append({
            "id": "dev-livre~9", "deviceId": "dev-livre", "empresaId": "E-A",
            "medidoEm": iso(-300), "recebidoEm": iso(-300)})
        _, resp = self.bater()
        self.assertGreater(resp["sensorFalhaDesde"], iso(-60))

    def test_falha_antiga_sem_leitura_depois_continua(self):
        antigo = iso(-600)
        self.containers["dispositivos"]._achar("dev-livre")["sensorFalhaDesde"] = antigo
        self.containers["leituras"].itens.append({
            "id": "dev-livre~8", "deviceId": "dev-livre", "empresaId": "E-A",
            "medidoEm": iso(-900), "recebidoEm": iso(-900)})
        _, resp = self.bater()
        self.assertEqual(resp["sensorFalhaDesde"], antigo)

    def test_inicio_ilegivel_recomeca(self):
        self.containers["dispositivos"]._achar("dev-livre")["sensorFalhaDesde"] = "quebrado"
        _, resp = self.bater()
        self.assertNotEqual(resp["sensorFalhaDesde"], "quebrado")

    def test_corpo_nao_json(self):
        status, resp = self.chamar(HEARTBEAT, "POST", "/api/heartbeat", corpo_raw=b"x",
                                   headers={"x-device-key": self.chave_dev2})
        self.assertEqual(status, 400)

    def test_corpo_invalido(self):
        status, resp = self.bater({"deviceId": "dev-livre", "motivo": "x", "fw": "1"})
        self.assertEqual(status, 400)
        self.assertIn("motivo: use sensor_falha", resp["erros"])

    def test_chave_errada_401(self):
        status, _ = self.bater(chave="chave-errada")
        self.assertEqual(status, 401)
        self.assertNotIn("heartbeatEm", self.disp())

    def test_chave_de_outro_sensor_401(self):
        # chave do dev-01 não vale para o dev-livre
        self.assertEqual(self.bater(chave=self.chave_dev1)[0], 401)

    def test_dispositivo_inexistente_401(self):
        self.assertEqual(self.bater(corpo(deviceId="nao-existe"))[0], 401)

    def test_device_id_em_maiusculas(self):
        self.assertEqual(self.bater(corpo(deviceId="DEV-LIVRE"))[0], 200)

    def test_limite_por_minuto(self):
        for _ in range(function_app.HEARTBEAT_POR_MINUTO):
            self.assertEqual(self.bater()[0], 200)
        status, resp = self.bater()
        self.assertEqual(status, 429)
        self.assertIn("heartbeats", resp["erros"][0])


class TestEstadoEmDispositivos(BaseHeartbeat):
    def test_heartbeat_deixa_online_e_em_falha(self):
        self.bater()
        dev = self.listar()["dev-livre"]
        self.assertTrue(dev["online"])
        self.assertEqual(dev["sensor"], "falha")
        self.assertIsNotNone(dev["sensorFalhaDesde"])
        self.assertEqual(dev["ultimoContato"], self.disp()["heartbeatEm"])
        # Campos internos do heartbeat não vazam na lista.
        self.assertNotIn("heartbeatEm", dev)
        self.assertNotIn("heartbeatMotivo", dev)
        self.assertNotIn("chaveHash", dev)

    def test_leitura_valida_depois_encerra_a_falha(self):
        self.bater()
        self.containers["leituras"].itens.append({
            "id": "dev-livre~5", "deviceId": "dev-livre", "empresaId": "E-A",
            "medidoEm": iso(5), "recebidoEm": iso(5)})
        dev = self.listar()["dev-livre"]
        self.assertEqual(dev["sensor"], "ok")
        self.assertIsNone(dev["sensorFalhaDesde"])
        self.assertTrue(dev["online"])

    def test_telemetria_real_depois_do_heartbeat_encerra_a_falha(self):
        self.bater()
        status, _ = self.chamar(TELEMETRIA, "POST", "/api/telemetria",
                                {"deviceId": "dev-livre", "temperatura": 12.0,
                                 "umidade": 80.0, "rssi": -60},
                                headers={"x-device-key": self.chave_dev2})
        self.assertEqual(status, 201)
        self.assertEqual(self.listar()["dev-livre"]["sensor"], "ok")

    def test_falha_antiga_aparece_offline_com_falha(self):
        d = self.containers["dispositivos"]._achar("dev-livre")
        d.update({"heartbeatEm": iso(-600), "heartbeatMotivo": "sensor_falha",
                  "sensorFalhaDesde": iso(-1200)})
        dev = self.listar()["dev-livre"]
        self.assertFalse(dev["online"])
        self.assertEqual(dev["sensor"], "falha")

    def test_sensor_ok_e_nunca_falou(self):
        lista = self.listar()
        self.assertEqual(lista["dev-01"]["sensor"], "ok")
        self.assertIsNone(lista["dev-01"]["sensorFalhaDesde"])
        self.assertIsNone(lista["dev-livre2"]["sensor"])
        self.assertIsNone(lista["dev-livre2"]["ultimoContato"])

    def test_heartbeat_com_horario_ilegivel_e_ignorado(self):
        d = self.containers["dispositivos"]._achar("dev-01")
        d.update({"heartbeatEm": "quebrado", "heartbeatMotivo": "sensor_falha"})
        dev = self.listar()["dev-01"]
        self.assertEqual(dev["sensor"], "ok")
        self.assertEqual(dev["ultimoContato"], "2026-05-10T10:00:01+00:00")


class TestEstadoNoMotorista(BaseMotorista):
    def ver(self):
        status, resp = self.chamar(MOTORISTA, "GET", "/api/motorista", email="moto@a.com")
        self.assertEqual(status, 200)
        return resp

    def test_sensor_ok(self):
        resp = self.ver()
        self.assertEqual(resp["sensor"], "ok")
        self.assertIsNone(resp["sensorFalhaDesde"])

    def test_sensor_em_falha(self):
        desde = iso(-60)
        self.containers["dispositivos"]._achar("dev-livre").update(
            {"heartbeatEm": iso(-5), "heartbeatMotivo": "sensor_falha",
             "sensorFalhaDesde": desde})
        resp = self.ver()
        self.assertEqual(resp["sensor"], "falha")
        self.assertEqual(resp["sensorFalhaDesde"], desde)
        # A última leitura válida continua lá; status segue a regra de idade da leitura.
        self.assertIsNotNone(resp["leitura"])

    def test_dispositivo_de_outra_empresa_nao_expoe_estado(self):
        self.containers["veiculos"]._achar("E-A~CT-002")["deviceId"] = "dev-b"
        resp = self.ver()
        self.assertIsNone(resp["sensor"])
        self.assertIsNone(resp["sensorFalhaDesde"])


if __name__ == "__main__":
    unittest.main()
