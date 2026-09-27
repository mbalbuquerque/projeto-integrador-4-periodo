"""Limpa os arquivos brutos do INMET e gera uma tabela horária única.

Entrada: dados/brutos/INMET_*.CSV (baixar_inmet.py)
Saída:   dados/inmet_rota_horario.csv
         colunas: codigo, estacao, datahora (horário de Brasília), temperatura_c,
                  umidade_pct, radiacao_kj_m2

Regras de limpeza:
- valores vazios ou -9999 (código de falta do INMET) viram ausentes;
- temperatura fora de -5 a 50 °C e umidade fora de 0 a 100 % são descartadas
  (leitura fisicamente impossível para a região = falha do sensor);
- hora UTC convertida para o horário de Brasília (UTC-3, sem horário de verão).

Uso:  python limpar.py
"""

from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
BRUTOS = AQUI / "dados" / "brutos"
SAIDA = AQUI / "dados" / "inmet_rota_horario.csv"

# Posição das colunas no layout do INMET (os nomes mudam de acento entre anos).
COL_DATA, COL_HORA, COL_RADIACAO, COL_TEMP, COL_UMID = 0, 1, 6, 7, 15

ORDEM_ROTA = ["A307", "A329", "A370", "A350", "A309", "A341", "A301"]


def numero(serie):
    valores = pd.to_numeric(
        serie.astype(str).str.strip().str.replace(",", ".", regex=False),
        errors="coerce",
    )
    return valores.mask(valores <= -9999)


def ler_estacao(arquivo):
    with open(arquivo, encoding="latin-1") as fh:
        cabecalho = [next(fh) for _ in range(8)]

    meta = dict(linha.strip().split(";", 1) for linha in cabecalho)
    codigo = meta["CODIGO (WMO):"].strip()
    estacao = meta["ESTACAO:"].strip().title()

    bruto = pd.read_csv(arquivo, sep=";", encoding="latin-1", skiprows=8,
                        header=0, dtype=str, index_col=False)

    data = bruto.iloc[:, COL_DATA].str.replace("-", "/", regex=False)
    hora = bruto.iloc[:, COL_HORA].str.replace(" UTC", "", regex=False).str.replace(":", "", regex=False).str.zfill(4)
    utc = pd.to_datetime(data + " " + hora, format="%Y/%m/%d %H%M", errors="coerce")

    tabela = pd.DataFrame({
        "codigo": codigo,
        "estacao": estacao,
        "datahora": utc - pd.Timedelta(hours=3),
        "temperatura_c": numero(bruto.iloc[:, COL_TEMP]),
        "umidade_pct": numero(bruto.iloc[:, COL_UMID]),
        "radiacao_kj_m2": numero(bruto.iloc[:, COL_RADIACAO]),
    })

    tabela.loc[~tabela["temperatura_c"].between(-5, 50), "temperatura_c"] = None
    tabela.loc[~tabela["umidade_pct"].between(0, 100), "umidade_pct"] = None

    return tabela.dropna(subset=["datahora"])


def main():
    arquivos = sorted(BRUTOS.glob("INMET_*.CSV"))
    if not arquivos:
        raise SystemExit("Nenhum arquivo em dados/brutos. Rode antes: python baixar_inmet.py")

    tabela = pd.concat([ler_estacao(a) for a in arquivos], ignore_index=True)
    tabela = tabela.drop_duplicates(subset=["codigo", "datahora"]).sort_values(["codigo", "datahora"])

    SAIDA.parent.mkdir(exist_ok=True)
    tabela.to_csv(SAIDA, index=False, float_format="%.1f")

    # Cobertura: quanto de cada estação tem temperatura válida.
    cobertura = (tabela.groupby(["codigo", "estacao"])["temperatura_c"]
                 .agg(horas="size", validas="count"))
    cobertura["cobertura_pct"] = (100 * cobertura["validas"] / cobertura["horas"]).round(1)
    cobertura = cobertura.reindex(ORDEM_ROTA, level=0)

    print(f"{len(tabela)} linhas salvas em {SAIDA.relative_to(AQUI)}")
    print(cobertura.to_string())


if __name__ == "__main__":
    main()
