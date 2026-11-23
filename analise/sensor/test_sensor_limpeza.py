"""Testes da limpeza da base do sensor (limpar_sensor.py), com dados sintéticos."""

import json

import pandas as pd

import limpar_sensor as ls

D = ls.DEVICE


def reg(seq, minuto, temp=30.0, umid=50.0, device=D, segundo=0):
    return {"deviceId": device, "seq": seq,
            "medidoEm": f"2026-11-17T10:{minuto:02d}:{segundo:02d}+00:00",
            "temperatura": temp, "umidade": umid, "rssi": -50}


def jsonl(tmp_path, registros):
    caminho = tmp_path / "leituras.jsonl"
    caminho.write_text("\n".join(json.dumps(r) for r in registros) + "\n", encoding="utf-8")
    return caminho


def passos_por_nome(passos):
    return {nome.split(" (")[0].split(" fora")[0]: removidas for nome, removidas, _ in passos}


def test_cada_passo_remove_so_o_que_descreve(tmp_path):
    registros = [
        reg(1, 0), reg(2, 1), reg(3, 2),
        reg(4, 3, device="teste-push"),                 # outro dispositivo
        {**reg(5, 4), "seq": None},                      # sem seq
        reg(2, 5),                                       # seq repetido (reenvio)
        reg(6, 6, temp=None),                            # sem temperatura
        reg(7, 7, temp=80.0),                            # temperatura fora da faixa
        reg(8, 8, umid=5.0),                             # umidade fora da faixa
        reg(9, 9, segundo=0),
        reg(10, 9, segundo=0),                           # mesmo instante que a seq 9
    ]
    limpa, passos = ls.limpar(ls.carregar(jsonl(tmp_path, registros)))
    removidas = [r for _, r, _ in passos]
    assert removidas == [0, 1, 1, 1, 1, 1, 1, 1]
    assert sorted(limpa["seq"]) == [1, 2, 3, 9]
    assert passos[-1][2] == len(limpa) == 4


def test_contagens_fecham(tmp_path):
    registros = [reg(i, i) for i in range(10)] + [reg(99, 11, device="teste-push")]
    limpa, passos = ls.limpar(ls.carregar(jsonl(tmp_path, registros)))
    for (_, removidas, restantes), (_, _, anteriores) in zip(passos[1:], passos):
        assert restantes == anteriores - removidas
    assert len(limpa) == 10


def test_faltantes_e_lacunas(tmp_path):
    registros = [reg(1, 0), reg(2, 1), reg(5, 10), reg(6, 11)]   # faltam seq 3 e 4; buraco de 9 min
    limpa, _ = ls.limpar(ls.carregar(jsonl(tmp_path, registros)))
    faltam, perda = ls.faltantes(limpa)
    assert faltam == 2 and abs(perda - 2 / 6) < 1e-9
    achadas = ls.lacunas(limpa)
    assert len(achadas) == 1 and achadas[0][2] == 540.0


def test_confere_csv_e_relatorio(tmp_path):
    registros = [reg(1, 0), reg(2, 1)]
    limpa, passos = ls.limpar(ls.carregar(jsonl(tmp_path, registros)))
    csv = tmp_path / "c.csv"
    pd.DataFrame({"seq": [1, 2]}).to_csv(csv, index=False)
    cruz = ls.confere_csv(limpa, csv)
    assert cruz == {"linhas_csv": 2, "linhas_limpas": 2, "mesmas_seq": True}
    texto = ls.relatorio(passos, limpa, cruz)
    assert "mesma quantidade" in texto and "| leituras no container | 0 | 2 |" in texto
    assert ls.confere_csv(limpa, tmp_path / "nao-existe.csv") is None


def test_main_imprime_e_grava(tmp_path, monkeypatch, capsys):
    arquivo = jsonl(tmp_path, [reg(1, 0), reg(2, 1)])
    ls.main([str(arquivo)])
    assert "Limpeza da base do sensor" in capsys.readouterr().out
    monkeypatch.setattr(ls, "SAIDA", tmp_path / "limpeza.md")
    ls.main([str(arquivo), "--gerar"])
    assert (tmp_path / "limpeza.md").read_text(encoding="utf-8").startswith("# Limpeza")
