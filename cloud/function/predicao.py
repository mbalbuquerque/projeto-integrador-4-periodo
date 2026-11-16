"""Modelo de risco térmico servido pela rota GET /api/predict.

O modelo é a tabela exportada por analise/exportar_modelo.py (modelo_risco.json, ao lado
deste arquivo): probabilidade de a temperatura externa passar de 30 °C para cada mês e
hora do dia, medida na estação A307 Petrolina do INMET. Não usa as leituras do sensor
do baú. Sem pandas nem scikit-learn: a consulta é só ler a célula (mês, hora).
"""

import json
import os

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQUIVO = os.path.join(PASTA, "modelo_risco.json")

_modelo = None


def carregar(caminho=ARQUIVO):
    """modelo_risco.json do disco, lido uma vez por instância (OSError se faltar)."""
    global _modelo
    if _modelo is None:
        with open(caminho, encoding="utf-8") as f:
            _modelo = json.load(f)
    return _modelo


def _inteiro(texto, nome, minimo, maximo):
    try:
        valor = int(str(texto).strip())
    except (TypeError, ValueError):
        return None, f"{nome}: inteiro de {minimo} a {maximo}"
    if not minimo <= valor <= maximo:
        return None, f"{nome}: inteiro de {minimo} a {maximo}"
    return valor, None


def validar(params):
    """(erros, mês, hora) a partir dos parâmetros ?mes=1..12&hora=0..23."""
    mes, erro_mes = _inteiro(params.get("mes"), "mes", 1, 12)
    hora, erro_hora = _inteiro(params.get("hora"), "hora", 0, 23)
    erros = [e for e in (erro_mes, erro_hora) if e]
    return erros, mes, hora


def nivel(probabilidade, niveis):
    """Primeira faixa cujo teto alcança a probabilidade (a última fecha em 1.0)."""
    for faixa in niveis:
        if probabilidade <= faixa["ate"]:
            return faixa["nivel"]
    return niveis[-1]["nivel"]


def prever(modelo, mes, hora):
    """Resposta da rota para um mês (1..12) e uma hora (0..23) já validados."""
    prob = modelo["probabilidade"][mes - 1][hora]
    baseline = modelo["baseline"]
    return {
        "mes": mes,
        "hora": hora,
        "limiarC": modelo["limiarC"],
        "probabilidade": prob,
        "nivel": nivel(prob, modelo["niveis"]),
        "horasDeHistorico": modelo["horasPorCelula"][mes - 1][hora],
        "baseline": {
            "probabilidade": baseline,
            "nivel": nivel(baseline, modelo["niveis"]),
        },
        "modelo": {
            "versao": modelo["versao"],
            "fonte": modelo["fonte"],
            "anosTreino": modelo["anosTreino"],
            "anosTeste": modelo["anosTeste"],
            "brierModelo": modelo["metricas"]["brierModelo"],
            "brierBaseline": modelo["metricas"]["brierBaseline"],
            "usaLeiturasDoSensor": False,
        },
    }
