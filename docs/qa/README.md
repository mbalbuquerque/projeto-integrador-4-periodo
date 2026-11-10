# Qualidade de Software: métricas do ColdTrack

Material da atividade "Aplicação de Métricas de Qualidade no Projeto Integrador". A coleta foi feita em 10/11/2026.

- [`apresentacao-metricas.pptx`](apresentacao-metricas.pptx): pitch de até 10 minutos. Tem cinco slides e um anexo com o quadro de diagnóstico; as falas estão nas notas de cada slide.
- [`metricas-de-qualidade.md`](metricas-de-qualidade.md): os dados brutos, os critérios, a lista de defeitos com a severidade, as limitações e os comandos usados.
- [`gerar-slides.py`](gerar-slides.py): regera o `.pptx`. Precisa do `python-pptx`; rode `python gerar-slides.py` dentro desta pasta.
- [`guia-da-atividade.pdf`](guia-da-atividade.pdf): o enunciado do professor.

Resultados:

| Métrica | Resultado |
|---|---|
| Densidade de defeitos | 1,48 por KLOC (19 defeitos em 12,8 KLOC) |
| Cobertura de linhas | 29,9% no total medido; API com 99,7% |
| Taxa de retrabalho | 11,0% (horas estimadas) |
| Produtividade | 0,49 PR mergeado por hora |
| Custo do retrabalho | R$ 116,00 (custo-hora simulado) |
