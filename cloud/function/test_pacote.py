"""Confere a lista de arquivos publicados (pacote.txt) contra a pasta da API."""

import os
import unittest

PASTA = os.path.dirname(os.path.abspath(__file__))


def ler_pacote():
    with open(os.path.join(PASTA, "pacote.txt"), encoding="utf-8") as f:
        return [linha.strip() for linha in f
                if linha.strip() and not linha.lstrip().startswith("#")]


class TestPacote(unittest.TestCase):
    def test_arquivos_existem(self):
        for nome in ler_pacote():
            self.assertTrue(os.path.isfile(os.path.join(PASTA, nome)), nome)

    def test_essenciais(self):
        pacote = set(ler_pacote())
        for nome in ("function_app.py", "host.json", "requirements.txt"):
            self.assertIn(nome, pacote)

    def test_todo_modulo_da_api_publicado(self):
        # Modulo novo na raiz que nao entra no pacote quebra o import na nuvem.
        pacote = set(ler_pacote())
        modulos = {n for n in os.listdir(PASTA)
                   if n.endswith(".py") and not n.startswith("test_")}
        self.assertEqual(modulos - pacote, set())

    def test_base_do_chat_publicada(self):
        # chat.py le a base do disco: sem ela no pacote, a rota /chat quebra na nuvem.
        self.assertIn("base_chat.json", set(ler_pacote()))

    def test_nada_de_teste_ou_script_publicado(self):
        for nome in ler_pacote():
            self.assertFalse(nome.startswith(("test_", "scripts/")), nome)


if __name__ == "__main__":
    unittest.main()
