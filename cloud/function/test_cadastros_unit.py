"""Testes unitários puros (sem mocks) para validação de cadastros (cadastros.py)."""

import unittest
from datetime import timezone

from cadastros import (
    _data,
    _senha,
    _texto,
    validar_dispositivo,
    validar_empresa,
    validar_troca_senha,
    validar_usuario,
    validar_veiculo,
    validar_viagem,
)


class TestCadastrosPuro(unittest.TestCase):
    def test_texto_auxiliar(self):
        erros = []
        # Opcional vazio ou None retorna None sem erro
        self.assertIsNone(_texto({"nome": ""}, "nome", 10, erros, obrigatorio=False))
        self.assertIsNone(_texto({"nome": "   "}, "nome", 10, erros, obrigatorio=False))
        self.assertIsNone(_texto({}, "nome", 10, erros, obrigatorio=False))
        self.assertEqual(erros, [])

        # Obrigatório ausente ou vazio
        self.assertIsNone(_texto({}, "nome", 10, erros, obrigatorio=True))
        self.assertIsNone(_texto({"nome": "  "}, "nome", 10, erros, obrigatorio=True))
        self.assertIsNone(_texto({"nome": 123}, "nome", 10, erros, obrigatorio=True))
        self.assertEqual(len(erros), 3)

        # Excede tamanho máximo
        erros_tam = []
        res = _texto({"nome": "abcdefghijk"}, "nome", 5, erros_tam)
        self.assertEqual(res, "abcdefghijk")
        self.assertIn("nome: no máximo 5 caracteres", erros_tam)

        # Sucesso
        erros_ok = []
        self.assertEqual(_texto({"nome": "  teste  "}, "nome", 10, erros_ok), "teste")
        self.assertEqual(erros_ok, [])

    def test_data_auxiliar(self):
        erros = []
        # Opcional vazio
        self.assertIsNone(_data({}, "data", erros, obrigatorio=False))
        self.assertIsNone(_data({"data": ""}, "data", erros, obrigatorio=False))
        self.assertEqual(erros, [])

        # Data inválida
        self.assertIsNone(_data({"data": "invalida"}, "data", erros))
        self.assertIn("data: data e hora inválidas (use ISO 8601)", erros)

        # Data sem fuso horário
        erros_fuso = []
        self.assertIsNone(_data({"data": "2026-05-10T12:00:00"}, "data", erros_fuso))
        self.assertIn("data: informe o fuso horário", erros_fuso)

        # Sucesso com ISO e Z
        erros_ok = []
        dt = _data({"data": "2026-05-10T12:00:00Z"}, "data", erros_ok)
        self.assertEqual(dt.tzinfo, timezone.utc)
        self.assertEqual(erros_ok, [])

    def test_senha_auxiliar(self):
        erros = []
        self.assertIsNone(_senha({"senha": "curta"}, "senha", erros))
        self.assertIsNone(_senha({"senha": 12345678}, "senha", erros))
        self.assertIn("senha: no mínimo 8 caracteres", erros)

        erros_longa = []
        self.assertIsNone(_senha({"senha": "a" * 129}, "senha", erros_longa))
        self.assertIn("senha: no máximo 128 caracteres", erros_longa)

        erros_ok = []
        self.assertEqual(_senha({"senha": "senha-valida-123"}, "senha", erros_ok),
                         "senha-valida-123")
        self.assertEqual(erros_ok, [])

    def test_validar_usuario_bordas(self):
        # Não objeto
        erros, doc = validar_usuario("não dict")
        self.assertEqual(erros, ["corpo deve ser um objeto JSON"])
        self.assertIsNone(doc)

        # Email inválido
        erros, _ = validar_usuario({"email": "email_sem_arroba", "nome": "Ana",
                                    "perfil": "gestor", "senha": "senha-valida-123"})
        self.assertIn("email: formato inválido", erros)

        # Perfil inválido
        erros, _ = validar_usuario({"email": "ana@a.com", "nome": "Ana",
                                    "perfil": "invalido", "senha": "senha-valida-123"})
        self.assertIn("perfil: use operador ou gestor", erros)

    def test_validar_empresa_bordas(self):
        erros, doc = validar_empresa([])
        self.assertEqual(erros, ["corpo deve ser um objeto JSON"])
        self.assertIsNone(doc)

        erros, doc = validar_empresa({"empresa": "", "email": "a@a.com", "nome": "A",
                                      "senha": "123"})
        self.assertTrue(len(erros) >= 2)
        self.assertIsNone(doc)

    def test_validar_troca_senha_bordas(self):
        erros, doc = validar_troca_senha(None)
        self.assertEqual(erros, ["corpo deve ser um objeto JSON"])
        self.assertIsNone(doc)

        erros, _ = validar_troca_senha({"atual": "", "nova": "nova-senha-123"})
        self.assertIn("atual: informe a senha atual", erros)

        erros, _ = validar_troca_senha({"atual": "mesma-senha-123", "nova": "mesma-senha-123"})
        self.assertIn("nova: deve ser diferente da atual", erros)

    def test_validar_dispositivo_bordas(self):
        erros, doc = validar_dispositivo("texto")
        self.assertEqual(erros, ["corpo deve ser um objeto JSON"])
        self.assertIsNone(doc)

        erros, _ = validar_dispositivo({"id": "a!"})
        self.assertIn("id: letras, números, _ ou - (3 a 40)", erros)

        # Sucesso com maiúsculas normalizadas para minúsculas
        erros, doc = validar_dispositivo({"id": "DEV-01", "descricao": "Sensor"})
        self.assertEqual(erros, [])
        self.assertEqual(doc["id"], "dev-01")
        self.assertEqual(doc["descricao"], "Sensor")

    def test_validar_veiculo_bordas(self):
        erros, doc = validar_veiculo(123)
        self.assertEqual(erros, ["corpo deve ser um objeto JSON"])
        self.assertIsNone(doc)

        # Código e deviceId ausentes
        erros, doc = validar_veiculo({})
        self.assertTrue(any("id: obrigatório" in e for e in erros))
        self.assertTrue(any("deviceId: obrigatório" in e for e in erros))
        self.assertIsNone(doc)

        # Código com caracteres proibidos
        erros, _ = validar_veiculo({"id": "código com espaço", "tipo": "Carreta",
                                    "deviceId": "dev-01", "perfil": "manga"})
        self.assertIn("id: 3 a 20 letras, números ou hífen (ex.: CT-001)", erros)

        # deviceId com caracteres proibidos
        erros, _ = validar_veiculo({"id": "CAM-01", "tipo": "Carreta",
                                    "deviceId": "dev#01", "perfil": "manga"})
        self.assertIn("deviceId: letras, números, _ ou - (3 a 40)", erros)

        # perfil desconhecido
        erros, _ = validar_veiculo({"id": "CAM-01", "tipo": "Carreta",
                                    "deviceId": "dev-01", "perfil": "banana"})
        self.assertTrue(any("perfil: use" in e for e in erros))

        # Sucesso
        erros, doc = validar_veiculo({"id": "cam-01", "tipo": "Caminhão",
                                      "deviceId": "DEV-01", "perfil": "uva"})
        self.assertEqual(erros, [])
        self.assertEqual(doc["id"], "CAM-01")
        self.assertEqual(doc["deviceId"], "dev-01")

    def test_validar_viagem_bordas(self):
        erros, doc = validar_viagem(False)
        self.assertEqual(erros, ["corpo deve ser um objeto JSON"])
        self.assertIsNone(doc)

        # Fim antes ou igual ao início
        erros, _ = validar_viagem({
            "veiculo": "CAM-01",
            "origem": "Petrolina",
            "destino": "Recife",
            "carga": "Manga",
            "inicio": "2026-05-10T12:00:00Z",
            "fim": "2026-05-10T11:00:00Z"
        })
        self.assertIn("fim: deve ser depois do início", erros)

        # Sucesso com fim opcional ausente
        erros, doc = validar_viagem({
            "veiculo": "cam-01",
            "origem": "Petrolina",
            "destino": "Recife",
            "carga": "Manga Tommy",
            "inicio": "2026-05-10T12:00:00Z"
        })
        self.assertEqual(erros, [])
        self.assertEqual(doc["veiculo"], "CAM-01")
        self.assertIsNone(doc["fim"])


if __name__ == "__main__":
    unittest.main()
