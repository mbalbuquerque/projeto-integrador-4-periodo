"""Baixa os dados horários do INMET das estações da rota Petrolina -> Suape.

O INMET publica um .zip por ano com todas as estações automáticas do país
(~100 MB). Este script baixa cada ano, extrai só as estações da rota e salva
em dados/brutos/. Rodar uma vez; os demais scripts leem de lá.

Uso:  python baixar_inmet.py            (anos padrão: 2023 a 2025)
      python baixar_inmet.py 2022 2023
"""

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"

# O portal recusa clientes sem User-Agent de navegador.
CABECALHOS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129"}

# Estações automáticas ao longo da BR-428/BR-232, de Petrolina ao litoral.
ESTACOES = {
    "A307": "Petrolina",
    "A329": "Cabrobó",
    "A370": "Salgueiro",
    "A350": "Serra Talhada",
    "A309": "Arcoverde",
    "A341": "Caruaru",
    "A301": "Recife",
}

DESTINO = Path(__file__).resolve().parent / "dados" / "brutos"


def baixar(ano):
    print(f"{ano}: baixando…", flush=True)
    req = urllib.request.Request(URL.format(ano=ano), headers=CABECALHOS)
    conteudo = urllib.request.urlopen(req, timeout=600).read()

    pacote = zipfile.ZipFile(io.BytesIO(conteudo))
    DESTINO.mkdir(parents=True, exist_ok=True)

    achadas = []
    for nome in pacote.namelist():
        base = Path(nome).name
        codigo = next((c for c in ESTACOES if f"_{c}_" in base.upper()), None)
        if codigo:
            (DESTINO / base).write_bytes(pacote.read(nome))
            achadas.append(codigo)

    faltando = sorted(set(ESTACOES) - set(achadas))
    print(f"{ano}: {len(achadas)} estações salvas"
          + (f" (sem arquivo: {', '.join(faltando)})" if faltando else ""))


if __name__ == "__main__":
    anos = [int(a) for a in sys.argv[1:]] or [2023, 2024, 2025]
    for ano in anos:
        baixar(ano)
