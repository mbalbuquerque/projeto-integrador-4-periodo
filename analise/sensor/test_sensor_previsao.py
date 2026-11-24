"""Testes do pipeline de previsão (modelo_previsao.py) com série sintética, sem rede."""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import modelo_previsao as mp

T0 = datetime(2026, 11, 17, 0, 0, 10, tzinfo=timezone.utc)


def serie_sintetica(minutos=120, passo_s=20, inicio=T0, base=10.0):
    """Senoide lenta, uma leitura a cada `passo_s` segundos (dado sintético de teste)."""
    n = minutos * 60 // passo_s
    return [(inicio + timedelta(seconds=i * passo_s),
             base + np.sin(i * passo_s / 1800.0)) for i in range(n)]


def test_limpar_conta_cada_passo():
    df = pd.DataFrame({
        "momento_utc": pd.to_datetime(["2026-11-17T00:00:00Z", "2026-11-17T00:00:20Z",
                                       "2026-11-17T00:00:20Z", "2026-11-17T00:00:40Z",
                                       "2026-11-17T00:01:00Z"], utc=True),
        "temperatura": [10.0, 11.0, 11.0, None, 80.0],
    })
    serie, passos = mp.limpar(df)
    assert [v for _, v in serie] == [10.0, 11.0]
    assert [r for _, r, _ in passos] == [0, 1, 1, 1]
    assert passos[-1][2] == 2


def test_amostras_nao_atravessam_lacuna():
    trecho1 = serie_sintetica(minutos=30)
    trecho2 = serie_sintetica(minutos=30, inicio=T0 + timedelta(hours=2))
    dados = mp.amostras(trecho1 + trecho2)
    assert set(dados["trecho"]) == {0, 1}
    for _, parte in dados.groupby("trecho"):
        inicio = parte["momento"].min()
        fim = parte["momento"].max()
        assert fim - inicio <= timedelta(minutes=30 - mp.JANELA_MIN - mp.HORIZONTE_MIN)
    assert (dados["momento"].dt.second == 0).all()


def test_dividir_temporal_sem_vazamento():
    dados = mp.amostras(serie_sintetica(minutos=180))
    treino, teste, corte = mp.dividir(dados)
    assert teste["momento"].min() == corte
    assert (treino["momento"] + timedelta(minutes=mp.HORIZONTE_MIN) < corte).all()
    assert abs(len(teste) / len(dados) - mp.FRACAO_TESTE) < 0.02


def test_modelo_bate_persistencia_em_tendencia_e_exporta():
    # Em série com tendência suave e sem ruído, extrapolar a variação recente é melhor que
    # repetir a última leitura: o pipeline precisa enxergar isso.
    dados = mp.amostras(serie_sintetica(minutos=300))
    treino, teste, _ = mp.dividir(dados)
    coef = mp.ajustar(treino)
    metricas = mp.avaliar(teste, coef)
    assert metricas["maeModelo"] < metricas["maeBaseline"]
    modelo = mp.montar_modelo(treino, teste, coef, metricas, "cosmos")
    assert modelo["superaBaseline"] is True
    assert modelo["treino"]["ate"] < modelo["teste"]["de"]
    assert len(modelo["coeficientes"]) == len(mp.ATRIBUTOS)


def test_avaliar_persistencia_perfeita_em_serie_constante():
    dados = mp.amostras([(T0 + timedelta(seconds=20 * i), 5.0) for i in range(300)])
    treino, teste, _ = mp.dividir(dados)
    metricas = mp.avaliar(teste, mp.ajustar(treino))
    assert metricas["maeBaseline"] == 0.0
    assert metricas["maeModelo"] == 0.0
    modelo = mp.montar_modelo(treino, teste, mp.ajustar(treino), metricas, "thingspeak")
    assert modelo["superaBaseline"] is False


def test_sensibilidade_tem_uma_linha_por_corte():
    dados = mp.amostras(serie_sintetica(minutos=180))
    linhas = mp.sensibilidade(dados)
    assert [f for f, *_ in linhas] == list(mp.CORTES_SENSIBILIDADE)


def _csv(caminho, serie):
    pd.DataFrame({"momento_utc": [m.isoformat() for m, _ in serie],
                  "temperatura": [v for _, v in serie]}).to_csv(caminho, index=False)


def test_main_treina_exporta_e_faz_verificacao_cruzada(tmp_path, monkeypatch):
    cosmos, ts = tmp_path / "cosmos.csv", tmp_path / "ts.csv"
    _csv(cosmos, serie_sintetica(minutos=300))
    _csv(ts, serie_sintetica(minutos=300, base=12.0))
    monkeypatch.setattr(mp, "CSV_COSMOS", cosmos)
    monkeypatch.setattr(mp, "CSV_THINGSPEAK", ts)
    monkeypatch.setattr(mp, "ARQUIVOS", {"cosmos": cosmos, "thingspeak": ts})
    monkeypatch.setattr(mp, "SAIDA_MODELO", tmp_path / "modelo.json")
    monkeypatch.setattr(mp, "RELATORIO", tmp_path / "relatorio.md")
    monkeypatch.setattr(mp, "FIGURA", tmp_path / "fig" / "teste.png")
    assert mp.main([]) == 0
    modelo = json.loads((tmp_path / "modelo.json").read_text(encoding="utf-8"))
    assert modelo["versao"] == mp.VERSAO and modelo["fonte"] == mp.FONTES["cosmos"]
    texto = (tmp_path / "relatorio.md").read_text(encoding="utf-8")
    assert "## Verificação cruzada" in texto and "cosmos.csv" in texto and "ts.csv" in texto


def test_excursao_recorta_teste_e_vai_para_modelo_e_relatorio(monkeypatch):
    dados = mp.amostras(serie_sintetica(minutos=300))
    treino, teste, _ = mp.dividir(dados)
    coef = mp.ajustar(treino)
    de = teste["momento"].iloc[10].isoformat()
    ate = teste["momento"].iloc[29].isoformat()
    monkeypatch.setattr(mp, "EXCURSOES", [(de, ate)])
    assert len(mp.na_excursao(teste, [(de, ate)])) == 20
    modelo = mp.montar_modelo(treino, teste, coef, mp.avaliar(teste, coef), "cosmos")
    assert modelo["metricasExcursao"]["amostras"] == 20
    linhas = mp.secao_excursao(teste, modelo)
    assert "## Janela com excursão provocada (recorte do teste)" in linhas
    assert mp.mae_tendencia(teste.iloc[:0]) is None


def test_sem_excursao_no_teste_nao_gera_secao(monkeypatch):
    dados = mp.amostras(serie_sintetica(minutos=300))
    treino, teste, _ = mp.dividir(dados)
    coef = mp.ajustar(treino)
    monkeypatch.setattr(mp, "EXCURSOES", [])
    modelo = mp.montar_modelo(treino, teste, coef, mp.avaliar(teste, coef), "cosmos")
    assert modelo["metricasExcursao"] is None
    assert mp.secao_excursao(teste, modelo) == []
