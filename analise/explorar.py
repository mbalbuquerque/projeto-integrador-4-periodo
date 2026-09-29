"""Análise exploratória do clima na rota Petrolina -> Suape e modelo
preliminar de risco térmico para o transporte refrigerado.

Pergunta: quando e onde o calor externo mais ameaça a carga do baú?
O compressor do baú trabalha contra a temperatura de fora; quanto mais
quente e seco, maior o risco de a carga sair da faixa se houver porta
aberta, parada ao sol ou falha de refrigeração.

Entrada: dados/inmet_rota_horario.csv (limpar.py)
Saída:   figuras/*.png e relatorio.md

Modelo preliminar: probabilidade de a temperatura externa passar de 30 °C
em cada combinação de mês e hora do dia, estimada com os anos de treino e
avaliada nos anos de teste (dados que o modelo não viu), comparada com um
modelo ingênuo que usa só a média geral.

Uso:  python explorar.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).resolve().parent
ENTRADA = AQUI / "dados" / "inmet_rota_horario.csv"
FIGURAS = AQUI / "figuras"
RELATORIO = AQUI / "relatorio.md"

LIMIAR = 30.0          # °C: calor externo que exige atenção na operação
LIMIAR_EXTREMO = 35.0
UMIDADE_BAIXA = 30.0   # %: ar seco acelera a perda de água da fruta
ANOS_TREINO = [2019, 2020, 2021, 2022]
ANOS_TESTE = [2023, 2024, 2025]

ROTA = ["A307", "A329", "A370", "A350", "A309", "A341", "A301"]
NOMES = {"A307": "Petrolina", "A329": "Cabrobó", "A370": "Salgueiro", "A350": "Serra Talhada",
         "A309": "Arcoverde", "A341": "Caruaru", "A301": "Recife"}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Cores: tinta de texto neutra, uma cor por série, sequencial de um tom só.
TINTA = "#1f2933"
TINTA_APOIO = "#52606d"
GRADE = "#e4e7eb"
AZUL = "#1f5fbf"
LARANJA = "#c2410c"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRADE,
    "axes.labelcolor": TINTA_APOIO, "xtick.color": TINTA_APOIO, "ytick.color": TINTA_APOIO,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": TINTA,
    "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 160,
})


def carregar():
    t = pd.read_csv(ENTRADA, parse_dates=["datahora"])
    t["ano"] = t["datahora"].dt.year
    t["mes"] = t["datahora"].dt.month
    t["hora"] = t["datahora"].dt.hour
    return t


# ---------------------------------------------------------------- figuras

def fig_perfil_mensal(p):
    diario = (p.dropna(subset=["temperatura_c"])
              .groupby(p["datahora"].dt.date)
              .agg(maxima=("temperatura_c", "max"), minima=("temperatura_c", "min"),
                   mes=("mes", "first"), horas=("temperatura_c", "size")))
    diario = diario[diario["horas"] >= 20]  # só dias quase completos
    mensal = diario.groupby("mes")[["maxima", "minima"]].mean()

    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(mensal.index, mensal["maxima"], color=LARANJA, lw=2, marker="o", ms=4)
    ax.plot(mensal.index, mensal["minima"], color=AZUL, lw=2, marker="o", ms=4)
    ax.hlines(LIMIAR, 0.7, 12.2, color=TINTA_APOIO, lw=1, ls="--")
    ax.text(12.3, LIMIAR, f"{LIMIAR:.0f} °C", va="center", color=TINTA_APOIO, fontsize=9)
    ax.text(12.3, mensal["maxima"].iloc[-1], "máxima do dia", va="center", color=TINTA, fontsize=9)
    ax.text(12.3, mensal["minima"].iloc[-1], "mínima do dia", va="center", color=TINTA, fontsize=9)
    ax.set_xticks(range(1, 13), MESES)
    ax.set_xlim(0.7, 14.2)
    ax.set_ylabel("°C (média dos dias)")
    ax.grid(axis="y", color=GRADE)
    ax.set_title("Petrolina: máxima e mínima diárias por mês")
    fig.tight_layout()
    fig.savefig(FIGURAS / "perfil_mensal_petrolina.png")
    plt.close(fig)
    return mensal, len(diario)


def fig_risco_hora_mes(tabela, titulo, arquivo):
    fig, ax = plt.subplots(figsize=(9, 3.9))
    im = ax.imshow(tabela.values, aspect="auto", cmap="Blues", vmin=0, vmax=1)
    ax.set_yticks(range(12), MESES)
    ax.set_xticks(range(0, 24, 2), [f"{h}h" for h in range(0, 24, 2)])
    ax.set_xlabel("hora do dia (horário de Brasília)")
    for (i, j), v in pd.DataFrame(tabela.values).stack().items():
        if v >= 0.05 and j % 2 == 0:
            ax.text(j, i, f"{v*100:.0f}", ha="center", va="center", fontsize=7,
                    color="white" if v > 0.55 else TINTA)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("chance de passar de 30 °C", color=TINTA_APOIO)
    cb.ax.yaxis.set_major_formatter(lambda v, _: f"{v*100:.0f}%")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(titulo)
    fig.tight_layout()
    fig.savefig(FIGURAS / arquivo)
    plt.close(fig)


def fig_rota(rota):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    x = list(range(len(rota)))
    ax.plot(x, rota["tarde"], color=LARANJA, lw=2, marker="o", ms=5)
    ax.plot(x, rota["madrugada"], color=AZUL, lw=2, marker="o", ms=5)
    for c, xi in zip(rota.index, x):
        ax.text(xi, rota.loc[c, "tarde"] + 0.9, NOMES[c], ha="center", fontsize=8, color=TINTA)
    ax.text(x[-1] + 0.15, rota["tarde"].iloc[-1], "tarde (12h–16h)", va="center", color=TINTA, fontsize=9)
    ax.text(x[-1] + 0.15, rota["madrugada"].iloc[-1], "madrugada (0h–5h)", va="center", color=TINTA, fontsize=9)
    ax.set_xlim(-0.4, x[-1] + 1.6)
    ax.set_xticks(x, [""] * len(x))
    ax.set_ylim(rota["madrugada"].min() - 2, rota["tarde"].max() + 3)
    ax.set_xlabel("estações na ordem da rota, do sertão ao litoral")
    ax.set_ylabel("°C médio (12 meses com o mesmo peso)")
    ax.grid(axis="y", color=GRADE)
    ax.set_title("Temperatura média ao longo da rota até o litoral")
    fig.tight_layout()
    fig.savefig(FIGURAS / "rota_tarde_madrugada.png")
    plt.close(fig)


# ---------------------------------------------------------------- modelo

def probabilidade(p):
    """P(T > limiar | mês, hora) — tabela 12 x 24."""
    base = p.dropna(subset=["temperatura_c"])
    return (base.assign(quente=base["temperatura_c"] > LIMIAR)
            .pivot_table(index="mes", columns="hora", values="quente", aggfunc="mean")
            .reindex(index=range(1, 13), columns=range(24)))


def avaliar(p):
    treino = p[p["ano"].isin(ANOS_TREINO)].dropna(subset=["temperatura_c"])
    teste = p[p["ano"].isin(ANOS_TESTE)].dropna(subset=["temperatura_c"])

    tabela = probabilidade(treino)
    media_geral = (treino["temperatura_c"] > LIMIAR).mean()

    real = (teste["temperatura_c"] > LIMIAR).astype(float)
    prev = [tabela.loc[m, h] for m, h in zip(teste["mes"], teste["hora"])]
    prev = pd.Series(prev, index=teste.index).fillna(media_geral)

    brier_modelo = ((prev - real) ** 2).mean()
    brier_ingenuo = ((media_geral - real) ** 2).mean()

    # Acerto ao classificar "hora de risco" quando a chance prevista passa de 50%.
    alerta = prev >= 0.5
    acerto = (alerta == real.astype(bool)).mean()
    sensibilidade = (alerta & real.astype(bool)).sum() / max(real.sum(), 1)

    return {
        "horas_treino": len(treino), "horas_teste": len(teste),
        "brier_modelo": brier_modelo, "brier_ingenuo": brier_ingenuo,
        "ganho_pct": 100 * (1 - brier_modelo / brier_ingenuo),
        "acerto_pct": 100 * acerto, "sensibilidade_pct": 100 * sensibilidade,
        "tabela": tabela,
    }


# ---------------------------------------------------------------- relatório

def main():
    FIGURAS.mkdir(exist_ok=True)
    t = carregar()
    p = t[t["codigo"] == "A307"].copy()
    pv = p.dropna(subset=["temperatura_c"])

    cobertura = (t.groupby("codigo")["temperatura_c"].agg(lambda s: 100 * s.notna().mean())
                 .reindex(ROTA).round(0))

    mensal, dias = fig_perfil_mensal(p)
    prob = probabilidade(p)
    fig_risco_hora_mes(prob, "Petrolina: chance de a temperatura externa passar de 30 °C",
                       "risco_hora_mes_petrolina.png")

    rv = t.dropna(subset=["temperatura_c"])
    # Média de cada mês primeiro, depois dos 12 meses: estações com buraco em
    # meses diferentes ficam comparáveis (sem isso, quem perdeu o verão parece fria).
    def media_equilibrada(faixa):
        parte = rv[rv["hora"].between(*faixa)]
        por_mes = parte.groupby(["codigo", "mes"])["temperatura_c"].mean().unstack()
        return por_mes[por_mes.notna().sum(axis=1) == 12].mean(axis=1)

    rota = pd.DataFrame({
        "tarde": media_equilibrada((12, 16)),
        "madrugada": media_equilibrada((0, 5)),
    }).reindex(ROTA).dropna()
    fig_rota(rota)

    modelo = avaliar(p)

    por_mes = pv.groupby("mes").agg(
        acima30=("temperatura_c", lambda s: 100 * (s > LIMIAR).mean()),
        acima35=("temperatura_c", lambda s: 100 * (s > LIMIAR_EXTREMO).mean()),
    )
    umid = p.dropna(subset=["umidade_pct"]).groupby("mes")["umidade_pct"].apply(
        lambda s: 100 * (s < UMIDADE_BAIXA).mean())
    por_mes["umidade_baixa"] = umid

    pior_mes = por_mes["acima30"].idxmax()
    melhor_mes = por_mes["acima30"].idxmin()
    horas_risco = prob.mean(axis=0)
    janela = [h for h in range(24) if horas_risco[h] < 0.05]
    pico = int(horas_risco.idxmax())

    linhas_mes = "\n".join(
        f"| {MESES[m-1]} | {mensal.loc[m, 'maxima']:.1f} | {mensal.loc[m, 'minima']:.1f} | "
        f"{por_mes.loc[m, 'acima30']:.0f}% | {por_mes.loc[m, 'acima35']:.0f}% | {por_mes.loc[m, 'umidade_baixa']:.0f}% |"
        for m in range(1, 13))
    linhas_rota = "\n".join(
        f"| {NOMES[c]} | {rota.loc[c, 'tarde']:.1f} | {rota.loc[c, 'madrugada']:.1f} |"
        for c in rota.index)
    linhas_cob = " · ".join(f"{NOMES[c]} {v:.0f}%" for c, v in cobertura.items())

    relatorio = f"""# Análise climática da rota Petrolina → Suape

Gerado por `explorar.py` a partir dos dados horários das estações automáticas do INMET
({min(t['ano'])}–{max(t['ano'])}). Estação principal: **A307 Petrolina** ({len(pv)} horas válidas, {dias} dias completos).

## Qualidade dos dados

Percentual de horas com temperatura válida por estação: {linhas_cob}.
As estações do INMET têm longos períodos sem leitura (sensor fora do ar): Petrolina não
registrou nenhuma hora em 2025 e perdeu metade de 2024; o arquivo de Recife vem vazio a
partir de 2022. Horas sem dado foram descartadas, nunca preenchidas. Isso reforça o valor
do sensor próprio no baú: a estação pública não garante série contínua.

## Calor em Petrolina ao longo do ano

![Máxima e mínima diárias por mês](figuras/perfil_mensal_petrolina.png)

| Mês | Máxima média (°C) | Mínima média (°C) | Horas > 30 °C | Horas > 35 °C | Horas com umidade < 30% |
|---|---|---|---|---|---|
{linhas_mes}

- Mês mais quente: **{MESES[pior_mes-1]}**, com {por_mes.loc[pior_mes, 'acima30']:.0f}% das horas acima de 30 °C.
- Mês mais ameno: **{MESES[melhor_mes-1]}**, com {por_mes.loc[melhor_mes, 'acima30']:.0f}%.
- O ar seco (umidade abaixo de 30%) aparece nos mesmos meses de calor, o que soma perda de
  água da fruta ao risco térmico.

## Janela de viagem

![Chance de passar de 30 °C por mês e hora](figuras/risco_hora_mes_petrolina.png)

- Pico de risco às **{pico}h**.
- Horas com menos de 5% de chance de passar de 30 °C em qualquer mês: **{', '.join(f'{h}h' for h in janela) or 'nenhuma'}**.
- Implicação operacional: carregar, abrir portas e fazer paradas longas fora da faixa do
  meio-dia ao fim da tarde, principalmente nos meses de maior calor.

## Calor ao longo da rota

![Temperatura média ao longo da rota](figuras/rota_tarde_madrugada.png)

| Estação (ordem da rota) | Tarde 12h–16h (°C) | Madrugada 0h–5h (°C) |
|---|---|---|
{linhas_rota}

O trecho do sertão (Petrolina a Serra Talhada) é o mais quente à tarde e o de madrugada
mais amena só no agreste (Arcoverde, Caruaru). O baú enfrenta a maior carga térmica na
primeira metade da viagem. A tarde de Caruaru ficou abaixo do esperado para a cidade e deve
ser conferida (possível viés da estação); ela não muda a conclusão sobre o sertão.

## Modelo preliminar de risco térmico

Estima a chance de a temperatura externa passar de {LIMIAR:.0f} °C para cada mês e hora do dia.
Treino: {', '.join(map(str, ANOS_TREINO))} ({modelo['horas_treino']} horas).
Teste em anos que o modelo não viu: {', '.join(map(str, ANOS_TESTE))} ({modelo['horas_teste']} horas).

| Métrica (anos de teste) | Valor |
|---|---|
| Erro quadrático da probabilidade (Brier) — modelo | {modelo['brier_modelo']:.3f} |
| Brier — modelo ingênuo (média geral) | {modelo['brier_ingenuo']:.3f} |
| Redução de erro sobre o ingênuo | {modelo['ganho_pct']:.0f}% |
| Acerto ao marcar "hora de risco" (chance ≥ 50%) | {modelo['acerto_pct']:.0f}% |
| Horas realmente acima de 30 °C que o modelo marcou | {modelo['sensibilidade_pct']:.0f}% |

Uso previsto: o painel mostra o risco externo esperado para a hora e o mês da viagem, e a
equipe pode antecipar a saída ou reforçar o monitoramento nos horários de maior risco.

## Limitações e próximos passos

- É um modelo climatológico: descreve o padrão típico, não a previsão do tempo do dia.
  O passo seguinte é usar a previsão do dia (API de previsão) no lugar da média histórica.
- Ainda não há dados de temperatura dentro do baú em viagem real. Com o protótipo físico,
  cruzar a telemetria de cada viagem com o clima externo para medir quanto o calor de fora
  explica as ocorrências fora da faixa.
- Falta cruzar com o calendário de exportação (volume por mês, ex.: Comex Stat) para
  ponderar o risco pelos meses de maior movimento.
"""
    RELATORIO.write_text(relatorio, encoding="utf-8")

    print(f"Petrolina: {len(pv)} horas válidas, {dias} dias completos")
    print(f"Pior mês: {MESES[pior_mes-1]} ({por_mes.loc[pior_mes, 'acima30']:.0f}% > 30 °C) · pico {pico}h")
    print(f"Janela segura: {janela}")
    print(f"Modelo: Brier {modelo['brier_modelo']:.3f} vs ingênuo {modelo['brier_ingenuo']:.3f} "
          f"({modelo['ganho_pct']:.0f}% melhor) · acerto {modelo['acerto_pct']:.0f}% · "
          f"sensibilidade {modelo['sensibilidade_pct']:.0f}%")
    print("Figuras em figuras/, relatório em relatorio.md")


if __name__ == "__main__":
    main()
