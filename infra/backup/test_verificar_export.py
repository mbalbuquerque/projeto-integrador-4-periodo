"""Testes do verificar_export.py: export sintético íntegro, com divergência e com id repetido."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verificar_export as ve  # noqa: E402


def exportar(pasta, leituras, contagem=None):
    pasta.mkdir(exist_ok=True)
    (pasta / "leituras.jsonl").write_text(
        "".join(json.dumps(d) + "\n" for d in leituras), encoding="utf-8")
    (pasta / "manifesto.json").write_text(json.dumps({
        "versao": 1, "banco": "coldtrack", "data": "2026-11-23T00:00:00+00:00",
        "containers": {"leituras": {"arquivo": "leituras.jsonl",
                                    "contagem": len(leituras) if contagem is None else contagem,
                                    "chaveParticao": "/deviceId", "ttl": None}}}),
        encoding="utf-8")
    return str(pasta)


L = [{"id": "d1~1", "deviceId": "d1", "temperatura": 30.1},
     {"id": "d1~2", "deviceId": "d1", "temperatura": 30.2},
     {"id": "d2~1", "deviceId": "d2", "temperatura": 29.9}]


def test_export_integro_restaura_e_e_idempotente(tmp_path):
    linhas, ok = ve.verificar(exportar(tmp_path / "e", L))
    assert ok
    assert sum("restauração em memória" in x and "[ok]" in x for x in linhas) == 2


def test_contagem_do_manifesto_diferente_do_arquivo(tmp_path):
    _, ok = ve.verificar(exportar(tmp_path / "e", L, contagem=5))
    assert not ok


def test_id_repetido_na_mesma_particao_e_detectado(tmp_path):
    _, ok = ve.verificar(exportar(tmp_path / "e", L + [dict(L[0])]))
    assert not ok


def test_mesmo_id_em_particoes_diferentes_e_permitido(tmp_path):
    docs = [{"id": "x", "deviceId": "a"}, {"id": "x", "deviceId": "b"}]
    _, ok = ve.verificar(exportar(tmp_path / "e", docs))
    assert ok


def test_documento_sem_chave_de_particao(tmp_path):
    _, ok = ve.verificar(exportar(tmp_path / "e", [{"id": "1"}]))
    assert not ok


def test_main_sai_com_codigo(tmp_path, capsys):
    with pytest.raises(SystemExit) as saida:
        ve.main([exportar(tmp_path / "e", L)])
    assert saida.value.code == 0 and "[ok]" in capsys.readouterr().out
    with pytest.raises(SystemExit) as saida:
        ve.main([])
    assert saida.value.code != 0
