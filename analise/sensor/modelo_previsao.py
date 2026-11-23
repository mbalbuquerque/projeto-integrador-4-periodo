"""Previsão da temperatura do sensor 10 minutos à frente: dados reais, baseline e modelo.

Problema: a partir das últimas leituras da placa, estimar a temperatura daqui a 10 minutos,
para o painel avisar antes de a carga sair da faixa (excursão térmica).

Fluxo (a partir de dados/cosmos_leituras.csv, as leituras da placa gravadas no banco,
que é o que a rota recebe em produção; dados/thingspeak_3515173.csv, dado real do canal público,
serve de verificação cruzada):
1. Limpeza: descarta temperatura vazia, fora da faixa física do DHT11 (0 a 50 °C) e instante
   repetido; conta o que saiu em cada passo.
2. Trechos contínuos: intervalo entre leituras maior que LACUNA_S abre trecho novo. Nenhuma
   amostra atravessa uma lacuna (nem na janela de entrada nem no alvo).
3. Amostras: um instante por minuto em cada trecho; atributos dos últimos 10 min
   (cloud/function/previsao_sensor.atributos, a mesma função da rota) e alvo = temperatura
   10 min depois.
4. Divisão temporal: os 30% mais recentes dos instantes são teste; treino só com amostras cujo
   alvo é anterior ao primeiro instante de teste (sem vazamento de futuro).
5. Baseline: persistência (alvo = última leitura). Modelo: ridge sem intercepto sobre a
   variação (alvo - y0), lambda fixo, com numpy.
6. Métrica principal: MAE em °C no teste (RMSE junto). O modelo só é "recomendado" se o MAE
   dele for menor que o do baseline.
7. Exporta ../../cloud/function/modelo_sensor.json (coeficientes e métricas, lido pela rota
   GET /api/predict/sensor) e escreve relatorio_previsao.md e figuras/previsao_teste.png.

Re-treinar com dados novos (um comando, baixa o canal de novo):
    python modelo_previsao.py --baixar
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).parent
FUNCAO = AQUI.parent.parent / "cloud" / "function"
sys.path.insert(0, str(FUNCAO))

import previsao_sensor  # noqa: E402  (módulo da API, mesmo código do treino e da rota)

CSV_THINGSPEAK = AQUI / "dados" / "thingspeak_3515173.csv"
CSV_COSMOS = AQUI / "dados" / "cosmos_leituras.csv"   # gerado por descrever_cosmos.py --converter
RELATORIO = AQUI / "relatorio_previsao.md"
FIGURA = AQUI / "figuras" / "previsao_teste.png"
SAIDA_MODELO = FUNCAO / "modelo_sensor.json"

VERSAO = "sensor-ridge-10min-v2"
FONTES = {
    "cosmos": "Cosmos DB de produção, leituras da placa ESP32-C3 + DHT11 da equipe, em bancada",
    "thingspeak": "ThingSpeak 3515173 (placa ESP32-C3 + DHT11 da equipe, em bancada)",
}
HORIZONTE_MIN = 10
JANELA_MIN = 10
LACUNA_S = 300          # sem leitura por mais de 5 min = trecho novo (e previsão recusada)
FRACAO_TESTE = 0.30
LAMBDA = 1.0
ATRIBUTOS = ["d5", "d10", "m10"]
ARQUIVOS = {"cosmos": CSV_COSMOS, "thingspeak": CSV_THINGSPEAK}
FAIXA_DHT11 = (0.0, 50.0)
CORTES_SENSIBILIDADE = (0.20, 0.30, 0.40)


def limpar(df):
    """(série [(momento, temperatura)], tabela de limpeza [(passo, removidas, restantes)])."""
    passos = [("leituras no CSV", 0, len(df))]
    df = df.dropna(subset=["temperatura", "momento_utc"])
    passos.append(("sem temperatura ou sem data", passos[-1][2] - len(df), len(df)))
    lo, hi = FAIXA_DHT11
    df = df[(df["temperatura"] >= lo) & (df["temperatura"] <= hi)]
    passos.append(("fora da faixa do DHT11 (0 a 50 °C)", passos[-1][2] - len(df), len(df)))
    df = df.sort_values("momento_utc").drop_duplicates("momento_utc")
    passos.append(("instante repetido", passos[-1][2] - len(df), len(df)))
    serie = [(m.to_pydatetime(), float(t)) for m, t in zip(df["momento_utc"], df["temperatura"])]
    return serie, passos


def amostras(serie, horizonte=HORIZONTE_MIN, janela=JANELA_MIN, lacuna_s=LACUNA_S):
    """DataFrame de amostras (momento, trecho, y0, atributos, alvo), em ordem de tempo."""
    linhas = []
    for n, trecho in enumerate(previsao_sensor.trechos(serie, lacuna_s)):
        tempos = [p[0] for p in trecho]
        inicio = trecho[0][0] + timedelta(minutes=janela)
        momento = inicio.replace(second=0, microsecond=0)
        if momento < inicio:
            momento += timedelta(minutes=1)
        while momento + timedelta(minutes=horizonte) <= trecho[-1][0]:
            atrib = previsao_sensor.atributos(trecho, momento, janela)
            alvo = previsao_sensor.valor_em(trecho, tempos, momento + timedelta(minutes=horizonte))
            linhas.append({"momento": momento, "trecho": n, **atrib, "alvo": alvo})
            momento += timedelta(minutes=1)
    colunas = ["momento", "trecho", "y0", *ATRIBUTOS, "alvo"]
    return pd.DataFrame(linhas, columns=colunas)


def dividir(dados, fracao_teste=FRACAO_TESTE, horizonte=HORIZONTE_MIN):
    """(treino, teste, corte): teste = fração mais recente; treino com alvo antes do corte."""
    dados = dados.sort_values("momento").reset_index(drop=True)
    corte = dados["momento"].iloc[int(len(dados) * (1 - fracao_teste))]
    teste = dados[dados["momento"] >= corte]
    treino = dados[dados["momento"] + timedelta(minutes=horizonte) < corte]
    return treino, teste, corte


def ajustar(treino, lam=LAMBDA):
    """Coeficientes do ridge sem intercepto: variação = soma(coef * atributo)."""
    x = treino[ATRIBUTOS].to_numpy(dtype=float)
    y = (treino["alvo"] - treino["y0"]).to_numpy(dtype=float)
    return np.linalg.solve(x.T @ x + lam * np.eye(x.shape[1]), x.T @ y)


def avaliar(teste, coef):
    """MAE e RMSE (°C) do modelo e do baseline de persistência no conjunto de teste."""
    real = teste["alvo"].to_numpy(dtype=float)
    base = teste["y0"].to_numpy(dtype=float)
    modelo = base + teste[ATRIBUTOS].to_numpy(dtype=float) @ coef

    def mae(p):
        return float(np.mean(np.abs(p - real)))

    def rmse(p):
        return float(np.sqrt(np.mean((p - real) ** 2)))

    return {"maeModelo": round(mae(modelo), 4), "maeBaseline": round(mae(base), 4),
            "rmseModelo": round(rmse(modelo), 4), "rmseBaseline": round(rmse(base), 4)}


def periodo(parte):
    return {"de": parte["momento"].min().isoformat(), "ate": parte["momento"].max().isoformat(),
            "amostras": int(len(parte))}


def montar_modelo(treino, teste, coef, metricas, fonte):
    return {
        "versao": VERSAO,
        "fonte": FONTES[fonte],
        "horizonteMin": HORIZONTE_MIN,
        "janelaMin": JANELA_MIN,
        "lacunaMaxS": LACUNA_S,
        "atributos": ATRIBUTOS,
        "coeficientes": [round(float(c), 6) for c in coef],
        "lambda": LAMBDA,
        "baseline": "persistencia",
        "treino": periodo(treino),
        "teste": periodo(teste),
        "metricas": metricas,
        "superaBaseline": metricas["maeModelo"] < metricas["maeBaseline"],
    }


def sensibilidade(dados):
    """Mesmas métricas com outras frações de teste (só informativo; o modelo usa 30%)."""
    linhas = []
    for fracao in CORTES_SENSIBILIDADE:
        treino, teste, corte = dividir(dados, fracao)
        linhas.append((fracao, corte, len(treino), len(teste), avaliar(teste, ajustar(treino))))
    return linhas


def figura(teste, coef, caminho=FIGURA):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    caminho.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 4))
    alvo_em = teste["momento"] + timedelta(minutes=HORIZONTE_MIN)
    ax.plot(alvo_em, teste["alvo"], color="black", lw=1.2, label="real")
    ax.plot(alvo_em, teste["y0"], color="0.6", lw=1, ls="--", label="baseline (persistência)")
    ax.plot(alvo_em, teste["y0"] + teste[ATRIBUTOS].to_numpy() @ coef, color="0.3", lw=1,
            label="modelo (ridge)")
    ax.set_ylabel("temperatura (°C)")
    ax.set_title(f"Teste: temperatura {HORIZONTE_MIN} min à frente")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(caminho, dpi=110)
    plt.close(fig)


def carregar(caminho):
    """DataFrame com momento_utc (UTC) e temperatura de um dos CSV de dados/."""
    df = pd.read_csv(caminho).rename(columns={"medido_em": "momento_utc"})   # cosmos_leituras.csv
    df["momento_utc"] = pd.to_datetime(df["momento_utc"], utc=True, format="ISO8601")
    return df


def treinar(df):
    """Pipeline inteiro sobre um CSV: (serie, passos, dados, treino, teste, corte, coef, métricas)."""
    serie, passos = limpar(df)
    dados = amostras(serie)
    treino, teste, corte = dividir(dados)
    coef = ajustar(treino)
    return serie, passos, dados, treino, teste, corte, coef, avaliar(teste, coef)


def verificacao_cruzada(caminho):
    """Mesmo pipeline noutra fonte: (amostras de treino, de teste, métricas), só informativo."""
    *_, treino, teste, _, _, metricas = treinar(carregar(caminho))
    return len(treino), len(teste), metricas


def relatorio(passos, serie, dados, treino, teste, corte, modelo, sens, fonte, cruzada=None):
    m = modelo["metricas"]
    cadencia = pd.Series([p[0] for p in serie]).diff().dt.total_seconds()
    recente = previsao_sensor.trechos(serie, LACUNA_S)[-1]
    ultimo = pd.Series([p[0] for p in recente]).diff().dt.total_seconds()
    n_trechos = dados["trecho"].nunique() if len(dados) else 0
    if modelo["superaBaseline"]:
        veredito = (f"**O modelo supera o baseline** no teste: MAE {m['maeModelo']:.3f} °C contra "
                    f"{m['maeBaseline']:.3f} °C. A rota recomenda a previsão do modelo.")
    else:
        veredito = (f"**O modelo NÃO supera o baseline** no teste: MAE {m['maeModelo']:.3f} °C "
                    f"contra {m['maeBaseline']:.3f} °C da persistência. A rota continua "
                    "devolvendo as duas previsões, mas recomenda a persistência "
                    "(`recomendada = baseline`) até um novo treino mostrar ganho.")
    linhas = [
        "# Previsão da temperatura do sensor (10 min à frente)",
        "",
        f"Gerado por `modelo_previsao.py` em {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC, "
        f"a partir de `dados/{ARQUIVOS[fonte].name}` ({modelo['fonte']}). Exporta "
        "`cloud/function/modelo_sensor.json`, lido pela rota `GET /api/predict/sensor`.",
        "",
        "## Problema",
        "",
        "Estimar a temperatura da carga daqui a 10 minutos a partir das últimas leituras do "
        "próprio sensor, para avisar antes de a leitura sair da faixa do perfil de carga. Apoia "
        "uma decisão humana (conferir a porta, o equipamento de frio, a rota); não dispara ação "
        "automática.",
        "",
        "## Limpeza",
        "",
        "| passo | removidas | restantes |",
        "|---|---|---|",
        *[f"| {p} | {r} | {n} |" for p, r, n in passos],
        "",
        f"Cadência medida: mediana {cadencia.median():.0f} s entre leituras na base inteira e "
        f"{ultimo.median():.0f} s no trecho mais recente; {len(dados) / 60:.1f} h de amostras "
        "no total. Trecho contínuo = "
        f"sem intervalo maior que {LACUNA_S} s; {n_trechos} trechos geraram amostras "
        f"(um instante por minuto, com {JANELA_MIN} min de histórico e o alvo "
        f"{HORIZONTE_MIN} min depois dentro do mesmo trecho). Valor entre leituras = última "
        "leitura até o instante.",
        "",
        "## Divisão temporal",
        "",
        "| conjunto | de (UTC) | até (UTC) | amostras |",
        "|---|---|---|---|",
        f"| treino | {modelo['treino']['de'][:16]} | {modelo['treino']['ate'][:16]} | "
        f"{modelo['treino']['amostras']} |",
        f"| teste | {modelo['teste']['de'][:16]} | {modelo['teste']['ate'][:16]} | "
        f"{modelo['teste']['amostras']} |",
        "",
        f"Teste = {FRACAO_TESTE:.0%} mais recentes dos instantes (corte {corte:%Y-%m-%d %H:%M} "
        f"UTC). Amostras de treino cujo alvo cai depois do corte foram descartadas.",
        "",
        "## Resultado (teste)",
        "",
        "| métrica | modelo (ridge) | baseline (persistência) |",
        "|---|---|---|",
        f"| MAE (°C) | {m['maeModelo']:.3f} | {m['maeBaseline']:.3f} |",
        f"| RMSE (°C) | {m['rmseModelo']:.3f} | {m['rmseBaseline']:.3f} |",
        "",
        veredito,
        "",
        "Coeficientes (variação prevista = soma de coeficiente × atributo, sem intercepto, "
        f"lambda = {LAMBDA}):",
        "",
        "| atributo | significado | coeficiente |",
        "|---|---|---|",
        f"| d5 | última leitura menos a de 5 min antes | {modelo['coeficientes'][0]:+.4f} |",
        f"| d10 | última leitura menos a de 10 min antes | {modelo['coeficientes'][1]:+.4f} |",
        f"| m10 | média dos últimos 10 min menos a última leitura | "
        f"{modelo['coeficientes'][2]:+.4f} |",
        "",
        "## Sensibilidade ao corte (informativo, não usado para escolher nada)",
        "",
        "| fração de teste | corte (UTC) | treino | teste | MAE modelo | MAE baseline | "
        "RMSE modelo | RMSE baseline |",
        "|---|---|---|---|---|---|---|---|",
        *[f"| {f:.0%} | {c:%Y-%m-%d %H:%M} | {a} | {b} | {r['maeModelo']:.3f} | "
          f"{r['maeBaseline']:.3f} | {r['rmseModelo']:.3f} | {r['rmseBaseline']:.3f} |"
          for f, c, a, b, r in sens],
        "",
        *secao_cruzada(cruzada),
        "## Limitações",
        "",
        f"- Dados limitados: {len(dados) / 60:.0f} h de amostras em {n_trechos} trechos "
        "separados por lacunas (a placa ficou desligada ou sem rede entre eles).",
        "- Outras tentativas fora do pipeline (regressão pela mediana, gradient boosting com erro "
        "absoluto, janela de 30 min com mais atributos, hora do dia) também não passaram da "
        "persistência no MAE; o resumo está em `docs/model-card.md`.",
        "- Sensor em bancada, em ambiente interno, não dentro de um baú refrigerado: não há "
        "nenhuma excursão térmica real (porta aberta, falha do frio) na base. A série é quase "
        "estável e varia em degraus de resolução do DHT11, cenário em que a persistência é "
        "difícil de bater.",
        "- O modelo não sabe nada de clima, rota ou porta: só extrapola a própria série.",
        "",
        "## Re-treinar",
        "",
        "```bash",
        "cd analise/sensor",
        "python descrever_cosmos.py --converter <export>/leituras.jsonl   # export do backup",
        "python modelo_previsao.py            # treina, avalia e exporta",
        "python modelo_previsao.py --baixar   # antes, atualiza o CSV do ThingSpeak (verificação)",
        "```",
        "",
        f"![teste]({FIGURA.parent.name}/{FIGURA.name})",
        "",
    ]
    RELATORIO.write_text("\n".join(linhas), encoding="utf-8")


def secao_cruzada(cruzada):
    """Linhas do relatório com o mesmo pipeline na outra fonte (vazio se não houver)."""
    if cruzada is None:
        return []
    nome, n_treino, n_teste, m = cruzada
    return [
        "## Verificação cruzada",
        "",
        f"Mesmo pipeline (mesmos atributos, lambda e 30% de teste) sobre `dados/{nome}`, "
        "só para conferir que o resultado não depende da fonte:",
        "",
        "| treino | teste | MAE modelo | MAE baseline | RMSE modelo | RMSE baseline |",
        "|---|---|---|---|---|---|",
        f"| {n_treino} | {n_teste} | {m['maeModelo']:.3f} | {m['maeBaseline']:.3f} | "
        f"{m['rmseModelo']:.3f} | {m['rmseBaseline']:.3f} |",
        "",
    ]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--baixar" in argv:
        import baixar_thingspeak
        baixar_thingspeak.main()
    fonte = "cosmos" if CSV_COSMOS.exists() else "thingspeak"
    outra = CSV_THINGSPEAK if fonte == "cosmos" else CSV_COSMOS
    serie, passos, dados, treino, teste, corte, coef, metricas = treinar(carregar(ARQUIVOS[fonte]))
    modelo = montar_modelo(treino, teste, coef, metricas, fonte)
    SAIDA_MODELO.write_text(json.dumps(modelo, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    figura(teste, coef)
    cruzada = None
    if outra.exists():
        cruzada = (outra.name, *verificacao_cruzada(outra))
    relatorio(passos, serie, dados, treino, teste, corte, modelo, sensibilidade(dados), fonte,
              cruzada)
    print(json.dumps(modelo["metricas"]), "superaBaseline =", modelo["superaBaseline"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
