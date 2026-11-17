"""Contrato de telemetria do ColdTrack Edge.

Valida o JSON enviado pelo ESP32 e classifica a leitura. Não depende de Azure,
então pode ser testado localmente com `python -m unittest`.

Payload esperado (POST /api/telemetria):
{
  "deviceId": "coldtrack-01",
  "temperatura": 12.4,
  "umidade": 81.0,
  "rssi": -58,
  "medidoEm": 1790000000,     (opcional: epoch UTC em segundos da medição)
  "seq": 42                   (opcional: número de sequência da leitura no sensor)
}
"""

import bisect
import re
import time

DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{3,40}$")

# Faixas físicas do sensor (DHT22). Fora disso é leitura inconsistente.
TEMP_MIN, TEMP_MAX = -40.0, 80.0
UMID_MIN, UMID_MAX = 0.0, 100.0
RSSI_MIN, RSSI_MAX = -120, 0

# Número de sequência: contador do sensor, gravado na flash (uint32 no ESP32).
SEQ_MIN, SEQ_MAX = 1, 2**32 - 1

# Janela aceita para o horário da medição.
MEDIDO_FUTURO_MAX_S = 5 * 60
MEDIDO_PASSADO_MAX_S = 7 * 24 * 3600


def _numero(valor):
    # bool é subclasse de int em Python; não aceitar true/false como número.
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def id_leitura(device_id, medido_em):
    """Id da leitura no banco. Com o horário da medição, o id é determinístico
    (o mesmo sensor não mede duas vezes no mesmo segundo): um reenvio do sensor
    depois de uma resposta perdida bate no mesmo id em vez de duplicar.
    Sem horário (firmware antigo), None: o chamador usa um uuid."""
    if medido_em is None:
        return None
    return f"{device_id}~{int(medido_em)}"


def mesma_leitura(gravada, nova):
    """True quando `nova` repete os valores de `gravada` (reenvio legítimo).
    False = mesmo sensor e segundo com valores diferentes: não sobrescreve."""
    return (
        round(float(gravada["temperatura"]), 1) == round(float(nova["temperatura"]), 1)
        and round(float(gravada["umidade"]), 1) == round(float(nova["umidade"]), 1)
        and gravada.get("rssi") == nova.get("rssi")
        and gravada.get("seq") == nova.get("seq")
    )


def validar(dados, agora=None):
    """Retorna a lista de erros do payload. Lista vazia = payload válido."""
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"]

    erros = []
    device = dados.get("deviceId")
    if not isinstance(device, str) or not DEVICE_ID.match(device):
        erros.append("deviceId: texto de 3 a 40 caracteres (letras, números, _ ou -)")

    for campo, minimo, maximo in (
        ("temperatura", TEMP_MIN, TEMP_MAX),
        ("umidade", UMID_MIN, UMID_MAX),
        ("rssi", RSSI_MIN, RSSI_MAX),
    ):
        valor = dados.get(campo)
        # RSSI é diagnóstico de rede: o firmware manda null quando o rádio
        # devolve valor impossível (ex.: positivo no simulador). Temperatura e
        # umidade continuam obrigatórias.
        if campo == "rssi" and campo in dados and valor is None:
            continue
        if not _numero(valor):
            erros.append(f"{campo}: obrigatório e numérico")
        elif valor != valor or not minimo <= valor <= maximo:  # valor != valor pega NaN
            erros.append(f"{campo}: fora da faixa [{minimo}, {maximo}]")

    # medidoEm: horário da medição (epoch UTC em segundos), opcional.
    # Leituras guardadas offline no ESP32 chegam depois, então o horário de
    # recebimento não serve para a linha do tempo da carga.
    if "medidoEm" in dados:
        medido = dados["medidoEm"]
        referencia = time.time() if agora is None else agora
        if not _numero(medido) or medido != medido:
            erros.append("medidoEm: epoch em segundos (número)")
        elif medido > referencia + MEDIDO_FUTURO_MAX_S:
            erros.append("medidoEm: no futuro (relógio do dispositivo errado?)")
        elif medido < referencia - MEDIDO_PASSADO_MAX_S:
            erros.append("medidoEm: mais antigo que 7 dias")

    # seq: número de sequência da leitura, opcional (placa sem seq continua aceita).
    # Cresce 1 a cada leitura e sobrevive a reinício: buraco na sequência é
    # leitura perdida entre o sensor e o banco.
    if "seq" in dados:
        seq = dados["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool) or not SEQ_MIN <= seq <= SEQ_MAX:
            erros.append(f"seq: inteiro de {SEQ_MIN} a {SEQ_MAX}")

    extras = set(dados) - {"deviceId", "temperatura", "umidade", "rssi", "medidoEm", "seq"}
    if extras:
        erros.append("campos não previstos: " + ", ".join(sorted(extras)))

    return erros


# Heartbeat (POST /api/heartbeat): sinal de vida da placa quando não há leitura
# válida para enviar. Hoje o único motivo é o sensor em falha.
MOTIVOS_HEARTBEAT = ("sensor_falha",)
FW = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


def validar_heartbeat(dados):
    """Erros do corpo do heartbeat. Lista vazia = válido.

    {"deviceId": "coldtrack-01", "motivo": "sensor_falha", "fw": "2026.11.17.2",
     "rssi": -58 (opcional, null aceito), "seq": 42 (opcional: última leitura enviada)}
    """
    if not isinstance(dados, dict):
        return ["corpo deve ser um objeto JSON"]

    erros = []
    device = dados.get("deviceId")
    if not isinstance(device, str) or not DEVICE_ID.match(device):
        erros.append("deviceId: texto de 3 a 40 caracteres (letras, números, _ ou -)")
    if dados.get("motivo") not in MOTIVOS_HEARTBEAT:
        erros.append("motivo: use " + ", ".join(MOTIVOS_HEARTBEAT))
    fw = dados.get("fw")
    if not isinstance(fw, str) or not FW.match(fw):
        erros.append("fw: texto de 1 a 32 caracteres (letras, números, ., _ ou -)")
    if "rssi" in dados and dados["rssi"] is not None:
        rssi = dados["rssi"]
        if not isinstance(rssi, int) or isinstance(rssi, bool) or not RSSI_MIN <= rssi <= RSSI_MAX:
            erros.append(f"rssi: inteiro de {RSSI_MIN} a {RSSI_MAX} ou null")
    if "seq" in dados:
        seq = dados["seq"]
        if not isinstance(seq, int) or isinstance(seq, bool) or not SEQ_MIN <= seq <= SEQ_MAX:
            erros.append(f"seq: inteiro de {SEQ_MIN} a {SEQ_MAX}")

    extras = set(dados) - {"deviceId", "motivo", "fw", "rssi", "seq"}
    if extras:
        erros.append("campos não previstos: " + ", ".join(sorted(extras)))
    return erros


def lacunas_de_sequencia(leituras):
    """Leituras que faltam entre as recebidas, pelo número de sequência.

    `leituras` em qualquer ordem. Leitura sem `seq` (placa antiga) não entra
    na conta. A falta é calculada pelo número, não pela ordem do horário: a
    placa pode carimbar uma leitura com o relógio adiantado (reinício antes
    do NTP) e ela chega fora de ordem sem que nada tenha se perdido. Número
    presente na resposta nunca é dado como faltando.

    Contador zerado (flash apagada) recomeça a contagem: na ordem do horário,
    uma leitura com número menor que o menor da contagem atual abre uma
    contagem nova, e cada contagem tem as suas faltas.
    Retorna [{"de": n, "ate": m, "faltam": m - n + 1}], da mais antiga para a mais nova.
    """
    com_seq = sorted(
        (item for item in leituras if isinstance(item.get("seq"), int)),
        key=lambda item: (item["medidoEm"], item["seq"]),
    )

    contagens = []
    menor = None
    for item in com_seq:
        if menor is None or item["seq"] < menor:
            contagens.append(set())
            menor = item["seq"]
        contagens[-1].add(item["seq"])

    presentes = sorted(set().union(*contagens))
    lacunas = []
    for numeros in contagens:
        ordenados = sorted(numeros)
        for anterior, atual in zip(ordenados, ordenados[1:]):
            # Entre dois números da contagem, o que falta é o que nenhuma
            # leitura trouxe (nem de outra contagem).
            inicio = anterior + 1
            pos = bisect.bisect_left(presentes, inicio)
            while inicio < atual:
                proximo = presentes[pos] if pos < len(presentes) else atual
                fim = min(proximo, atual) - 1
                if fim >= inicio:
                    lacunas.append({"de": inicio, "ate": fim, "faltam": fim - inicio + 1})
                inicio = proximo + 1
                pos += 1
    return lacunas


STATUS_VALIDOS = ("NORMAL", "ATENCAO", "CRITICO")
HORAS_MAX = 7 * 24


def filtros_de_leitura(params, agora=None):
    """Interpreta os filtros opcionais de GET /leituras.

    horas:  1 a 168 — só leituras medidas nas últimas N horas.
    status: lista separada por vírgula (ex.: ATENCAO,CRITICO).

    Retorna (erros, filtros), com filtros = {"desde": epoch | None, "status": [..] | None}.
    """
    erros = []
    filtros = {"desde": None, "status": None}

    horas = params.get("horas")
    if horas is not None:
        try:
            horas = int(horas)
        except ValueError:
            horas = 0
        if not 1 <= horas <= HORAS_MAX:
            erros.append(f"horas: inteiro de 1 a {HORAS_MAX}")
        else:
            referencia = time.time() if agora is None else agora
            filtros["desde"] = referencia - horas * 3600

    status = params.get("status")
    if status is not None:
        lista = [s.strip().upper() for s in status.split(",") if s.strip()]
        invalidos = [s for s in lista if s not in STATUS_VALIDOS]
        if not lista or invalidos:
            erros.append("status: use " + ", ".join(STATUS_VALIDOS) + " separados por vírgula")
        else:
            filtros["status"] = lista

    return erros, filtros


# Perfis de carga. Faixa normal [min, max]; até `margem` °C fora dela é ATENCAO,
# além disso é CRITICO. min None = sem limite inferior.
# Manga e uva: faixas de referência de pós-colheita, a validar com o produtor.
# O DHT11 não mede abaixo de 0 °C: a uva pede DHT22 ou sonda DS18B20.
PERFIS_CARGA = {
    "demonstrativo": {"nome": "Demonstrativo (protótipo)", "min": None, "max": 15.0, "margem": 5.0},
    "manga": {"nome": "Manga", "min": 10.0, "max": 13.0, "margem": 3.0},
    "uva": {"nome": "Uva de mesa", "min": -1.0, "max": 0.0, "margem": 2.0},
}
PERFIL_PADRAO = "demonstrativo"


def faixa(perfil):
    p = PERFIS_CARGA.get(perfil, PERFIS_CARGA[PERFIL_PADRAO])
    return {"min": p["min"], "max": p["max"], "margem": p["margem"]}


def classificar(temperatura, perfil=PERFIL_PADRAO):
    f = faixa(perfil)
    minimo = f["min"] if f["min"] is not None else float("-inf")
    if minimo <= temperatura <= f["max"]:
        return "NORMAL"
    if minimo - f["margem"] <= temperatura <= f["max"] + f["margem"]:
        return "ATENCAO"
    return "CRITICO"
