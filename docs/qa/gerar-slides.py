# Gera apresentacao-metricas.pptx (pitch de métricas de qualidade do PI ColdTrack).
# Dados coletados em 10/11/2026; fontes e comandos em dados-coleta.md.
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

PRETO = RGBColor(0x1A, 0x1A, 0x1A)
CINZA = RGBColor(0x55, 0x55, 0x55)
CINZA_CLARO = RGBColor(0xF0, 0xF0, 0xF0)
CINZA_MEDIO = RGBColor(0xBF, 0xBF, 0xBF)
BRANCO = RGBColor(0xFF, 0xFF, 0xFF)
FONTE = "Calibri"
TITULO_FONTE = "Cambria"
RODAPE = "ColdTrack  |  Qualidade de Software, Projeto Integrador  |  Coleta em 10/11/2026"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BRANCO_LAYOUT = prs.slide_layouts[6]


def texto(slide, x, y, w, h, linhas, tam=16, cor=PRETO, negrito=False, fonte=FONTE,
          alinhar=PP_ALIGN.LEFT, ancora=MSO_ANCHOR.TOP, espaco=6, nome=None):
    """linhas: lista de str ou de (str, dict de opções) ou de listas de runs."""
    caixa = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if nome:
        caixa.name = nome
    tf = caixa.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = ancora
    tf.margin_left = tf.margin_right = Inches(0)
    tf.margin_top = tf.margin_bottom = Inches(0)
    for i, linha in enumerate(linhas):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = alinhar
        p.space_after = Pt(espaco)
        runs = linha if isinstance(linha, list) else [linha]
        for run in runs:
            if isinstance(run, tuple):
                t, op = run
            else:
                t, op = run, {}
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = op.get("fonte", fonte)
            f.size = Pt(op.get("tam", tam))
            f.bold = op.get("negrito", negrito)
            f.italic = op.get("italico", False)
            f.color.rgb = op.get("cor", cor)
    return caixa


def base(titulo, notas):
    s = prs.slides.add_slide(BRANCO_LAYOUT)
    texto(s, 0.7, 0.45, 11.9, 0.8, [titulo], tam=34, negrito=True, fonte=TITULO_FONTE,
          nome="Titulo")
    texto(s, 0.7, 6.95, 11.9, 0.3, [RODAPE], tam=11, cor=CINZA, nome="Rodape")
    num = len(prs.slides)
    texto(s, 12.1, 6.95, 0.5, 0.3, [str(num)], tam=11, cor=CINZA, alinhar=PP_ALIGN.RIGHT)
    s.notes_slide.notes_text_frame.text = notas
    return s


def caixa_fundo(slide, x, y, w, h, cor=CINZA_CLARO):
    r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    r.fill.solid()
    r.fill.fore_color.rgb = cor
    r.line.fill.background()
    r.shadow.inherit = False
    return r


def tabela(slide, x, y, w, linhas, larguras, tam=14, alt=0.4, negrito_ult=False):
    n_l, n_c = len(linhas), len(linhas[0])
    g = slide.shapes.add_table(n_l, n_c, Inches(x), Inches(y), Inches(w), Inches(alt * n_l))
    t = g.table
    tbl_pr = g._element.graphic.graphicData.tbl.tblPr
    tbl_pr.set("bandRow", "0")
    tbl_pr.set("firstRow", "0")
    for j, lw in enumerate(larguras):
        t.columns[j].width = Inches(lw)
    for i, linha in enumerate(linhas):
        t.rows[i].height = Inches(alt)
        for j, val in enumerate(linha):
            c = t.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.08)
            c.margin_top = c.margin_bottom = Inches(0.03)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            c.fill.fore_color.rgb = CINZA_MEDIO if i == 0 else BRANCO
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == 0 or not val[:1].isdigit() else PP_ALIGN.RIGHT
            r = p.add_run()
            r.text = val
            r.font.name = FONTE
            r.font.size = Pt(tam)
            r.font.color.rgb = PRETO
            r.font.bold = i == 0 or (negrito_ult and i == n_l - 1)
    # bordas finas pretas
    from pptx.oxml.ns import qn
    from lxml import etree
    for i in range(n_l):
        for j in range(n_c):
            tc_pr = t.cell(i, j)._tc.get_or_add_tcPr()
            for lado in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
                ln = etree.SubElement(tc_pr, qn(lado), w="9525")
                sf = etree.SubElement(ln, qn("a:solidFill"))
                etree.SubElement(sf, qn("a:srgbClr"), val="1A1A1A")
    return g


def stat(slide, x, y, w, numero, rotulo, detalhe):
    caixa_fundo(slide, x, y, w, 2.35)
    texto(slide, x + 0.3, y + 0.2, w - 0.6, 0.9, [numero], tam=44, negrito=True,
          fonte=TITULO_FONTE)
    texto(slide, x + 0.3, y + 1.1, w - 0.6, 0.4, [rotulo], tam=17, negrito=True)
    texto(slide, x + 0.3, y + 1.5, w - 0.6, 0.8, [detalhe], tam=14, cor=CINZA)


# ---------------------------------------------------------------- slide 1
s = base(
    "ColdTrack: visão geral e escopo medido",
    "0 a 2 min. Problema: carga de fruta do Vale do São Francisco perde qualidade quando a "
    "temperatura do baú sai da faixa, e sem registro contínuo a transportadora só descobre na "
    "chegada. O ColdTrack mede no baú, envia para a nuvem e mostra no painel. Tamanho: 12.848 "
    "linhas de código de produção, contando só linhas não vazias e sem comentário, ferramenta "
    "cloc, só arquivos versionados. Ficaram fora JSON gerado (OpenAPI, base do chat), lockfiles, "
    "configuração, documentação e o certificado embutido no firmware. Testes contados à parte: "
    "6.225 linhas.",
)
texto(s, 0.7, 1.55, 5.6, 4.9, [
    [("Problema. ", {"negrito": True}),
     ("Fruta em caminhão refrigerado perde qualidade fora da faixa de temperatura; "
      "sem registro contínuo, o problema só aparece na chegada.", {})],
    [("Solução. ", {"negrito": True}),
     ("Sensor ESP32-C3 no baú envia leituras por HTTPS; a API classifica e grava; "
      "o painel web mostra situação, alertas e relatórios por empresa.", {})],
    [("Stack. ", {"negrito": True}),
     ("Firmware C++ (Arduino), API Python 3.11 em Azure Functions, Cosmos DB, "
      "painel React 18 + Vite, Azure OpenAI no chat. CI no GitHub Actions.", {})],
    [("Período analisado. ", {"negrito": True}),
     ("16/09/2026 (primeiro commit) a 10/11/2026 (data da coleta), dois repositórios.", {})],
], tam=16, espaco=14)
tabela(s, 6.8, 1.55, 5.8, [
    ["Módulo (código de produção)", "LOC"],
    ["API (Python, 7 arquivos)", "1.472"],
    ["Scripts da API e análise climática", "530"],
    ["Firmware (C++)", "1.111"],
    ["Painel: telas e lógica (JSX/JS)", "6.140"],
    ["Painel: estilos (CSS) e entrada", "3.595"],
    ["Total", "12.848 = 12,8 KLOC"],
], [3.8, 2.0], tam=15, alt=0.45, negrito_ult=True)
texto(s, 6.8, 4.95, 5.8, 1.3, [
    "Critério: linhas não vazias e sem comentário (cloc), só arquivos versionados. "
    "Fora: JSON gerado, lockfile, configuração, docs e certificado. "
    "Código de teste contado à parte: 6.225 linhas.",
], tam=13, cor=CINZA)

# ---------------------------------------------------------------- slide 2
s = base(
    "Métricas de produto: defeitos e cobertura",
    "2 a 5 min, primeira parte. Defeito = commit do tipo fix que corrige algo já entregue. "
    "20 commits fix, sendo 2 do mesmo defeito (RSSI inválido corrigido na API e no firmware), "
    "logo 19 defeitos. 19 dividido por 12,848 KLOC dá 1,48 defeito por KLOC. Por repositório: "
    "back 9 em 3,1 KLOC (2,89), front 10 em 9,7 KLOC (1,03). A severidade é classificação nossa "
    "na coleta. Dos 4 de severidade alta, 3 são de segurança, achados na auditoria interna, e 1 "
    "é do firmware lendo a faixa errada. Nenhum chegou a cliente, porque o produto ainda não tem cliente. Limitação: o grupo não registrava defeito em issue, então defeito "
    "sem commit fix não entra, e o ambiente em que cada um foi achado não foi registrado. "
    "Cobertura: pytest-cov e vitest com v8. A API tem 99,7% de linhas e de ramos, com mínimo de "
    "98% travado no CI. O painel tem 19,3% de linhas no teste unitário porque as telas e "
    "componentes são testados por e2e com Playwright (224 execuções simuladas e 57 contra "
    "produção), que essa medida não captura. Somando tudo que foi medido: 2.808 de 9.398 linhas, "
    "29,9%. O firmware tem testes em C++, mas sobre uma cópia das funções, então não entra.",
)
stat(s, 0.7, 1.55, 3.6, "1,48", "defeito por KLOC",
     "19 defeitos ÷ 12,848 KLOC. Back 2,89; painel 1,03.")
tabela(s, 0.7, 4.15, 3.6, [
    ["Severidade", "Qtd."],
    ["Alta (3 segurança)", "4"],
    ["Média", "7"],
    ["Baixa (texto, layout)", "8"],
], [2.6, 1.0], tam=14, alt=0.4)
texto(s, 0.7, 5.85, 3.6, 0.9, [
    "Defeito = commit fix que corrige algo já entregue. Sem issue de bug no período.",
], tam=13, cor=CINZA)

dados = CategoryChartData()
dados.categories = ["API (Python)", "Painel: lógica (src/lib)", "Análise climática",
                    "Painel: total unitário", "Firmware (C++)"]
dados.add_series("Cobertura de linhas (%)", (99.7, 97.5, 52.7, 19.3, 0))
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(4.8), Inches(1.45), Inches(7.8),
                        Inches(4.3), dados)
ch = gf.chart
ch.has_legend = False
ch.has_title = True
ch.chart_title.text_frame.text = "Cobertura de linhas por módulo (%)"
tp = ch.chart_title.text_frame.paragraphs[0].runs[0].font
tp.size, tp.bold, tp.name, tp.color.rgb = Pt(16), True, FONTE, PRETO
plot = ch.plots[0]
plot.gap_width = 60
plot.has_data_labels = True
dl = plot.data_labels
dl.number_format = '0.0"%"'
dl.number_format_is_linked = False
dl.position = XL_LABEL_POSITION.OUTSIDE_END
dl.font.size, dl.font.name, dl.font.color.rgb = Pt(14), FONTE, PRETO
ser = plot.series[0]
ser.format.fill.solid()
ser.format.fill.fore_color.rgb = CINZA
pt = ser.points[4]
pt.data_label.has_text_frame = True
pt.data_label.text_frame.text = "não medido"
pt.data_label.position = XL_LABEL_POSITION.INSIDE_BASE
pt.data_label.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
pt.data_label.text_frame.paragraphs[0].runs[0].font.color.rgb = PRETO
cat = ch.category_axis
cat.reverse_order = True
cat.tick_labels.font.size, cat.tick_labels.font.name = Pt(14), FONTE
cat.tick_labels.font.color.rgb = PRETO
cat.format.line.color.rgb = CINZA_MEDIO
val = ch.value_axis
val.maximum_scale, val.minimum_scale = 115, 0
val.visible = False
val.has_major_gridlines = False
texto(s, 4.8, 5.85, 7.8, 0.9, [
    "Total medido: 2.808 de 9.398 linhas = 29,9%. As telas do painel são cobertas por "
    "testes e2e (Playwright), que essa medida não captura. API com mínimo de 98% no CI.",
], tam=13, cor=CINZA)

# ---------------------------------------------------------------- slide 3
s = base(
    "Métricas de processo: retrabalho e produtividade",
    "2 a 5 min, segunda parte. O grupo não apontava horas, então as horas são estimadas pelo "
    "histórico do git: commits com menos de 2 h de intervalo formam uma sessão, e cada sessão "
    "vale do primeiro ao último commit mais meia hora. Deu 26,3 h. Isso é um piso: não conta "
    "estudo, reunião, montagem da placa nem trabalho sem commit. Retrabalho: tempo de corrigir "
    "o que já tinha sido entregue, ou seja, a fatia de commits fix, 20 de 181, 11,0%, que vira "
    "2,9 h. Não contamos como retrabalho a reescrita do painel para React nem melhoria de "
    "segurança planejada, porque são evolução e não correção. Produtividade, abordagem A: "
    "entrega concluída = pull request mergeado na main com CI verde. Foram 13 PRs em 26,3 h, "
    "0,49 entrega por hora. Os PRs variam muito de tamanho, de 6 a quase 19 mil linhas, então o "
    "número serve para acompanhar o grupo ao longo do tempo, não para comparar com outra equipe "
    "nem para avaliar pessoa. Não usamos LOC por hora porque as horas não são medidas.",
)
stat(s, 0.7, 1.55, 5.75, "11,0%", "taxa de retrabalho",
     "2,9 h ÷ 26,3 h. Horas de retrabalho = fatia de commits fix (20 de 181).")
stat(s, 6.85, 1.55, 5.75, "0,49", "entrega por hora (abordagem A)",
     "13 PRs mergeados na main com CI verde ÷ 26,3 h estimadas.")
texto(s, 0.7, 4.2, 5.75, 2.5, [
    [("Critério. ", {"negrito": True}),
     ("Retrabalho é corrigir o que já foi entregue. Reescrita do painel em React e "
      "melhoria planejada não entram: são evolução.", {})],
    [("Limitação. ", {"negrito": True}),
     ("Horas estimadas pelos commits, não apontadas.", {})],
], tam=15, espaco=10)
texto(s, 6.85, 4.2, 5.75, 2.5, [
    [("Horas. ", {"negrito": True}),
     ("Sessões de commits com intervalo menor que 2 h, mais 0,5 h cada. É piso: "
      "estudo, reunião e montagem da placa ficam fora.", {})],
    [("Limitação. ", {"negrito": True}),
     ("PRs de 6 a 19 mil linhas. Serve para acompanhar o grupo, não para "
      "comparar equipes ou pessoas.", {})],
], tam=15, espaco=10)

# ---------------------------------------------------------------- slide 4
s = base(
    "Impacto no plano de negócio",
    "5 a 8 min. Custo: 2,9 h vezes R$ 40,00 por hora, premissa didática de desenvolvedor "
    "júnior com encargos, dá R$ 116,00. Como as horas são piso, o valor também é piso; a forma "
    "útil de ler é que, com 11% de retrabalho, cada 100 horas de equipe custam R$ 440,00 de "
    "correção. Riscos: a API, que guarda e classifica os dados, é a parte mais testada. O risco "
    "maior está nas telas do painel sem teste unitário, como login e alertas, que dependem só "
    "do e2e. No firmware, os testes conferem uma cópia das funções, então um bug na placa pode "
    "passar pelo CI. E sem registro de defeito não dá para saber quantos chegariam ao cliente. "
    "Não afirmamos que essas métricas provam escalabilidade ou retenção de cliente.",
)
stat(s, 0.7, 1.55, 3.8, "R$ 116", "custo estimado do retrabalho",
     "2,9 h × R$ 40,00/h (premissa didática: dev júnior com encargos).")
texto(s, 0.7, 4.15, 3.8, 2.5, [
    "Horas são piso, então o custo também. Leitura útil: com 11% de retrabalho, "
    "cada 100 h de equipe custam R$ 440,00 em correção.",
], tam=14, cor=CINZA)
riscos = [
    ("Painel sem teste unitário nas telas",
     "Login, Alertas, Cadastro e Configurações só têm e2e. Erro de tela pode chegar ao "
     "usuário entre uma rodada e2e e outra."),
    ("Firmware testado por cópia",
     "Os testes C++ validam funções copiadas para um header que a placa não usa. "
     "Bug na placa pode passar no CI."),
    ("Defeito sem registro",
     "Sem issue de bug, não se sabe onde cada defeito foi achado nem quantos chegariam "
     "ao cliente."),
    ("Ponto forte: núcleo de dados",
     "API com 99,7% de cobertura e mínimo de 98% no CI. 3 dos 4 defeitos de severidade "
     "alta eram de segurança e saíram na auditoria interna."),
]
for i, (tit, desc) in enumerate(riscos):
    col, lin = i % 2, i // 2
    x, y = 4.9 + col * 3.9, 1.55 + lin * 2.6
    caixa_fundo(s, x, y, 3.7, 2.4)
    texto(s, x + 0.25, y + 0.2, 3.2, 2.0, [
        [(tit, {"negrito": True, "tam": 16})],
        [(desc, {"tam": 14})],
    ], espaco=8)

# ---------------------------------------------------------------- slide 5
s = base(
    "Plano de ação para as próximas sprints",
    "8 a 10 min. Três ações em ordem de prioridade. 1: registrar defeito como issue com "
    "etiqueta bug, severidade e ambiente, e apontar horas no quadro; sem isso as métricas 1 e 3 "
    "continuam estimadas. 2: testes de componente nas telas do painel, com mínimo de cobertura "
    "no CI que sobe a cada sprint, como já é feito na API. 3: o firmware passa a usar o header "
    "testado, e assim o teste C++ valida o código que roda na placa. Fecha agradecendo e abrindo "
    "para perguntas.",
)
tabela(s, 0.7, 1.55, 11.9, [
    ["#", "Ação", "Problema que reduz", "Como acompanhar"],
    ["1", "Issue com etiqueta bug, severidade e ambiente; horas apontadas por tarefa no quadro",
     "Defeito e horas sem registro (métricas 1 e 3 estimadas)",
     "Densidade por sprint e retrabalho com horas medidas"],
    ["2", "Testes de componente nas telas do painel e mínimo de cobertura no CI",
     "Painel com 19,3% de linhas no teste unitário",
     "Meta 60% em 2 sprints; CI reprova abaixo do mínimo"],
    ["3", "Firmware passa a incluir o header testado (payload_core.h)",
     "Testes C++ validam uma cópia, não o código da placa",
     "Teste C++ quebra quando a função da placa muda"],
], [0.5, 4.3, 3.6, 3.5], tam=15, alt=1.0)
texto(s, 0.7, 5.75, 11.9, 0.8, [
    "Fontes: documentação do pytest e do pytest-cov, do Vitest (cobertura v8), do Playwright "
    "e GitHub Docs (issues e pull requests). Sem benchmark externo.",
], tam=13, cor=CINZA)

# ---------------------------------------------------------------- anexo
s = base(
    "Anexo: quadro de diagnóstico técnico",
    "Slide de apoio para a arguição; não entra no tempo.",
)
tabela(s, 0.7, 1.35, 11.9, [
    ["Item", "Valor bruto", "Resultado", "Diagnóstico / evidência"],
    ["Projeto", "ColdTrack", "—", "Monitoramento IoT da cadeia fria de frutas"],
    ["Repositórios", "github.com/mbalbuquerque/projeto-integrador-4-periodo e /Front-End-pi",
     "—", "Branch main, coleta em 10/11/2026"],
    ["Período", "16/09/2026 a 10/11/2026", "—", "Do primeiro commit à coleta"],
    ["Tamanho", "12.848 LOC", "12,8 KLOC", "cloc, linhas não vazias sem comentário; sem gerados"],
    ["1. Densidade de defeitos", "19 defeitos (20 commits fix)", "1,48 /KLOC",
     "4 alta, 7 média, 8 baixa; ambiente não registrado"],
    ["2. Cobertura", "2.808 / 9.398 linhas", "29,9%",
     "Linhas; API 99,7%, painel 19,3% (telas no e2e)"],
    ["3. Retrabalho", "2,9 h / 26,3 h", "11,0%", "Fatia de commits fix; horas estimadas"],
    ["4. Produtividade", "13 PRs / 26,3 h", "0,49 entrega/h", "Abordagem A; PRs de tamanhos díspares"],
    ["Custo do retrabalho", "2,9 h × R$ 40,00", "R$ 116,00", "Custo-hora simulado; piso"],
], [2.3, 4.0, 1.7, 3.9], tam=12, alt=0.5)

prs.save("apresentacao-metricas.pptx")
print("ok apresentacao-metricas.pptx")
