"""Testes unitários de lacunas, janelas e validação (descrever.py), com dados sintéticos."""

import pandas as pd
import pytest
from descrever import (calcular, estatistica, intervalos, invalidos, janelas_continuas,
                       lacunas, relatorio)


def serie(segundos):
    base = pd.Timestamp("2026-10-08 12:00:00", tz="UTC")
    return pd.Series([base + pd.Timedelta(seconds=s) for s in segundos])


def test_intervalos():
    assert intervalos(serie([0, 20, 45])).tolist() == [20.0, 25.0]


def test_lacunas_so_acima_de_2x():
    # 40 s exatos não é lacuna; 41 s é.
    assert lacunas(serie([0, 20, 60])) == []
    ls = lacunas(serie([0, 20, 61, 81]))
    assert len(ls) == 1 and ls[0][2] == 41.0


def test_lacunas_vazio_e_unico():
    assert lacunas(serie([])) == []
    assert lacunas(serie([0])) == []


def test_janelas_continuas():
    j = janelas_continuas(serie([0, 20, 40, 1000, 1020, 5000]))
    assert [x[2] for x in j] == [3, 2, 1]
    assert (j[0][1] - j[0][0]).total_seconds() == 40
    assert janelas_continuas(serie([])) == []


def test_invalidos_nan_e_faixa():
    s = pd.Series([25.0, float("nan"), -1.0, 50.0, 50.1])
    assert invalidos(s, (0.0, 50.0)).tolist() == [False, True, True, False, True]


def test_estatistica_ignora_nan():
    e = estatistica(pd.Series([1.0, 2.0, 3.0, 4.0, float("nan")]))
    assert e["n"] == 4 and e["min"] == 1 and e["max"] == 4
    assert e["mediana"] == 2.5 and e["media"] == 2.5 and e["q1"] == 1.75


def df_sintetico():
    t = serie([0, 20, 40, 100000, 100020])
    return pd.DataFrame({"momento_utc": t, "temperatura": [25, 26, 60, 25, 25.5],
                         "umidade": [50, 50, 50, 10, 50], "rssi": [-50, -51, None, -52, -50]})


def test_calcular_e_relatorio():
    m = calcular(df_sintetico())
    assert m["n"] == 5 and len(m["lacunas"]) == 1 and len(m["janelas"]) == 2
    assert m["maior"][2] == 3
    assert m["inv"]["temperatura"]["sensor"] == 1      # 60 °C fora do DHT11
    assert m["inv"]["temperatura"]["api"] == 0         # 60 °C ainda cabe na faixa da API
    assert m["inv"]["umidade"]["sensor"] == 1          # 10 % abaixo do mínimo do DHT11
    assert m["inv"]["rssi"]["nan"] == 1
    assert m["linhas_inv_sensor"] == 2 and m["linhas_inv_api"] == 0
    texto = relatorio(m)
    assert "Não atendida" in texto                      # sem 48 h contínuas
    assert "Estatística descritiva" in texto


def test_veredito_atendido_com_48h_continuas():
    t = serie(list(range(0, 49 * 3600, 20)))
    df = pd.DataFrame({"momento_utc": t, "temperatura": 25.0, "umidade": 50.0, "rssi": -50.0})
    m = calcular(df)
    assert m["lacunas"] == [] and len(m["janelas"]) == 1
    assert "**Atendida.**" in relatorio(m)
