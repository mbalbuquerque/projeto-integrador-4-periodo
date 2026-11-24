# Calibração do sensor (#128)

**Situação: não realizada. Lacuna justificada.** Nenhuma medição contra referência foi feita,
e este documento não afirma o contrário.

## Por que não foi feita

A equipe não teve acesso a um termômetro de referência antes de 30/11. Sem referência, qualquer
"calibração" seria um número sem base.

## O que se sabe do sensor

- Precisão declarada no datasheet do DHT11: **±2 °C** na temperatura (e ±5 % UR na umidade).
  É a tolerância que vale para as leituras enquanto não houver medição própria.
- Desde o firmware **2026.11.23.1**, cada leitura guarda também o valor bruto
  (`temperaturaBruta` e `umidadeBruta`). Uma correção pode ser aplicada depois, sem perder nem
  reescrever o histórico.

## Como fazer (próximo passo)

1. Colocar a placa e um termo-higrômetro de referência lado a lado, em ambiente estável, e
   esperar 15 min.
2. Medir em **3 pontos** de temperatura (por exemplo ~20, ~30 e ~35 °C), com 10 leituras da
   placa e 10 da referência por ponto.
3. Registrar a tabela **referência × sensor** e o **erro médio** (placa − referência).
4. Decidir: aplicar a correção (offset, ou ganho e offset) sobre o valor bruto, ou justificar
   por que não é necessária (erro dentro de ±2 °C e estável).

Tabela de registro e detalhes: [`hardware/calibracao.md`](hardware/calibracao.md). Plano de
ação: [`../PLANO_ACAO.md`](../PLANO_ACAO.md).
