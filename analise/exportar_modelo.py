"""Exporta o modelo de risco térmico para um JSON leve, servido pela rota /api/predict.

A Function não carrega pandas nem scikit-learn: o modelo é uma tabela de 12 meses x 24
horas com a probabilidade de a temperatura externa passar de 30 °C, e a rota só consulta
a célula pedida. Este script recalcula a tabela com os mesmos anos de treino e de teste
de explorar.py (divisão temporal) e grava junto as métricas medidas nos anos de teste.

Entrada: dados/inmet_rota_horario.csv (limpar.py)
Saída:   ../cloud/function/modelo_risco.json

Uso:  python exportar_modelo.py
"""

import json
import math
from pathlib import Path

from explorar import ANOS_TESTE, ANOS_TREINO, LIMIAR, avaliar, carregar

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI.parent / "cloud" / "function" / "modelo_risco.json"

ESTACAO = "A307"
VERSAO = "clima-a307-30c-v1"

# Faixas de risco: "alto" coincide com o corte de 50% usado na avaliação ("hora de risco").
NIVEIS = [
    {"nivel": "baixo", "ate": 0.2},
    {"nivel": "moderado", "ate": 0.5},
    {"nivel": "alto", "ate": 1.0},
]


def horas_por_celula(treino):
    """Quantidade de horas de treino em cada (mês, hora): mostra quanto dado sustenta a célula."""
    base = treino.dropna(subset=["temperatura_c"])
    return (base.pivot_table(index="mes", columns="hora", values="temperatura_c",
                             aggfunc="size")
            .reindex(index=range(1, 13), columns=range(24)))


def montar(p):
    """Monta o dicionário exportado a partir das leituras horárias de uma estação."""
    modelo = avaliar(p)
    treino = p[p["ano"].isin(ANOS_TREINO)].dropna(subset=["temperatura_c"])
    baseline = float((treino["temperatura_c"] > LIMIAR).mean())
    contagem = horas_por_celula(treino)

    def valor(v, padrao):
        return padrao if v is None or (isinstance(v, float) and math.isnan(v)) else v

    # Célula sem hora de treino usa o baseline, como faz a avaliação em explorar.py.
    probabilidade = [[round(float(valor(modelo["tabela"].loc[m, h], baseline)), 4)
                      for h in range(24)] for m in range(1, 13)]
    horas = [[int(valor(contagem.loc[m, h], 0)) for h in range(24)] for m in range(1, 13)]

    return {
        "versao": VERSAO,
        "descricao": ("Climatological probability that the outdoor air temperature exceeds "
                      f"{LIMIAR:.0f} °C, per month and hour (Brasília time), INMET station "
                      f"{ESTACAO} Petrolina. It does not use the readings of the cargo sensor."),
        "fonte": f"INMET, estação automática {ESTACAO} (Petrolina), dados horários",
        "limiarC": LIMIAR,
        "anosTreino": ANOS_TREINO,
        "anosTeste": ANOS_TESTE,
        "horasTreino": modelo["horas_treino"],
        "horasTeste": modelo["horas_teste"],
        "metricas": {
            "brierModelo": round(float(modelo["brier_modelo"]), 4),
            "brierBaseline": round(float(modelo["brier_ingenuo"]), 4),
            "ganhoPct": round(float(modelo["ganho_pct"]), 1),
            "acertoPct": round(float(modelo["acerto_pct"]), 1),
            "sensibilidadePct": round(float(modelo["sensibilidade_pct"]), 1),
        },
        "baseline": round(baseline, 4),
        "niveis": NIVEIS,
        "probabilidade": probabilidade,
        "horasPorCelula": horas,
    }


def serializar(dados):
    """JSON legível: campos um por linha e cada mês da tabela numa linha só."""
    tabelas = ("probabilidade", "horasPorCelula")
    resto = {k: v for k, v in dados.items() if k not in tabelas}
    texto = json.dumps(resto, ensure_ascii=False, indent=1)[:-2]
    for nome in tabelas:
        linhas = ",\n  ".join(json.dumps(linha) for linha in dados[nome])
        texto += f',\n "{nome}": [\n  {linhas}\n ]'
    return texto + "\n}\n"


def main():
    t = carregar()
    p = t[t["codigo"] == ESTACAO].copy()
    dados = montar(p)
    SAIDA.write_text(serializar(dados), encoding="utf-8")
    m = dados["metricas"]
    print(f"{SAIDA.name}: versão {dados['versao']}, Brier modelo {m['brierModelo']} "
          f"vs baseline {m['brierBaseline']} ({m['ganhoPct']}% melhor), "
          f"{dados['horasTreino']} horas de treino, {dados['horasTeste']} de teste")


if __name__ == "__main__":
    main()
