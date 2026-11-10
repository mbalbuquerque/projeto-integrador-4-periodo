"""Testes unitários automatizados para o download de dados do INMET (baixar_inmet.py)."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import baixar_inmet


class TestBaixarInmet(unittest.TestCase):
    def test_baixar_extrai_apenas_estacoes_da_rota(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            # Uma estação que pertence à rota (A307 - Petrolina)
            zf.writestr("INMET_NE_PE_A307_PETROLINA_01-01-2026.CSV", "dados petrolina")
            # Uma estação fora da rota (São Paulo)
            zf.writestr("INMET_SE_SP_A701_SAO_PAULO_01-01-2026.CSV", "dados sp")
        buffer.seek(0)

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_destino = Path(tmpdir)
            mock_resp = mock.Mock()
            mock_resp.read.return_value = buffer.getvalue()

            with mock.patch("baixar_inmet.DESTINO", fake_destino), \
                 mock.patch("urllib.request.urlopen", return_value=mock_resp):
                baixar_inmet.baixar(2026)

            salvos = list(fake_destino.glob("*.CSV"))
            self.assertEqual(len(salvos), 1)
            self.assertEqual(salvos[0].name, "INMET_NE_PE_A307_PETROLINA_01-01-2026.CSV")


if __name__ == "__main__":
    unittest.main()

