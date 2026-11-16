"""Testes da rota GET /api/health (estado do serviço e do banco)."""

import json
import unittest
from unittest import mock

import azure.functions as func

import function_app

HEALTH = function_app.health.build().get_user_function()


def chamar():
    return HEALTH(func.HttpRequest(method="GET", url="/api/health", body=b""))


class ContainerSaudavel:
    def __init__(self):
        self.consultas = []

    def query_items(self, query, **kwargs):
        self.consultas.append((query, kwargs))
        return iter([{"id": "x"}])


class ContainerFora:
    def query_items(self, query, **kwargs):
        raise RuntimeError("sem conexão com o banco, chave=segredo-que-nao-pode-vazar")


class TestHealth(unittest.TestCase):
    def test_banco_respondendo_devolve_200(self):
        falso = ContainerSaudavel()
        with mock.patch.object(function_app, "container", return_value=falso):
            r = chamar()
        corpo = json.loads(r.get_body())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/json")
        self.assertEqual(corpo["status"], "ok")
        self.assertEqual(corpo["banco"], "ok")
        self.assertTrue(corpo["horario"].endswith("+00:00"))
        self.assertEqual(len(falso.consultas), 1)

    def test_banco_fora_devolve_503_sem_vazar_o_erro(self):
        with mock.patch.object(function_app, "container", return_value=ContainerFora()), \
                self.assertLogs(level="ERROR"):
            r = chamar()
        texto = r.get_body().decode()
        corpo = json.loads(texto)
        self.assertEqual(r.status_code, 503)
        self.assertEqual(corpo["status"], "degradado")
        self.assertEqual(corpo["banco"], "indisponivel")
        self.assertNotIn("segredo", texto)
        self.assertNotIn("conexão", texto)

    def test_nao_pede_autenticacao(self):
        # Sem Authorization nem chave de dispositivo e com o banco no ar: responde 200.
        with mock.patch.object(function_app, "container", return_value=ContainerSaudavel()):
            self.assertEqual(chamar().status_code, 200)


if __name__ == "__main__":
    unittest.main()
