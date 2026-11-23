import json

import pandas as pd

import descrever_cosmos as dc


def _jsonl(tmp_path, seqs, device=dc.DEVICE):
    base = pd.Timestamp("2026-11-17 07:00", tz="UTC")
    linhas = []
    for i, s in enumerate(seqs):
        t = base + pd.Timedelta(seconds=20 * i)
        linhas.append(json.dumps({"deviceId": device, "seq": s, "medidoEm": t.isoformat(),
                                  "temperatura": 30.0, "umidade": 50, "rssi": -50}))
    linhas.append(json.dumps({"deviceId": "outro", "seq": 1, "medidoEm": base.isoformat()}))
    p = tmp_path / "l.jsonl"
    p.write_text("\n".join(linhas), encoding="utf-8")
    return p


def test_perda_por_sequencia(tmp_path):
    p = _jsonl(tmp_path, [1, 2, 3, 5, 6, 7, 8, 9, 10, 11])   # falta o 4
    df = dc.converter(p, tmp_path / "c.csv")
    assert len(df) == 10                                    # ignora o outro dispositivo
    m = dc.calcular(dc.carregar(tmp_path / "c.csv"))
    assert m["faltantes"] == 1 and abs(m["perda"] - 1 / 11) < 1e-9
    assert m["duplicadas"] == 0 and not m["grandes"]


def test_lacuna_e_relatorio(tmp_path):
    p = _jsonl(tmp_path, [1, 2, 3, 4])
    linhas = p.read_text(encoding="utf-8").splitlines()
    d = json.loads(linhas[3])
    d["medidoEm"] = "2026-11-17T09:00:00+00:00"
    linhas[3] = json.dumps(d)
    p.write_text("\n".join(linhas), encoding="utf-8")
    dc.converter(p, tmp_path / "c.csv")
    m = dc.calcular(dc.carregar(tmp_path / "c.csv"))
    assert len(m["grandes"]) == 1
    texto = dc.relatorio(m)
    assert "taxa de perda" in texto and "Lacunas maiores" in texto
