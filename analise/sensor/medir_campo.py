"""Medições de campo da placa com os dados já gravados no Cosmos DB (sem a placa ligada).

Lê um export JSONL de `leituras` (infra/backup/exportar.py) e mede, só a partir do dado:

1. perda por janelas de 24 h, calculada pela sequência (`seq`): o que falta entre o menor e o maior
   `seq` da janela. Placa desligada não conta como perda, porque a numeração continua de onde parou;
2. latência placa -> banco = `recebidoEm` - `medidoEm`, separando leitura em tempo real (atraso
   menor que 60 s) de reenvio de buffer (atraso de 60 s ou mais);
3. evidência de guardar-e-reenviar (R2): sequências de leituras entregues com atraso e com `seq`
   contínuo.

Uso:
    python analise/sensor/medir_campo.py <leituras.jsonl> [--device ID] [--inicio ISO] [--saida arquivo.md]

O export tem dado real: fica fora do repositório. Só leitura; nada é estimado à mão.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

DEVICE = "coldtrack-0e0b2c"
INICIO = "2026-11-17T06:46:41Z"   # primeira leitura da coleta de 17 a 20/11 (a mesma de relatorio_cosmos.md)
JANELA_H = 24
PASSO_H = 1
INTERVALO_S = 20
LIMITE_PERDA = 0.01
LIMITE_TEMPO_REAL_S = 60


def carregar(caminho, device=DEVICE, inicio=INICIO):
    """Leituras do dispositivo com `seq`, a partir de `inicio`, ordenadas por `seq`."""
    linhas = []
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                linhas.append(json.loads(linha))
    df = pd.DataFrame(linhas)
    df = df[(df["deviceId"] == device) & df["seq"].notna()].copy()
    df["seq"] = df["seq"].astype(int)
    df["medido"] = pd.to_datetime(df["medidoEm"], utc=True, format="ISO8601")
    df["recebido"] = pd.to_datetime(df["recebidoEm"], utc=True, format="ISO8601")
    df = df[df["medido"] >= pd.Timestamp(inicio)]
    return df.sort_values("seq").reset_index(drop=True)


def perda_janela(seqs):
    """(recebidas, esperadas, faltantes) de um conjunto de `seq`: esperadas = maior - menor + 1."""
    seqs = pd.Series(list(seqs)).drop_duplicates()
    if seqs.empty:
        return 0, 0, 0
    esperadas = int(seqs.max() - seqs.min() + 1)
    recebidas = int(len(seqs))
    return recebidas, esperadas, esperadas - recebidas


def janelas_24h(df, janela_h=JANELA_H, passo_h=PASSO_H):
    """Uma linha por janela deslizante de `janela_h` horas (passo `passo_h`) dentro do período."""
    ini, fim = df["medido"].min(), df["medido"].max()
    saida = []
    t = ini
    largura = pd.Timedelta(janela_h, unit="h")
    while t + largura <= fim:
        parte = df[(df["medido"] >= t) & (df["medido"] < t + largura)]
        recebidas, esperadas, faltantes = perda_janela(parte["seq"])
        saida.append({
            "inicio": t,
            "fim": t + largura,
            "recebidas": recebidas,
            "esperadas": esperadas,
            "faltantes": faltantes,
            "perda": faltantes / esperadas if esperadas else 0.0,
            "disponibilidade": recebidas / (janela_h * 3600 / INTERVALO_S),
        })
        t += pd.Timedelta(passo_h, unit="h")
    return pd.DataFrame(saida)


def lacunas_seq(df):
    """Buracos na numeração: (seq que voltou, faltantes, medido antes, medido depois)."""
    d = df["seq"].diff()
    buracos = df[d > 1]
    saida = []
    for i in buracos.index:
        saida.append({
            "seq_depois": int(df.loc[i, "seq"]),
            "faltantes": int(d[i] - 1),
            "medido_antes": df.loc[i - 1, "medido"],
            "medido_depois": df.loc[i, "medido"],
        })
    return saida


def latencias(df, limite_s=LIMITE_TEMPO_REAL_S):
    """Atraso (s) entre medir e gravar, com a separação tempo real x reenvio."""
    atraso = (df["recebido"] - df["medido"]).dt.total_seconds()
    return atraso, atraso < limite_s


def resumo_atraso(serie):
    if serie.empty:
        return {"n": 0, "mediana": None, "p95": None, "p99": None, "max": None, "min": None}
    return {
        "n": int(len(serie)),
        "mediana": float(serie.median()),
        "p95": float(serie.quantile(0.95)),
        "p99": float(serie.quantile(0.99)),
        "max": float(serie.max()),
        "min": float(serie.min()),
    }


def reenvios(df, limite_s=LIMITE_TEMPO_REAL_S):
    """Grupos de leituras com atraso >= limite e `seq` consecutivo (um grupo = um reenvio de buffer)."""
    atraso = (df["recebido"] - df["medido"]).dt.total_seconds()
    atrasadas = df[atraso >= limite_s].copy()
    atrasadas["atraso_s"] = atraso[atrasadas.index]
    if atrasadas.empty:
        return []
    grupo = (atrasadas["seq"].diff() != 1).cumsum()
    saida = []
    for _, g in atrasadas.groupby(grupo):
        saida.append({
            "seq_ini": int(g["seq"].iloc[0]),
            "seq_fim": int(g["seq"].iloc[-1]),
            "leituras": int(len(g)),
            "medido_ini": g["medido"].iloc[0],
            "medido_fim": g["medido"].iloc[-1],
            "recebido_ini": g["recebido"].min(),
            "recebido_fim": g["recebido"].max(),
            "atraso_max_s": float(g["atraso_s"].max()),
            # a ordem de medição segue a ordem de `seq`: o buffer reenvia em ordem
            "em_ordem": bool(g["medido"].is_monotonic_increasing),
        })
    return saida


def _fmt(t):
    return t.strftime("%d/%m %H:%M:%S")


def _pct(x):
    return f"{x * 100:.2f}%".replace(".", ",")


def _num(x, casas=1):
    return f"{x:.{casas}f}".replace(".", ",")


def relatorio(df, device=DEVICE):
    jan = janelas_24h(df)
    atraso, tempo_real = latencias(df)
    r_tr = resumo_atraso(atraso[tempo_real])
    r_buf = resumo_atraso(atraso[~tempo_real])
    r_todas = resumo_atraso(atraso)
    grupos = reenvios(df)
    grupos_ord = sorted(grupos, key=lambda g: (g["leituras"], g["atraso_max_s"]), reverse=True)

    recebidas, esperadas, faltantes = perda_janela(df["seq"])
    ok = int((jan["perda"] <= LIMITE_PERDA).sum()) if not jan.empty else 0
    pior = jan.loc[jan["perda"].idxmax()] if not jan.empty else None
    melhor = jan.loc[jan["perda"].idxmin()] if not jan.empty else None

    L = []
    L.append("# Medições de campo com os dados já gravados (sem a placa ligada)\n")
    L.append(f"Gerado por `medir_campo.py` a partir do export da coleção `leituras` do Cosmos DB "
             f"(dispositivo `{device}`). Tudo sai do dado; nada é estimado à mão.\n")
    L.append("## Período\n")
    L.append("| item | valor |\n|---|---|")
    L.append(f"| primeira leitura (medidoEm, UTC) | {df['medido'].min():%Y-%m-%d %H:%M:%S} |")
    L.append(f"| última leitura (medidoEm, UTC) | {df['medido'].max():%Y-%m-%d %H:%M:%S} |")
    L.append(f"| duração | {_num((df['medido'].max() - df['medido'].min()).total_seconds() / 3600)} h |")
    L.append(f"| leituras gravadas (com `seq`) | {recebidas} |")
    L.append(f"| `seq` esperados (do menor ao maior) | {esperadas} |")
    L.append(f"| `seq` faltantes | {faltantes} ({_pct(faltantes / esperadas)}) |")
    L.append("")
    L.append("## 1. Perda em janelas de 24 h (pela sequência)\n")
    L.append("Janelas deslizantes de 24 h, com passo de 1 h, por `medidoEm`. Perda = `seq` faltantes ÷ `seq` "
             "esperados na janela. Placa desligada não é perda: a numeração (guardada na flash) continua de onde "
             "parou. A queda do aparelho aparece na disponibilidade, não aqui.\n")
    if jan.empty:
        L.append("Período menor que 24 h: sem janela completa.\n")
    else:
        L.append("| item | valor |\n|---|---|")
        L.append(f"| janelas de 24 h analisadas | {len(jan)} |")
        L.append(f"| janelas com perda ≤ 1% | {ok} de {len(jan)} ({_pct(ok / len(jan))}) |")
        L.append(f"| mediana da perda | {_pct(jan['perda'].median())} |")
        L.append(f"| melhor janela | {_pct(melhor['perda'])} ({_fmt(melhor['inicio'])} a {_fmt(melhor['fim'])} UTC; "
                 f"{int(melhor['faltantes'])} faltantes de {int(melhor['esperadas'])}) |")
        L.append(f"| pior janela | {_pct(pior['perda'])} ({_fmt(pior['inicio'])} a {_fmt(pior['fim'])} UTC; "
                 f"{int(pior['faltantes'])} faltantes de {int(pior['esperadas'])}) |")
        L.append(f"| disponibilidade na janela (leituras ÷ 4.320 por 24 h), mediana | {_pct(jan['disponibilidade'].median())} |")
        L.append(f"| disponibilidade na janela, pior | {_pct(jan['disponibilidade'].min())} |")
        L.append("")
        L.append(f"Meta da entrega final: perda ≤ 1% em 24 h. "
                 f"{'Todas as janelas cumprem.' if ok == len(jan) else f'{len(jan) - ok} janela(s) acima de 1%.'}\n")
    buracos = sorted(lacunas_seq(df), key=lambda g: g["faltantes"], reverse=True)
    L.append("### Onde está a perda\n")
    L.append(f"{len(buracos)} buraco(s) na numeração somam {faltantes} leituras. Os maiores:\n")
    L.append("| faltantes | entre (UTC) | `seq` seguinte |\n|---|---|---|")
    for g in buracos[:5]:
        L.append(f"| {g['faltantes']} | {_fmt(g['medido_antes'])} a {_fmt(g['medido_depois'])} | {g['seq_depois']} |")
    if buracos:
        L.append("")
        L.append(f"O maior buraco concentra {_pct(buracos[0]['faltantes'] / faltantes)} de toda a perda. "
                 "O dado não registra a causa.\n")
    L.append("## 2. Latência placa → banco\n")
    L.append("`recebidoEm` − `medidoEm`. O horário de medição vem da placa (NTP) e o de recebimento da API; "
             "pequena diferença de relógio entra na conta. Tempo real = atraso menor que 60 s; reenvio de buffer = "
             "atraso de 60 s ou mais.\n")
    L.append("| grupo | leituras | mediana (s) | p95 (s) | p99 (s) | máximo (s) |\n|---|---|---|---|---|---|")
    for nome, r in (("todas", r_todas), ("tempo real (< 60 s)", r_tr), ("reenvio de buffer (≥ 60 s)", r_buf)):
        if r["n"]:
            L.append(f"| {nome} | {r['n']} | {_num(r['mediana'])} | {_num(r['p95'])} | {_num(r['p99'])} | {_num(r['max'])} |")
        else:
            L.append(f"| {nome} | 0 | - | - | - | - |")
    negativas = int((atraso < 0).sum())
    L.append("")
    L.append(f"Leituras com atraso negativo (relógio da placa à frente do servidor): {negativas}"
             f"{f' (menor valor {_num(atraso.min())} s)' if negativas else ''}.\n")
    L.append("## 3. Guardar e reenviar (R2) em campo\n")
    L.append(f"Leituras entregues com atraso ≥ 60 s: **{r_buf['n']}** de {r_todas['n']} "
             f"({_pct(r_buf['n'] / r_todas['n']) if r_todas['n'] else '0%'}), em **{len(grupos)}** reenvio(s) de `seq` "
             f"consecutivo. Cada grupo é um trecho que a placa guardou sem rede e entregou depois, mantendo o horário "
             f"da medição.\n")
    if grupos_ord:
        L.append("Maiores reenvios:\n")
        L.append("| `seq` | leituras | medidas entre (UTC) | recebidas entre (UTC) | maior atraso | em ordem |\n|---|---|---|---|---|---|")
        for g in grupos_ord[:8]:
            atraso_txt = f"{_num(g['atraso_max_s'] / 60)} min" if g["atraso_max_s"] >= 120 else f"{_num(g['atraso_max_s'])} s"
            L.append(f"| {g['seq_ini']} a {g['seq_fim']} | {g['leituras']} | {_fmt(g['medido_ini'])} a {_fmt(g['medido_fim'])} | "
                     f"{_fmt(g['recebido_ini'])} a {_fmt(g['recebido_fim'])} | {atraso_txt} | "
                     f"{'sim' if g['em_ordem'] else 'não'} |")
        L.append("")
    L.append("## O que este relatório não mede\n")
    L.append("- Latência ao vivo com estímulo (aquecer o sensor e cronometrar até a tela): depende da placa ligada (#126).")
    L.append("- Watchdog travando na placa física (#124), F4 com reenvio pela placa (#121) e F6 real (#123).")
    L.append("- A causa de cada reenvio (queda de Wi-Fi, API fora, reinício): o dado não registra o motivo.")
    L.append("- A última etapa, do banco até aparecer no painel, não está neste dado: ver `RESILIENCIA.md`.")
    return "\n".join(L) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("jsonl")
    p.add_argument("--device", default=DEVICE)
    p.add_argument("--inicio", default=INICIO)
    p.add_argument("--saida", default=str(Path(__file__).parent / "relatorio_campo.md"))
    args = p.parse_args(argv)
    df = carregar(args.jsonl, args.device, args.inicio)
    if df.empty:
        raise SystemExit("Sem leituras com `seq` para esse dispositivo e período.")
    Path(args.saida).write_text(relatorio(df, args.device), encoding="utf-8", newline="\n")
    print(f"relatório em {args.saida}")


if __name__ == "__main__":
    sys.exit(main())
