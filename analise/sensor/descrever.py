"""Descreve a base real da placa física (ThingSpeak 3515173): cobertura, lacunas, inválidos e estatística.

Gera relatorio.md. Os números saem todos do CSV; nada é estimado à mão.
"""

import sys
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).parent
CSV = AQUI / "dados" / "thingspeak_3515173.csv"
RELATORIO = AQUI / "relatorio.md"
FIGURAS = AQUI / "figuras"

INTERVALO_S = 20          # período nominal de publicação do firmware
FATOR_LACUNA = 2          # lacuna = intervalo entre leituras > 2x o nominal
META_HORAS = 48           # IOT-06
# Faixas físicas do DHT11 (datasheet) e faixas aceitas pela API (cloud/function/contrato.py).
FAIXAS_SENSOR = {"temperatura": (0.0, 50.0), "umidade": (20.0, 90.0)}
FAIXAS_API = {"temperatura": (-40.0, 80.0), "umidade": (0.0, 100.0)}
VARIAVEIS = ["temperatura", "umidade", "rssi"]
UNIDADE = {"temperatura": "°C", "umidade": "%", "rssi": "dBm"}


def carregar(caminho=CSV):
    df = pd.read_csv(caminho)
    df["momento_utc"] = pd.to_datetime(df["momento_utc"], utc=True)
    return df.sort_values("momento_utc").reset_index(drop=True)


def intervalos(momentos):
    """Segundos entre leituras consecutivas (série com len-1 elementos)."""
    return pd.Series(momentos).diff().dropna().dt.total_seconds()


def lacunas(momentos, intervalo_s=INTERVALO_S, fator=FATOR_LACUNA):
    """Lista de (inicio, fim, duracao_s) onde o intervalo passa de fator x intervalo_s."""
    m = pd.Series(momentos).reset_index(drop=True)
    saida = []
    for i in range(1, len(m)):
        d = (m[i] - m[i - 1]).total_seconds()
        if d > fator * intervalo_s:
            saida.append((m[i - 1], m[i], d))
    return saida


def janelas_continuas(momentos, intervalo_s=INTERVALO_S, fator=FATOR_LACUNA):
    """Trechos sem lacuna: lista de (inicio, fim, n_leituras), na ordem do tempo."""
    m = pd.Series(momentos).reset_index(drop=True)
    if m.empty:
        return []
    janelas, ini, n = [], m[0], 1
    for i in range(1, len(m)):
        if (m[i] - m[i - 1]).total_seconds() > fator * intervalo_s:
            janelas.append((ini, m[i - 1], n))
            ini, n = m[i], 0
        n += 1
    janelas.append((ini, m[len(m) - 1], n))
    return janelas


def invalidos(serie, faixa):
    """Máscara booleana: True onde é NaN ou fora de [min, max]."""
    lo, hi = faixa
    return serie.isna() | (serie < lo) | (serie > hi)


def estatistica(serie):
    s = serie.dropna()
    q = s.quantile([0.25, 0.5, 0.75])
    return {"n": int(s.size), "min": s.min(), "q1": q[0.25], "mediana": q[0.5],
            "q3": q[0.75], "max": s.max(), "media": s.mean(), "desvio": s.std()}


def _h(segundos):
    return segundos / 3600


def _fmt_dur(segundos):
    if segundos >= 86400:
        return f"{segundos / 86400:.2f} dias"
    return f"{_h(segundos):.2f} h"


def _dur(j):
    return (j[1] - j[0]).total_seconds()


def calcular(df):
    """Todas as métricas do relatório, num dicionário."""
    t = df["momento_utc"]
    dt = intervalos(t)
    lac = lacunas(t)
    jan = janelas_continuas(t)
    maior = max(jan, key=_dur)
    periodo_s = (t.iloc[-1] - t.iloc[0]).total_seconds()
    inv = {}
    for v in ("temperatura", "umidade"):
        inv[v] = {"sensor": int(invalidos(df[v], FAIXAS_SENSOR[v]).sum()),
                  "api": int(invalidos(df[v], FAIXAS_API[v]).sum()),
                  "nan": int(df[v].isna().sum())}
    inv["rssi"] = {"nan": int(df["rssi"].isna().sum())}
    linha_sensor = (invalidos(df["temperatura"], FAIXAS_SENSOR["temperatura"])
                    | invalidos(df["umidade"], FAIXAS_SENSOR["umidade"]))
    linha_api = (invalidos(df["temperatura"], FAIXAS_API["temperatura"])
                 | invalidos(df["umidade"], FAIXAS_API["umidade"]))
    return {
        "n": len(df), "inicio": t.iloc[0], "fim": t.iloc[-1], "periodo_s": periodo_s,
        "dt_mediana": float(dt.median()), "dt_p95": float(dt.quantile(0.95)),
        "lacunas": lac, "lac_s": sum(x[2] for x in lac),
        "esperadas": int(periodo_s // INTERVALO_S) + 1,
        "janelas": jan, "maior": maior, "cobertas_s": sum(_dur(j) for j in jan),
        "inv": inv, "linhas_inv_sensor": int(linha_sensor.sum()),
        "linhas_inv_api": int(linha_api.sum()),
        "stats": {v: estatistica(df[v]) for v in VARIAVEIS},
        "dias_com_dado": int(t.dt.tz_convert("America/Recife").dt.date.nunique()),
    }


def figuras(df, m):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIGURAS.mkdir(exist_ok=True)
    fig, eixos = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    for ax, v in zip(eixos, VARIAVEIS):
        ax.plot(df["momento_utc"], df[v], ".", ms=2)
        ax.set_ylabel(f"{v} ({UNIDADE[v]})")
    eixos[-1].set_xlabel("momento (UTC)")
    fig.suptitle("Placa física: leituras do canal ThingSpeak 3515173")
    fig.tight_layout()
    fig.savefig(FIGURAS / "serie.png", dpi=110)
    plt.close(fig)

    dur = [_dur(j) / 3600 for j in m["janelas"]]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(range(len(dur)), dur)
    ax.axhline(META_HORAS, color="red", ls="--", label=f"meta {META_HORAS} h")
    ax.set_xlabel("janela contínua (ordem cronológica)")
    ax.set_ylabel("duração (h)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURAS / "janelas.png", dpi=110)
    plt.close(fig)


def _f(x):
    return f"{x:.2f}"


def _pct(a, b):
    return f"{100 * a / b:.2f}%"


def relatorio(m):
    maior_s = _dur(m["maior"])
    tem48 = _h(maior_s) >= META_HORAS
    cob_h = _h(m["cobertas_s"])
    n = m["n"]
    ausentes = m["esperadas"] - n
    L = []
    L.append("# Base da placa física: descrição e qualidade\n")
    L.append("Gerado por `descrever.py` a partir de `dados/thingspeak_3515173.csv` "
             "(canal público ThingSpeak 3515173, placa ESP32-C3 via MQTT, dado real). "
             "Requisito IOT-06.\n")
    L.append("## Cobertura\n")
    L.append("| item | valor |\n|---|---|")
    L.append(f"| primeira leitura (UTC) | {m['inicio']:%Y-%m-%d %H:%M:%S} |")
    L.append(f"| última leitura (UTC) | {m['fim']:%Y-%m-%d %H:%M:%S} |")
    L.append(f"| período entre a primeira e a última | {_fmt_dur(m['periodo_s'])} |")
    L.append(f"| leituras | {n} |")
    L.append(f"| leituras esperadas no período (a cada {INTERVALO_S} s) | {m['esperadas']} |")
    L.append(f"| completude em relação ao esperado | {_pct(n, m['esperadas'])} |")
    L.append(f"| dias de calendário (UTC-3) com ao menos uma leitura | {m['dias_com_dado']} |")
    L.append(f"| **horas cobertas** (soma dos trechos sem lacuna) | **{_f(cob_h)} h** |")
    L.append(f"| **maior janela contínua** | **{_f(_h(maior_s))} h** "
             f"({m['maior'][0]:%Y-%m-%d %H:%M} a {m['maior'][1]:%Y-%m-%d %H:%M} UTC, "
             f"{m['maior'][2]} leituras) |")
    L.append("")
    L.append("## Veredito sobre a meta de 48 h\n")
    if tem48:
        L.append(f"**Atendida.** Há um trecho contínuo de {_f(_h(maior_s))} h (sem lacuna maior que "
                 f"{FATOR_LACUNA * INTERVALO_S} s), acima das {META_HORAS} h exigidas.\n")
    else:
        soma = cob_h >= META_HORAS
        titulo = ("**Não atendida como trecho contínuo; atendida pela soma das horas cobertas.**"
                  if soma else "**Não atendida.**")
        L.append(f"{titulo} A maior janela sem lacuna tem {_f(_h(maior_s))} h, abaixo das "
                 f"{META_HORAS} h seguidas. A soma das horas cobertas é {_f(cob_h)} h "
                 f"({'acima' if soma else 'abaixo'} das {META_HORAS} h), em trechos separados "
                 "por lacunas (placa desligada ou sem rede; a causa não consta nos dados). "
                 "O período entre a primeira e a última leitura é maior que a cobertura real.\n")
    L.append("## Intervalo entre leituras\n")
    L.append("| métrica | valor |\n|---|---|")
    L.append(f"| esperado | {INTERVALO_S} s |")
    L.append(f"| mediana real | {_f(m['dt_mediana'])} s |")
    L.append(f"| p95 real | {_f(m['dt_p95'])} s |\n")
    L.append("## Faltantes (lacunas)\n")
    L.append(f"Lacuna = intervalo entre duas leituras consecutivas maior que {FATOR_LACUNA}x o "
             f"esperado ({FATOR_LACUNA * INTERVALO_S} s).\n")
    L.append("| item | valor |\n|---|---|")
    L.append(f"| lacunas | {len(m['lacunas'])} |")
    L.append(f"| duração total das lacunas | {_fmt_dur(m['lac_s'])} |")
    L.append(f"| fração do período em lacuna | {_pct(m['lac_s'], m['periodo_s'])} |")
    L.append(f"| trechos contínuos | {len(m['janelas'])} |")
    L.append(f"| leituras ausentes no período (esperadas menos presentes) | {ausentes} "
             f"({_pct(ausentes, m['esperadas'])} das esperadas) |\n")
    top = sorted(m["lacunas"], key=lambda x: -x[2])[:10]
    if top:
        L.append("Dez maiores lacunas:\n")
        L.append("| de (UTC) | até (UTC) | duração |\n|---|---|---|")
        for a, b, d in top:
            L.append(f"| {a:%Y-%m-%d %H:%M:%S} | {b:%Y-%m-%d %H:%M:%S} | {_fmt_dur(d)} |")
        L.append("")
    L.append("Maiores trechos contínuos:\n")
    L.append("| início (UTC) | fim (UTC) | duração | leituras |\n|---|---|---|---|")
    for j in sorted(m["janelas"], key=lambda j: -_dur(j))[:10]:
        L.append(f"| {j[0]:%Y-%m-%d %H:%M:%S} | {j[1]:%Y-%m-%d %H:%M:%S} | "
                 f"{_fmt_dur(_dur(j))} | {j[2]} |")
    L.append("")
    L.append("## Inválidos\n")
    s, a = FAIXAS_SENSOR, FAIXAS_API
    L.append(f"Faixa física do DHT11: temperatura {s['temperatura'][0]:g} a {s['temperatura'][1]:g} °C, "
             f"umidade {s['umidade'][0]:g} a {s['umidade'][1]:g} %. Faixa aceita pela API "
             f"(`cloud/function/contrato.py`): temperatura {a['temperatura'][0]:g} a "
             f"{a['temperatura'][1]:g} °C, umidade {a['umidade'][0]:g} a {a['umidade'][1]:g} %. "
             "Inválido = NaN ou fora da faixa.\n")
    L.append("| variável | NaN | fora da faixa DHT11 (inclui NaN) | fora da faixa da API (inclui NaN) |\n"
             "|---|---|---|---|")
    for v in ("temperatura", "umidade"):
        i = m["inv"][v]
        L.append(f"| {v} | {i['nan']} | {i['sensor']} ({_pct(i['sensor'], n)}) | "
                 f"{i['api']} ({_pct(i['api'], n)}) |")
    L.append(f"| rssi | {m['inv']['rssi']['nan']} | n/a | n/a |")
    L.append(f"| **leituras com ao menos uma variável inválida** | | "
             f"**{m['linhas_inv_sensor']} ({_pct(m['linhas_inv_sensor'], n)})** | "
             f"**{m['linhas_inv_api']} ({_pct(m['linhas_inv_api'], n)})** |\n")
    L.append("## Estatística descritiva\n")
    L.append("| variável | n | mín | Q1 | mediana | Q3 | máx | média | desvio |\n"
             "|---|---|---|---|---|---|---|---|---|")
    for v in VARIAVEIS:
        e = m["stats"][v]
        L.append(f"| {v} ({UNIDADE[v]}) | {e['n']} | {_f(e['min'])} | {_f(e['q1'])} | "
                 f"{_f(e['mediana'])} | {_f(e['q3'])} | {_f(e['max'])} | {_f(e['media'])} | "
                 f"{_f(e['desvio'])} |")
    L.append("")
    L.append("![série](figuras/serie.png)\n\n![janelas](figuras/janelas.png)\n")
    return "\n".join(L)


def main():
    df = carregar()
    m = calcular(df)
    figuras(df, m)
    RELATORIO.write_text(relatorio(m), encoding="utf-8")
    print(f"relatório em {RELATORIO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
