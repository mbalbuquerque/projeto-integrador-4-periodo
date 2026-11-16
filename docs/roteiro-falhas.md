# Roteiro dos testes de falha F1 e F3

Os dois testes provocados pela banca na prévia. Registrar o resultado medido em
[`RESILIENCIA.md`](../RESILIENCIA.md). Contingência: roteador ou hotspot próprio.

## Preparação (antes)

1. Placa ligada, conectada e enviando; dashboard aberto no sensor.
2. Monitor Serial aberto (mostra `FILA:` e o código HTTP de cada envio).
3. Anotar a última leitura recebida no dashboard.

## F1: queda de rede (60 s)

1. Anotar o horário `t0` e desligar o hotspot por 60 s.
2. No Serial, conferir "Wi-Fi desconectado" e as leituras indo para a fila (`FILA:`).
3. Religar o hotspot, anotar o horário de volta da rede e o de `t1`, a primeira leitura reenviada.
4. Critério: reconecta em até 30 s depois da volta da rede e não há lacuna nas leituras do
   período no banco (conferir o histórico do sensor).
5. Registrar: leituras enfileiradas, leituras reenviadas, tempo de reconexão.

## F3: falha de sensor

1. Desconectar o fio de dados do DHT.
2. Esperar dois ciclos de leitura (cerca de 40 s).
3. Critério: a placa não envia valor como válido, o alerta aparece e nenhuma leitura inválida
   fica gravada como válida no banco.
4. Religar o fio e conferir que as leituras voltam sozinhas.
5. Registrar: o que o Serial mostrou, se houve alerta e o que apareceu no painel.

## Se falhar

Anotar a falha sem esconder. Ela entra no `PLANO_ACAO.md`, e o teste é repetido depois da
correção.
