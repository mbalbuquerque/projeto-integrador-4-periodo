"""F6 (ThingSpeak indisponível): a API em nuvem não depende do ThingSpeak.

O ThingSpeak é só o canal de telemetria da placa (MQTT). Se ele sair do ar ou a chave for
inválida, a placa continua enviando por HTTPS à API e o painel continua lendo da API. Este teste
trava a parte do back-end dessa garantia: nenhum módulo da Function App fala com o ThingSpeak,
então nenhuma rota pode falhar por causa dele. A parte do painel está em `RESILIENCIA.md` (F6).
"""
from pathlib import Path

AQUI = Path(__file__).parent


def _modulos_de_producao():
    return [p for p in AQUI.glob("*.py")
            if not p.name.startswith("test_") and p.name != "conftest.py"]


def test_ha_modulos_de_producao_para_verificar():
    assert len(_modulos_de_producao()) >= 5


def test_nenhum_modulo_da_api_referencia_thingspeak():
    achados = [p.name for p in _modulos_de_producao()
               if "thingspeak" in p.read_text(encoding="utf-8").lower()]
    assert achados == []


def test_variaveis_do_thingspeak_nao_sao_exigidas_pela_api():
    exemplo = (AQUI / "local.settings.example.json").read_text(encoding="utf-8").lower()
    assert "thingspeak" not in exemplo
    assert "mqtt" not in exemplo
