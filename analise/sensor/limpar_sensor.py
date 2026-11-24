"""Limpeza da base do sensor (leituras gravadas no Cosmos), passo a passo, com contagens.

Uso:
    python limpar_sensor.py <leituras.jsonl>           # imprime a tabela de limpeza
    python limpar_sensor.py <leituras.jsonl> --gerar   # grava limpeza.md

O .jsonl vem de `infra/backup/exportar.py` (container `leituras`). A base limpa é a mesma que
`descrever_cosmos.py --converter` grava em `dados/cosmos_leituras.csv` e que
`modelo_previsao.py` usa no treino; `confere_csv` prova que as duas saídas batem.

Cada passo remove só o que ele descreve, na ordem abaixo, e a tabela mostra quantas leituras
saíram em cada um. Lacunas de coleta não removem leitura: são contadas à parte, porque o
modelo e o relatório de cobertura as tratam como quebra de trecho.
"""

import argparse
import json
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).parent
CSV = AQUI / "dados" / "cosmos_leituras.csv"
SAIDA = AQUI / "limpeza.md"
DEVICE = "coldtrack-0e0b2c"                      # a placa física do PI
FAIXAS = {"temperatura": (0.0, 50.0), "umidade": (20.0, 90.0)}   # datasheet do DHT11
INTERVALO_S = 20
LACUNA_S = 120                                   # lacuna = intervalo maior que 2 min


def carregar(jsonl):
    """DataFrame com as colunas usadas na limpeza (sem e-mail, senha ou chave)."""
    linhas = []
    for texto in Path(jsonl).read_text(encoding="utf-8").splitlines():
        if not texto.strip():
            continue
        d = json.loads(texto)
        linhas.append({"deviceId": d.get("deviceId"), "seq": d.get("seq"),
                       "medido_em": d.get("medidoEm"), "temperatura": d.get("temperatura"),
                       "umidade": d.get("umidade"), "rssi": d.get("rssi")})
    df = pd.DataFrame(linhas, columns=["deviceId", "seq", "medido_em", "temperatura",
                                       "umidade", "rssi"])
    df["medido_em"] = pd.to_datetime(df["medido_em"], utc=True, format="ISO8601",
                                     errors="coerce")
    return df


def limpar(df, device=DEVICE, faixas=FAIXAS):
    """(base limpa, passos [(passo, removidas, restantes)]), na ordem em que são aplicados."""
    passos = [("leituras no container", 0, len(df))]

    def passo(nome, novo):
        nonlocal df
        passos.append((nome, len(df) - len(novo), len(novo)))
        df = novo

    passo("de outro dispositivo (testes de push)", df[df["deviceId"] == device])
    passo("sem número de sequência (`seq`)", df[df["seq"].notna()])
    df = df.assign(seq=df["seq"].astype(int))
    passo("`seq` repetido (reenvio idêntico)", df.sort_values("seq").drop_duplicates("seq"))
    passo("sem data ou sem temperatura", df.dropna(subset=["medido_em", "temperatura"]))
    lo, hi = faixas["temperatura"]
    passo(f"temperatura fora de {lo:g} a {hi:g} °C (faixa do DHT11)",
          df[df["temperatura"].between(lo, hi)])
    lo, hi = faixas["umidade"]
    invalida = df["umidade"].notna() & ~df["umidade"].between(lo, hi)
    passo(f"umidade fora de {lo:g} a {hi:g} % (faixa do DHT11)", df[~invalida])
    passo("instante repetido", df.sort_values("medido_em").drop_duplicates("medido_em"))
    return df.sort_values("medido_em").reset_index(drop=True), passos


def lacunas(df, lacuna_s=LACUNA_S):
    """Intervalos entre leituras vizinhas maiores que `lacuna_s`: [(inicio, fim, segundos)]."""
    t = df["medido_em"].reset_index(drop=True)
    d = t.diff().dt.total_seconds()
    return [(t[i - 1], t[i], float(d[i])) for i in d.index[d > lacuna_s]]


def faltantes(df):
    """Números de `seq` que faltam entre o menor e o maior (perda medida pela sequência)."""
    if df.empty:
        return 0, 0.0
    faixa = int(df["seq"].max() - df["seq"].min() + 1)
    faltam = faixa - df["seq"].nunique()
    return faltam, faltam / faixa


def confere_csv(limpa, csv=CSV):
    """Compara a base limpa com `dados/cosmos_leituras.csv` (a que alimenta o modelo)."""
    if not Path(csv).exists():
        return None
    base = pd.read_csv(csv)
    return {"linhas_csv": len(base), "linhas_limpas": len(limpa),
            "mesmas_seq": set(base["seq"]) <= set(limpa["seq"])}


def relatorio(passos, limpa, cruzamento):
    n_lac = lacunas(limpa)
    faltam, perda = faltantes(limpa)
    horas = (limpa["medido_em"].max() - limpa["medido_em"].min()).total_seconds() / 3600
    linhas = [
        "# Limpeza da base do sensor",
        "",
        "Gerado por `limpar_sensor.py` a partir do container `leituras` do Cosmos (export de "
        "17 a 24/11/2026). Requisito do plano de ação (#138). Os números saem todos do export; "
        "nada é estimado à mão. O export bruto tem endereço de e-mail em outros containers e "
        "fica fora do repositório; só o CSV sem dado pessoal (`dados/cosmos_leituras.csv`) é "
        "versionado.",
        "",
        "## Passo a passo",
        "",
        "| passo | removidas | restantes |",
        "|---|---|---|",
    ]
    for nome, removidas, restantes in passos:
        linhas.append(f"| {nome} | {removidas} | {restantes} |")
    linhas += [
        "",
        f"A base limpa tem **{len(limpa)} leituras**, de {limpa['medido_em'].min():%d/%m %H:%M} "
        f"a {limpa['medido_em'].max():%d/%m %H:%M} UTC ({horas:.1f} h entre a primeira e a "
        "última).",
        "",
        "## O que cada passo trata",
        "",
        "- **Outro dispositivo:** leituras `teste-push*`, enviadas para testar o alerta push; "
        "não são da placa.",
        "- **Sem `seq`:** leituras gravadas antes de o firmware numerar as mensagens (R3); sem "
        "número não dá para medir perda nem detectar duplicata.",
        "- **`seq` repetido:** reenvio idêntico da fila; a API já responde `duplicada`, e este "
        "passo garante a mesma regra na análise.",
        "- **Sem data ou temperatura:** leitura que o DHT não conseguiu fazer (a placa marca "
        "como inválida e não grava como válida; aqui é só a segunda barreira).",
        "- **Fora da faixa:** valores fisicamente impossíveis para o DHT11 (datasheet: 0 a "
        "50 °C e 20 a 90 % de umidade).",
        "- **Instante repetido:** duas leituras no mesmo segundo (a série do modelo precisa de "
        "instantes únicos).",
        "",
        "## Lacunas e perda (não removem leitura)",
        "",
        f"- Lacunas maiores que {LACUNA_S // 60} min na base limpa: **{len(n_lac)}**"
        + (f" (maior: {max(x[2] for x in n_lac) / 60:.1f} min)." if n_lac else "."),
        f"- Números de `seq` faltando entre o menor e o maior: **{faltam}** "
        f"({100 * perda:.2f}% da faixa).",
        "- O modelo quebra a série em trechos nas lacunas (`LACUNA_S` em `modelo_previsao.py`), "
        "então nenhum alvo atravessa um buraco.",
        "",
        "## Ligação com o modelo",
        "",
    ]
    if cruzamento:
        igual = cruzamento["linhas_csv"] == cruzamento["linhas_limpas"]
        veredito = "mesma quantidade" if igual else "quantidade diferente: outro export"
        linhas.append(
            f"`dados/cosmos_leituras.csv`, que alimenta `modelo_previsao.py`, tem "
            f"{cruzamento['linhas_csv']} linhas; esta limpeza deixa {cruzamento['linhas_limpas']}"
            f" ({veredito}). "
            "Todas as `seq` do CSV estão na base limpa: "
            f"**{'sim' if cruzamento['mesmas_seq'] else 'NÃO'}**. "
            "Depois disso `modelo_previsao.py` ainda descarta, na temperatura, vazio, fora de "
            "0 a 50 °C e instante repetido (a tabela de limpeza dele, em `relatorio_previsao.md`).")
    else:
        linhas.append("`dados/cosmos_leituras.csv` não encontrado para a comparação.")
    linhas += [
        "",
        "## Reproduzir",
        "",
        "```",
        "python infra/backup/exportar.py <pasta-fora-do-repo> --excluir limites usuarios",
        "python analise/sensor/limpar_sensor.py <pasta>/leituras.jsonl --gerar",
        "```",
        "",
    ]
    return "\n".join(linhas)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("jsonl", help="leituras.jsonl exportado do Cosmos")
    p.add_argument("--gerar", action="store_true", help=f"grava {SAIDA.name}")
    args = p.parse_args(argv)
    limpa, passos = limpar(carregar(args.jsonl))
    texto = relatorio(passos, limpa, confere_csv(limpa))
    if args.gerar:
        SAIDA.write_text(texto, encoding="utf-8", newline="\n")
        print(f"relatório em {SAIDA}")
    else:
        print(texto)


if __name__ == "__main__":
    main()
