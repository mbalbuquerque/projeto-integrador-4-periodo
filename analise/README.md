# Análise de dados climáticos — rota Petrolina → Suape

Scripts de coleta, limpeza e análise exploratória dos dados horários das estações
automáticas do INMET ao longo da rota do transporte refrigerado, com um modelo
preliminar de risco térmico.

Resultado atual: [relatorio.md](relatorio.md).

## Como rodar

```bash
cd analise
pip install -r requirements.txt
python baixar_inmet.py 2020 2021 2022 2023 2024 2025   # ~600 MB de download, salva só a rota
python limpar.py                                        # gera dados/inmet_rota_horario.csv
python explorar.py                                      # gera figuras/ e relatorio.md
```

A pasta `dados/` não vai para o Git: os scripts baixam e regeneram tudo.

## Fonte

INMET — Banco de dados meteorológicos, dados históricos anuais das estações automáticas
(portal.inmet.gov.br/dadoshistoricos). Estações usadas: A307 Petrolina, A329 Cabrobó,
A370 Salgueiro, A350 Serra Talhada, A309 Arcoverde, A341 Caruaru e A301 Recife.

## Arquivos

| arquivo | função |
|---|---|
| `baixar_inmet.py` | baixa o pacote anual do INMET e guarda só as estações da rota |
| `limpar.py` | padroniza as colunas, converte para o horário de Brasília e descarta valores ausentes ou impossíveis |
| `explorar.py` | calcula os indicadores, gera as figuras, treina e avalia o modelo preliminar, escreve o relatório |
