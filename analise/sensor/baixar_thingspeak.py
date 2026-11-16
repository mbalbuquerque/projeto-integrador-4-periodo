"""Baixa o canal público ThingSpeak 3515173 (placa física ColdTrack, via MQTT) por inteiro.

Pagina por entry_id (start/end em data) até cobrir todas as entradas e grava
dados/thingspeak_3515173.csv, com a coluna `origem` = placa_fisica_thingspeak.
Somente leitura (GET) na API pública.
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

CANAL = 3515173
ORIGEM = "placa_fisica_thingspeak"
URL = f"https://api.thingspeak.com/channels/{CANAL}/feeds.json"
SAIDA = Path(__file__).parent / "dados" / f"thingspeak_{CANAL}.csv"
LOTE = 8000
CAMPOS = {"field1": "temperatura", "field2": "umidade", "field3": "rssi"}


def buscar(params):
    url = URL + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 (URL fixa, https)
        return json.load(r)


def para_dataframe(feeds):
    """Converte a lista `feeds` da API em DataFrame tipado, sem duplicatas, ordenado."""
    linhas = [
        {"entry_id": f["entry_id"], "momento_utc": f["created_at"],
         **{nome: f.get(campo) for campo, nome in CAMPOS.items()}}
        for f in feeds
    ]
    df = pd.DataFrame(linhas, columns=["entry_id", "momento_utc", *CAMPOS.values()])
    for nome in CAMPOS.values():
        df[nome] = pd.to_numeric(df[nome], errors="coerce")
    df["momento_utc"] = pd.to_datetime(df["momento_utc"], utc=True)
    df = df.drop_duplicates("entry_id").sort_values("entry_id").reset_index(drop=True)
    df["origem"] = ORIGEM
    return df


def baixar_tudo():
    meta = buscar({"results": 1})
    ultimo = meta["channel"]["last_entry_id"]
    feeds, fim = [], None
    while True:
        params = {"results": LOTE}
        if fim:
            params["end"] = fim
        lote = buscar(params)["feeds"]
        if not lote:
            break
        feeds = lote + feeds
        if len(lote) < LOTE:
            break
        fim = (pd.to_datetime(lote[0]["created_at"]) - pd.Timedelta(seconds=1)).strftime(
            "%Y-%m-%d %H:%M:%S")
    df = para_dataframe(feeds)
    return df, ultimo


def main():
    df, ultimo = baixar_tudo()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False)
    print(f"{len(df)} entradas (last_entry_id={ultimo}) -> {SAIDA}")
    if len(df) != ultimo:
        print("AVISO: nº de entradas difere de last_entry_id (entradas apagadas no canal?)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
