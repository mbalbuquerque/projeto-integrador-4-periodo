"""Teste unitário da conversão dos feeds da API ThingSpeak (baixar_thingspeak.py), sem rede."""

import math

from baixar_thingspeak import ORIGEM, para_dataframe


def test_para_dataframe_tipa_ordena_e_remove_duplicata():
    feeds = [
        {"created_at": "2026-10-08T12:00:20Z", "entry_id": 2, "field1": "25.5", "field2": "50.0", "field3": "-50"},
        {"created_at": "2026-10-08T12:00:00Z", "entry_id": 1, "field1": "25.0", "field2": None, "field3": "-51"},
        {"created_at": "2026-10-08T12:00:20Z", "entry_id": 2, "field1": "25.5", "field2": "50.0", "field3": "-50"},
    ]
    df = para_dataframe(feeds)
    assert df["entry_id"].tolist() == [1, 2]
    assert math.isnan(df.loc[0, "umidade"])
    assert df["temperatura"].tolist() == [25.0, 25.5]
    assert set(df["origem"]) == {ORIGEM}
    assert str(df["momento_utc"].dt.tz) == "UTC"
