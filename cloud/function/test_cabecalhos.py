"""Cabeçalhos de segurança nas respostas JSON da API."""

import json
import unittest

import function_app


class TestCabecalhos(unittest.TestCase):
    def test_resposta_json_leva_cabecalhos_de_seguranca(self):
        r = function_app.resposta({"ok": True}, 201)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(json.loads(r.get_body()), {"ok": True})
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["Cache-Control"], "no-store")
        self.assertIn("max-age=", r.headers["Strict-Transport-Security"])
        self.assertEqual(r.headers["Referrer-Policy"], "no-referrer")

    def test_erro_tambem_leva(self):
        r = function_app.resposta({"erros": ["x"]}, 400)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
