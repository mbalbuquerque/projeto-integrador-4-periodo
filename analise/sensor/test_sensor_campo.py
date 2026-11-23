import json

import pandas as pd

import medir_campo as mc

BASE = pd.Timestamp("2026-11-17 07:00", tz="UTC")


def _df(tmp_path, itens):
    """itens: (seq, segundos_desde_BASE, atraso_s)."""
    linhas = []
    for seq, seg, atraso in itens:
        t = BASE + pd.Timedelta(seconds=seg)
        linhas.append(json.dumps({"deviceId": mc.DEVICE, "seq": seq, "medidoEm": t.isoformat(),
                                  "recebidoEm": (t + pd.Timedelta(seconds=atraso)).isoformat()}))
    linhas.append(json.dumps({"deviceId": "outro", "seq": 1, "medidoEm": BASE.isoformat(),
                              "recebidoEm": BASE.isoformat()}))
    p = tmp_path / "l.jsonl"
    p.write_text("\n".join(linhas), encoding="utf-8")
    return mc.carregar(p, inicio="2026-11-17T00:00:00Z")


def test_perda_pela_sequencia_ignora_outro_dispositivo(tmp_path):
    df = _df(tmp_path, [(s, 20 * i, 3) for i, s in enumerate([1, 2, 3, 5, 6, 7, 8, 9, 10, 11])])  # falta o 4
    assert len(df) == 10
    assert mc.perda_janela(df["seq"]) == (10, 11, 1)


def test_placa_desligada_nao_e_perda():
    # a numeração continua de onde parou: 3 -> 4 mesmo com horas de pausa
    assert mc.perda_janela([1, 2, 3, 4, 5]) == (5, 5, 0)


def test_janelas_de_24h(tmp_path):
    # 26 h de leituras de hora em hora, com o seq 1 faltando (só a primeira janela o contém)
    itens = [(i, 3600 * i, 3) for i in range(27) if i != 1]
    df = _df(tmp_path, itens)
    jan = mc.janelas_24h(df)
    assert len(jan) == 3                                   # passo de 1 h: inícios em 0 h, 1 h e 2 h
    assert jan.iloc[0]["faltantes"] == 1
    assert jan.iloc[-1]["faltantes"] == 0                  # as outras janelas começam depois do seq 1
    assert (jan["perda"] >= 0).all()


def test_periodo_menor_que_24h_sem_janela(tmp_path):
    df = _df(tmp_path, [(i, 20 * i, 3) for i in range(10)])
    assert mc.janelas_24h(df).empty


def test_latencia_separa_tempo_real_de_reenvio(tmp_path):
    df = _df(tmp_path, [(1, 0, 4), (2, 20, 6), (3, 40, 300), (4, 60, 280), (5, 80, 5)])
    atraso, tempo_real = mc.latencias(df)
    r = mc.resumo_atraso(atraso[tempo_real])
    b = mc.resumo_atraso(atraso[~tempo_real])
    assert (r["n"], b["n"]) == (3, 2)
    assert r["mediana"] == 5 and r["max"] == 6
    assert b["max"] == 300


def test_resumo_de_serie_vazia():
    assert mc.resumo_atraso(pd.Series([], dtype=float))["n"] == 0


def test_reenvios_agrupam_seq_consecutivo(tmp_path):
    itens = [(1, 0, 3), (2, 20, 3), (3, 40, 500), (4, 60, 480), (5, 80, 3), (6, 100, 3), (7, 120, 400)]
    grupos = mc.reenvios(_df(tmp_path, itens))
    assert [(g["seq_ini"], g["seq_fim"], g["leituras"]) for g in grupos] == [(3, 4, 2), (7, 7, 1)]
    assert grupos[0]["em_ordem"] is True
    assert grupos[0]["atraso_max_s"] == 500


def test_lacunas_da_sequencia(tmp_path):
    df = _df(tmp_path, [(1, 0, 3), (2, 20, 3), (6, 100, 3), (7, 120, 3), (9, 160, 3)])
    assert [(g["seq_depois"], g["faltantes"]) for g in mc.lacunas_seq(df)] == [(6, 3), (9, 1)]


def test_sem_reenvio(tmp_path):
    assert mc.reenvios(_df(tmp_path, [(1, 0, 3), (2, 20, 3)])) == []


def test_relatorio_e_main(tmp_path):
    itens = [(i, 3600 * i, 4) for i in range(30)] + [(30, 3600 * 30, 700)]
    p = tmp_path / "l.jsonl"
    linhas = []
    for seq, seg, atraso in itens:
        t = BASE + pd.Timedelta(seconds=seg)
        linhas.append(json.dumps({"deviceId": mc.DEVICE, "seq": seq, "medidoEm": t.isoformat(),
                                  "recebidoEm": (t + pd.Timedelta(seconds=atraso)).isoformat()}))
    p.write_text("\n".join(linhas), encoding="utf-8")
    saida = tmp_path / "r.md"
    mc.main([str(p), "--inicio", "2026-11-17T00:00:00Z", "--saida", str(saida)])
    texto = saida.read_text(encoding="utf-8")
    assert "Perda em janelas de 24 h" in texto
    assert "reenvio(s)" in texto
    assert "Todas as janelas cumprem" in texto
