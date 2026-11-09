"""Especificação OpenAPI (openapi.json) e rotas /docs e /openapi.json.

openapi-spec-validator é dependência só de teste (requirements-dev.txt).
Rodar: python -m unittest -v
"""

import json
import os
import re
import unittest

import azure.functions as func
from openapi_spec_validator import validate

import function_app

PASTA = os.path.dirname(os.path.abspath(__file__))
METODOS = {"get", "post", "put", "delete", "patch", "head", "options"}


def carregar_spec():
    with open(os.path.join(PASTA, "openapi.json"), encoding="utf-8") as f:
        return json.load(f)


def rotas_registradas():
    """{(caminho, metodo)} das rotas da Function, abrindo `x/{id?}` em `/x` e `/x/{id}`."""
    rotas = {}
    for funcao in function_app.app.get_functions():
        gatilho = funcao.get_trigger()
        metodos = {str(getattr(m, "value", m)).lower() for m in gatilho.methods}
        rotas["/" + re.sub(r"/\{(\w+)\?\}$", "", gatilho.route)] = metodos
    return rotas


def rotas_da_spec(spec):
    """{caminho base: métodos}, juntando `/x` e `/x/{id}` no mesmo caminho base."""
    rotas = {}
    for caminho, item in spec["paths"].items():
        base = re.sub(r"/\{\w+\}$", "", caminho)
        rotas.setdefault(base, set()).update(m for m in item if m in METODOS)
    return rotas


def chamar(rota, url):
    funcao = rota.build().get_user_function()
    return funcao(func.HttpRequest(method="GET", url=url, body=b""))


class TestSpec(unittest.TestCase):
    def setUp(self):
        self.spec = carregar_spec()

    def test_spec_valida(self):
        validate(self.spec)
        self.assertEqual(self.spec["openapi"], "3.0.3")

    def test_toda_rota_da_function_esta_na_spec_e_vice_versa(self):
        self.assertEqual(rotas_registradas(), rotas_da_spec(self.spec))

    def test_rota_com_id_opcional_documenta_lista_e_item(self):
        for base in ("/dispositivos", "/veiculos", "/viagens", "/usuarios"):
            self.assertIn(base + "/{id}", self.spec["paths"])

    def test_toda_operacao_documentada(self):
        for caminho, item in self.spec["paths"].items():
            for metodo, op in item.items():
                if metodo not in METODOS:
                    continue
                with self.subTest(rota=f"{metodo.upper()} {caminho}"):
                    self.assertTrue(op.get("summary"))
                    self.assertIn("Quem pode chamar", op.get("description", ""))
                    self.assertIn("security", op)
                    self.assertTrue(op.get("tags"))

    def test_seguranca_por_rota(self):
        paths = self.spec["paths"]
        self.assertEqual(paths["/telemetria"]["post"]["security"], [{"dispositivo": []}])
        for publica in (("/login", "post"), ("/empresas", "post"), ("/perfis", "get"),
                        ("/chat", "post"), ("/docs", "get"), ("/openapi.json", "get")):
            self.assertEqual(paths[publica[0]][publica[1]]["security"], [], publica)
        self.assertEqual(paths["/eu"]["get"]["security"], [{"bearerAuth": []}])
        esquema = self.spec["components"]["securitySchemes"]["dispositivo"]
        self.assertEqual((esquema["in"], esquema["name"]), ("header", "x-device-key"))

    def test_sem_credencial_real(self):
        texto = json.dumps(self.spec, ensure_ascii=False)
        for proibido in ("AccountKey=", "COSMOS_CONNECTION", "JWT_SECRET", "sk-"):
            self.assertNotIn(proibido, texto)
        emails = set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", texto))
        self.assertTrue(all(e.endswith("@empresa-exemplo.com.br") for e in emails), emails)


class TestRotasDeDocumentacao(unittest.TestCase):
    def test_docs_html_com_cdn_e_csp(self):
        r = chamar(function_app.docs, "/api/docs")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.mimetype.startswith("text/html"))
        html = r.get_body().decode()
        self.assertIn("cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js", html)
        self.assertIn('integrity="sha384-', html)
        self.assertIn('url: "openapi.json"', html)
        self.assertIn("ColdTrack API — documentação", html)
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("script-src https://cdn.jsdelivr.net 'sha256-", csp)
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertIn("connect-src 'self' https://func-coldtrack-7319.azurewebsites.net", csp)
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("Referrer-Policy", r.headers)

    def test_hash_da_csp_bate_com_o_script_inline(self):
        import base64
        import hashlib
        html = function_app.DOCS_HTML
        inline = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        esperado = base64.b64encode(hashlib.sha256(inline.encode()).digest()).decode()
        self.assertIn(f"'sha256-{esperado}'", function_app.DOCS_CSP)

    def test_openapi_json(self):
        r = chamar(function_app.openapi, "/api/openapi.json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "application/json")
        self.assertEqual(r.headers["Cache-Control"], "public, max-age=300")
        self.assertEqual(json.loads(r.get_body())["info"]["title"], "ColdTrack API")


if __name__ == "__main__":
    unittest.main()
