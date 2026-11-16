"""Último contato e status online/offline de cada sensor em GET /api/dispositivos."""

from datetime import datetime, timedelta, timezone

import function_app
from test_rotas import DISPOSITIVOS, BaseRotas


def iso(atraso_s):
    return (datetime.now(timezone.utc) - timedelta(seconds=atraso_s)).isoformat()


class TestOnline(BaseRotas):
    def listar(self):
        status, corpo = self.chamar(DISPOSITIVOS, "GET", "/api/dispositivos",
                                    email="operador@a.com")
        self.assertEqual(status, 200)
        return {d["id"]: d for d in corpo["dispositivos"]}

    def test_sensor_com_leitura_antiga_esta_offline(self):
        dev = self.listar()["dev-01"]
        self.assertFalse(dev["online"])
        self.assertEqual(dev["ultimoContato"], "2026-05-10T10:00:01+00:00")

    def test_sensor_com_leitura_recente_esta_online(self):
        self.containers["leituras"].itens.append({
            "id": "dev-livre~1", "deviceId": "dev-livre", "empresaId": "E-A",
            "medidoEm": iso(10), "recebidoEm": iso(10)})
        dev = self.listar()["dev-livre"]
        self.assertTrue(dev["online"])
        self.assertIsNotNone(dev["ultimoContato"])

    def test_limite_de_120_segundos(self):
        self.containers["leituras"].itens.append({
            "id": "dev-livre~2", "deviceId": "dev-livre", "empresaId": "E-A",
            "medidoEm": iso(function_app.LIMITE_ONLINE_S + 30),
            "recebidoEm": iso(function_app.LIMITE_ONLINE_S + 30)})
        self.assertFalse(self.listar()["dev-livre"]["online"])

    def test_sensor_que_nunca_enviou(self):
        dev = self.listar()["dev-livre2"]
        self.assertFalse(dev["online"])
        self.assertIsNone(dev["ultimoContato"])

    def test_horario_ilegivel_conta_como_offline(self):
        self.containers["leituras"].itens.append({
            "id": "dev-livre~3", "deviceId": "dev-livre", "empresaId": "E-A",
            "medidoEm": iso(5), "recebidoEm": "isto-nao-e-data"})
        self.assertFalse(self.listar()["dev-livre"]["online"])

    def test_sensor_de_outra_empresa_nao_aparece(self):
        self.assertNotIn("dev-b", self.listar())
