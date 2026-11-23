"""Descreve a coleta da placa física gravada no Cosmos DB (via API), com perda medida pela sequência.

Uso:
    python descrever_cosmos.py --converter <leituras.jsonl>   # gera dados/cosmos_leituras.csv
    python descrever_cosmos.py                                 # gera relatorio_cosmos.md

O .jsonl vem de `infra/backup/exportar.py` (container `leituras`). O CSV guarda só o que a
análise usa (sem e-mail, senha ou chave): seq, medido_em, temperatura, umidade, rssi.
Perda = números de `seq` que faltam entre o menor e o maior; disponibilidade = leituras
recebidas dividido pelas esperadas (uma a cada 20 s) no período.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).parent
CSV = AQUI / "dados" / "cosmos_leituras.csv"
RELATORIO = AQUI / "relatorio_cosmos.md"
DEVICE = "coldtrack-0e0b2c"
INTERVALO_S = 20
LACUNA_S = 120            # lacuna listada = intervalo maior que 2 min


def converter(jsonl, saida=CSV, device=DEVICE):
    linhas = []
    for texto in Path(jsonl).read_text(encoding="utf-8").splitlines():
        d = json.loads(texto)
        if d.get("deviceId") != device or d.get("seq") is None:
            continue
        linhas.append({"seq": int(d["seq"]), "medido_em": d["medidoEm"],
                       "temperatura": d.get("temperatura"), "umidade": d.get("umidade"),
                       "rssi": d.get("rssi")})
    df = pd.DataFrame(linhas)
    df["medido_em"] = pd.to_datetime(df["medido_em"], utc=True, format="ISO8601")
    df = df.sort_values("seq").drop_duplicates("seq")
    df["medido_em"] = df["medido_em"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(saida, index=False)
    return df


def carregar(caminho=CSV):
    df = pd.read_csv(caminho)
    df["medido_em"] = pd.to_datetime(df["medido_em"], utc=True)
    return df.sort_values("medido_em").reset_index(drop=True)


def calcular(df, desde=None):
    if desde is not None:
        df = df[df["medido_em"] >= pd.Timestamp(desde, tz="UTC")].reset_index(drop=True)
    t = df["medido_em"]
    span = (t.iloc[-1] - t.iloc[0]).total_seconds()
    seq = df["seq"]
    esperadas_seq = int(seq.max() - seq.min() + 1)
    faltantes = esperadas_seq - int(seq.nunique())
    esperadas_t = int(span // INTERVALO_S) + 1
    gaps = t.diff().dt.total_seconds()
    grandes = [(t[i - 1], t[i], gaps[i]) for i in gaps.index[1:] if gaps[i] > LACUNA_S]
    blocos = (gaps.fillna(0) > 2 * INTERVALO_S).cumsum()
    janelas = [(g.iloc[0], g.iloc[-1], len(g)) for _, g in t.groupby(blocos)]
    cobertas = sum((b - a).total_seconds() for a, b, _ in janelas)
    maior = max(janelas, key=lambda j: (j[1] - j[0]).total_seconds())
    return {"n": len(df), "inicio": t.iloc[0], "fim": t.iloc[-1], "span_s": span,
            "seq_min": int(seq.min()), "seq_max": int(seq.max()), "faltantes": faltantes,
            "perda": faltantes / esperadas_seq, "esperadas_t": esperadas_t,
            "disponibilidade": len(df) / esperadas_t, "grandes": grandes,
            "cobertas_s": cobertas, "maior": maior, "duplicadas": int(seq.duplicated().sum())}


def _h(s):
    return f"{s / 3600:.2f} h"


def relatorio(m):
    L = ["# Coleta da placa física no Cosmos DB (perda medida por sequência)\n",
         "Gerado por `descrever_cosmos.py` a partir de `dados/cosmos_leituras.csv` (container "
         f"`leituras` da API em produção, dispositivo `{DEVICE}`). Complementa o `relatorio.md` "
         "(canal ThingSpeak). Dado real da placa; nada estimado à mão.\n",
         "## Resultado\n", "| item | valor |\n|---|---|",
         f"| primeira leitura (UTC) | {m['inicio']:%Y-%m-%d %H:%M:%S} |",
         f"| última leitura (UTC) | {m['fim']:%Y-%m-%d %H:%M:%S} |",
         f"| período | {_h(m['span_s'])} |",
         f"| leituras gravadas | {m['n']} |",
         f"| `seq` | {m['seq_min']} a {m['seq_max']}, {m['duplicadas']} repetidas |",
         f"| números de `seq` faltantes | {m['faltantes']} |",
         f"| **taxa de perda** (faltantes ÷ faixa de `seq`) | **{100 * m['perda']:.2f}%** |",
         f"| leituras esperadas no período (a cada {INTERVALO_S} s) | {m['esperadas_t']} |",
         f"| **disponibilidade** (gravadas ÷ esperadas) | **{100 * m['disponibilidade']:.1f}%** |",
         f"| horas cobertas (soma dos trechos sem lacuna) | {_h(m['cobertas_s'])} |",
         f"| maior trecho contínuo | {_h((m['maior'][1] - m['maior'][0]).total_seconds())} "
         f"({m['maior'][0]:%Y-%m-%d %H:%M} a {m['maior'][1]:%Y-%m-%d %H:%M} UTC) |\n",
         "A perda mede só o que a placa numerou e a API não recebeu. O tempo com a placa "
         "desligada ou sem rede não gera `seq`, e entra na disponibilidade, não na perda. "
         "Meta de perda: no máximo 1% (prévia técnica, seção 4.2); aqui o período é maior "
         "que as 24 h exigidas, mas não é um teste controlado de 24 h seguidas.\n",
         f"## Lacunas maiores que {LACUNA_S // 60} min\n",
         "| de (UTC) | até (UTC) | duração |\n|---|---|---|"]
    for a, b, d in sorted(m["grandes"], key=lambda x: -x[2]):
        L.append(f"| {a:%Y-%m-%d %H:%M:%S} | {b:%Y-%m-%d %H:%M:%S} | {d / 60:.1f} min |")
    return "\n".join(L) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--converter", help="leituras.jsonl exportado do Cosmos")
    p.add_argument("--desde", default="2026-11-17 06:46", help="início do período analisado (UTC)")
    a = p.parse_args(argv)
    if a.converter:
        converter(a.converter)
    RELATORIO.write_text(relatorio(calcular(carregar(), a.desde)), encoding="utf-8", newline="\n")
    print(f"relatório em {RELATORIO}")


if __name__ == "__main__":
    main()
