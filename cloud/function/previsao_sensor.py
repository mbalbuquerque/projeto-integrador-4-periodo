"""Previsão de curto prazo da temperatura do sensor, servida pela rota GET /api/predict/sensor.

O modelo é o arquivo exportado por analise/sensor/modelo_previsao.py (modelo_sensor.json, ao
lado deste arquivo): uma regressão linear (ridge, sem intercepto) que estima quanto a
temperatura muda nos próximos `horizonteMin` minutos a partir das variações recentes da
própria série do sensor. O baseline é a persistência (a temperatura daqui a `horizonteMin`
minutos é igual à última leitura).

As funções de série (trechos, valor_em, atributos) são as mesmas usadas no treino, para o
atributo calculado na rota ser idêntico ao do treino. Sem pandas, numpy ou scikit-learn.
"""

import bisect
import json
import os
from datetime import datetime, timedelta

from contrato import PERFIL_PADRAO, PERFIS_CARGA, classificar

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQUIVO = os.path.join(PASTA, "modelo_sensor.json")

# Gravidade de cada status, para dizer se a previsão piora a situação atual.
GRAVIDADE = {"NORMAL": 0, "ATENCAO": 1, "CRITICO": 2}

_modelo = None


def carregar(caminho=ARQUIVO):
    """modelo_sensor.json do disco, lido uma vez por instância (OSError se faltar)."""
    global _modelo
    if _modelo is None:
        with open(caminho, encoding="utf-8") as f:
            _modelo = json.load(f)
    return _modelo


def instante(texto):
    """datetime com fuso de um ISO 8601, ou None se faltar ou estiver quebrado."""
    try:
        momento = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return momento if momento.tzinfo is not None else None


def serie_de_leituras(leituras):
    """[(momento, temperatura)] em ordem crescente, sem leitura sem data ou sem número.

    Duas leituras no mesmo instante ficam uma só (a primeira que aparece).
    """
    pares = {}
    for item in leituras:
        momento = instante(item.get("medidoEm"))
        valor = item.get("temperatura")
        if momento is None or isinstance(valor, bool) or not isinstance(valor, (int, float)):
            continue
        pares.setdefault(momento, float(valor))
    return sorted(pares.items())


def trechos(serie, lacuna_s):
    """Divide a série em trechos contínuos: um intervalo maior que lacuna_s abre trecho novo."""
    saida, atual = [], []
    for par in serie:
        if atual and (par[0] - atual[-1][0]).total_seconds() > lacuna_s:
            saida.append(atual)
            atual = []
        atual.append(par)
    if atual:
        saida.append(atual)
    return saida


def valor_em(trecho, tempos, momento):
    """Última temperatura medida até `momento` (inclusive), ou None se ele vem antes do trecho."""
    i = bisect.bisect_right(tempos, momento)
    return trecho[i - 1][1] if i else None


def atributos(trecho, momento, janela_min):
    """Atributos no instante `momento`, a partir de um trecho contínuo.

    y0 é o último valor até `momento`; d5 e d10, a variação contra 5 e 10 minutos antes;
    m10, a média dos valores minuto a minuto da janela menos y0. None se o trecho não cobre
    a janela inteira (começa depois de `momento - janela_min`).
    """
    if not trecho or trecho[0][0] > momento - timedelta(minutes=janela_min):
        return None
    tempos = [p[0] for p in trecho]
    v = [valor_em(trecho, tempos, momento - timedelta(minutes=k)) for k in range(janela_min + 1)]
    y0 = v[0]
    return {"y0": y0, "d5": y0 - v[5], "d10": y0 - v[janela_min],
            "m10": sum(v[:janela_min]) / janela_min - y0}


def estimar(modelo, atrib):
    """Temperatura prevista: y0 mais a variação estimada pelos coeficientes."""
    variacao = sum(c * atrib[nome] for nome, c in zip(modelo["atributos"], modelo["coeficientes"]))
    return atrib["y0"] + variacao


def _com_status(temperatura, perfil):
    return {"temperatura": round(temperatura, 1), "status": classificar(temperatura, perfil)}


def prever(modelo, leituras, agora):
    """Resposta da rota a partir das leituras recentes de um sensor (qualquer ordem).

    `previsao` (modelo) e `baseline` (persistência) saem None quando não há base: sem
    leituras, última leitura velha demais (sensor sem sinal) ou, só para o modelo, menos de
    `janelaMin` minutos contínuos de histórico. `recomendada` diz qual das duas ganhou no
    teste temporal; é ela que a tela deve mostrar.
    """
    horizonte = modelo["horizonteMin"]
    serie = serie_de_leituras(leituras)
    corpo = {
        "horizonteMin": horizonte,
        "ultimaLeitura": None,
        "previsao": None,
        "baseline": None,
        "recomendada": "modelo" if modelo["superaBaseline"] else "baseline",
        "antecipaExcursao": False,
        "motivo": None,
        "modelo": {
            "versao": modelo["versao"],
            "fonte": modelo["fonte"],
            "treino": modelo["treino"],
            "teste": modelo["teste"],
            "maeModelo": modelo["metricas"]["maeModelo"],
            "maeBaseline": modelo["metricas"]["maeBaseline"],
            "rmseModelo": modelo["metricas"]["rmseModelo"],
            "rmseBaseline": modelo["metricas"]["rmseBaseline"],
            "superaBaseline": modelo["superaBaseline"],
            "usaLeiturasDoSensor": True,
        },
    }
    if not serie:
        corpo["motivo"] = "sem_leituras"
        return corpo

    perfil = _perfil_mais_recente(leituras)
    momento, valor = serie[-1]
    corpo["ultimaLeitura"] = {"medidoEm": momento.isoformat(), "perfil": perfil,
                              **_com_status(valor, perfil)}
    if (agora - momento).total_seconds() > modelo["lacunaMaxS"]:
        corpo["motivo"] = "sem_leitura_recente"
        return corpo

    para = (momento + timedelta(minutes=horizonte)).isoformat()
    corpo["baseline"] = {"para": para, **_com_status(valor, perfil)}
    atrib = atributos(trechos(serie, modelo["lacunaMaxS"])[-1], momento, modelo["janelaMin"])
    if atrib is None:
        corpo["motivo"] = "historico_insuficiente"
    else:
        corpo["previsao"] = {"para": para, **_com_status(estimar(modelo, atrib), perfil)}

    escolhida = corpo["previsao"] if corpo["recomendada"] == "modelo" else corpo["baseline"]
    if escolhida is not None:
        corpo["antecipaExcursao"] = (GRAVIDADE[escolhida["status"]]
                                     > GRAVIDADE[corpo["ultimaLeitura"]["status"]])
    return corpo


def _perfil_mais_recente(leituras):
    """Perfil de carga gravado na leitura mais nova; o padrão se faltar ou for desconhecido."""
    datadas = [(instante(i.get("medidoEm")), i.get("perfil")) for i in leituras]
    datadas = [d for d in datadas if d[0] is not None]
    perfil = max(datadas, key=lambda d: d[0])[1] if datadas else None
    return perfil if perfil in PERFIS_CARGA else PERFIL_PADRAO
