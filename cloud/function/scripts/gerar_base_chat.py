"""Gera a base de conhecimento do chat do site (cloud/function/base_chat.json).

Lê a documentação deste repositório e do repositório do painel (Front-End-pi),
mais as respostas do FAQ do site, corta em trechos, gera os embeddings no
Azure OpenAI e grava a lista {"id", "fonte", "texto", "vetor"}.

Uso (a partir de cloud/function), com Python 3.11 e o requirements.txt instalado:
  export AOAI_ENDPOINT=https://<recurso>.openai.azure.com/
  export AOAI_DEPLOY_EMBED=text-embedding-3-small
  # Autenticação: AOAI_KEY no ambiente, ou `az login` com o papel
  # "Cognitive Services OpenAI User" no recurso.
  python scripts/gerar_base_chat.py --front ../../../Front-End-pi
  python scripts/gerar_base_chat.py --seco      # só mostra os trechos, sem chamar a IA

Depois de gerar, rodar os testes e commitar o base_chat.json.
Segredos: só entram os arquivos da lista abaixo; .specs, local.settings*,
secrets.h e arquivos .txt nunca são lidos, e trecho com cara de credencial é
descartado.
"""

import argparse
import json
import os
import re
import sys
import time

PASTA_API = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(os.path.dirname(PASTA_API))
sys.path.insert(0, PASTA_API)

import chat  # noqa: E402

# Fontes deste repositório (back-end, firmware, infraestrutura).
DOCS_BACK = [
    "README.md",
    "docs/memorial-descritivo.md",
    "docs/stack-tecnica.md",
    "docs/api.md",
    "docs/implantacao.md",
    "cloud/function/README.md",
    "analise/README.md",
]
# Fontes do repositório do painel.
DOCS_FRONT = ["README.md", "docs/guia-de-uso.md", "docs/ARQUITETURA.md", "CONTRIBUTING.md"]
FAQ_FRONT = "src/components/ChatWidget/respostas.js"

PROIBIDOS = re.compile(r"(^|/)(\.specs|local\.settings[^/]*|secrets\.h)(/|$)|\.txt$")
CREDENCIAL = re.compile(
    r"AccountKey=|SharedAccessKey=|-----BEGIN [A-Z ]*PRIVATE KEY|"
    r"\bsk-[A-Za-z0-9]{20,}|\beyJ[A-Za-z0-9_-]{20,}\.|"
    r"(senha|password|secret|chave)\s*[:=]\s*['\"][^'\"<]{8,}['\"]",
    re.IGNORECASE)

TAMANHO = 800
SOBREPOSICAO = 150
MINIMO = 60
LOTE = 32
TENTATIVAS = 6


def _limpar_markdown(texto):
    texto = re.sub(r"```.*?```", "", texto, flags=re.DOTALL)        # blocos de código
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.DOTALL)
    texto = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", texto)          # imagens
    texto = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", texto)           # links
    texto = re.sub(r"^\s*\|?[-:| ]+\|?\s*$", "", texto, flags=re.MULTILINE)  # separador
    texto = re.sub(r"[*_`]{1,3}", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _janelas(texto):
    """Corta texto longo em pedaços de ~TAMANHO com sobreposição, preferindo parágrafos."""
    if len(texto) <= TAMANHO:
        return [texto]
    pedacos, inicio = [], 0
    while inicio < len(texto):
        fim = min(len(texto), inicio + TAMANHO)
        if fim < len(texto):
            quebra = max(texto.rfind("\n", inicio + TAMANHO // 2, fim),
                         texto.rfind(". ", inicio + TAMANHO // 2, fim))
            if quebra > inicio:
                fim = quebra + 1
        pedacos.append(texto[inicio:fim].strip())
        if fim >= len(texto):
            break
        # Sobreposição começando numa palavra inteira (nunca no meio de um link).
        recuo = max(fim - SOBREPOSICAO, inicio + 1)
        espaco = re.search(r"\s", texto[recuo:fim])
        inicio = recuo + espaco.end() if espaco else fim
    return pedacos


def trechos_markdown(conteudo, fonte):
    """Divide pelos títulos; cada trecho leva o caminho de títulos como contexto."""
    secoes, titulos, linhas = [], [], []

    def fechar():
        corpo = _limpar_markdown("\n".join(linhas))
        if corpo:
            secoes.append((" > ".join(t for t in titulos if t), corpo))

    em_codigo = False
    for linha in conteudo.splitlines():
        if linha.lstrip().startswith("```"):
            em_codigo = not em_codigo
        titulo = None if em_codigo else re.match(r"^(#{1,4})\s+(.*)", linha)
        if titulo:
            fechar()
            nivel = len(titulo.group(1))
            titulos = titulos[:nivel - 1] + [""] * max(0, nivel - 1 - len(titulos))
            titulos.append(_limpar_markdown(titulo.group(2)))
            linhas = []
        else:
            linhas.append(linha)
    fechar()

    saida = []
    for caminho, corpo in secoes:
        for pedaco in _janelas(corpo):
            texto = f"{caminho}: {pedaco}" if caminho else pedaco
            if len(pedaco) >= MINIMO:
                saida.append({"fonte": fonte, "texto": texto})
    return saida


def _literais(trecho_js):
    partes = re.findall(r'"((?:[^"\\]|\\.)*)"', trecho_js)
    return "".join(json.loads(f'"{p}"') for p in partes)


def trechos_faq(conteudo):
    """Pergunta-chave (termos) e resposta de cada item do array CONHECIMENTO."""
    inicio = conteudo.find("CONHECIMENTO")
    if inicio < 0:
        return []
    saida = []
    padrao = re.compile(
        r"termos:\s*\[(?P<termos>[^\]]*)\]\s*,\s*resposta:\s*"
        r"(?P<resposta>(?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)")
    for m in padrao.finditer(conteudo, inicio):
        termos = ", ".join(re.findall(r'"([^"]*)"', m.group("termos")))
        resposta = _literais(m.group("resposta")).strip()
        if resposta:
            saida.append({"fonte": "FAQ do site", "texto": f"Sobre {termos}: {resposta}"})
    return saida


def _ler(raiz, caminho):
    if PROIBIDOS.search(caminho.replace("\\", "/")):
        raise ValueError(f"fonte proibida: {caminho}")
    completo = os.path.join(raiz, caminho)
    if not os.path.isfile(completo):
        print(f"  (não encontrado, pulando) {completo}")
        return None
    with open(completo, encoding="utf-8") as f:
        return f.read()


def coletar(front):
    trechos = []
    for caminho in DOCS_BACK:
        conteudo = _ler(RAIZ, caminho)
        if conteudo:
            trechos += trechos_markdown(conteudo, caminho)
    if front:
        for caminho in DOCS_FRONT:
            conteudo = _ler(front, caminho)
            if conteudo:
                trechos += trechos_markdown(conteudo, f"painel/{caminho}")
        conteudo = _ler(front, FAQ_FRONT)
        if conteudo:
            trechos += trechos_faq(conteudo)

    seguros = [t for t in trechos if not CREDENCIAL.search(t["texto"])]
    if len(seguros) < len(trechos):
        print(f"  {len(trechos) - len(seguros)} trecho(s) descartado(s) por parecer credencial")
    contagem = {}
    for t in seguros:
        n = contagem.get(t["fonte"], 0)
        contagem[t["fonte"]] = n + 1
        t["id"] = f"{t['fonte']}#{n}"
    return seguros


def _vetorizar_com_espera(textos, cli):
    """O deploy tem cota baixa (tokens por minuto): no 429, espera o tempo pedido e repete."""
    from openai import RateLimitError

    for tentativa in range(TENTATIVAS):
        try:
            return chat.vetorizar(textos, cli)
        except RateLimitError as e:
            if tentativa == TENTATIVAS - 1:
                raise
            pedido = re.search(r"retry after (\d+) second", str(e))
            espera = int(pedido.group(1)) + 1 if pedido else 30
            print(f"  cota por minuto atingida; esperando {espera} s")
            time.sleep(espera)


def main():
    # Terminal do Windows (cp1252) não imprime setas e emojis da documentação.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    padrao_front = os.getenv("FRONT_REPO") or os.path.join(os.path.dirname(RAIZ), "Front-End-pi")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--front", default=padrao_front,
                   help="pasta do repositório Front-End-pi (padrão: ao lado deste repositório "
                        "ou a variável FRONT_REPO)")
    p.add_argument("--saida", default=chat.ARQUIVO_BASE)
    p.add_argument("--seco", action="store_true", help="não chama a IA nem grava o arquivo")
    args = p.parse_args()

    front = args.front if os.path.isdir(args.front) else None
    if front is None:
        print(f"Aviso: repositório do painel não encontrado em {args.front}; "
              "só a documentação deste repositório entra na base.")
    trechos = coletar(front)
    print(f"{len(trechos)} trechos de {len({t['fonte'] for t in trechos})} fontes")
    if args.seco:
        for t in trechos:
            print(f"- {t['id']} ({len(t['texto'])}): {t['texto'][:100]!r}")
        return
    if not chat.configurado():
        sys.exit("Defina AOAI_ENDPOINT (e AOAI_KEY ou faça az login) antes de gerar a base.")

    cli = chat.cliente()
    for i in range(0, len(trechos), LOTE):
        lote = trechos[i:i + LOTE]
        for t, vetor in zip(lote, _vetorizar_com_espera([t["texto"] for t in lote], cli)):
            t["vetor"] = [round(x, 6) for x in vetor]
        print(f"  embeddings {min(i + LOTE, len(trechos))}/{len(trechos)}")

    base = [{"id": t["id"], "fonte": t["fonte"], "texto": t["texto"], "vetor": t["vetor"]}
            for t in trechos]
    with open(args.saida, "w", encoding="utf-8", newline="\n") as f:
        json.dump(base, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"Gravado {args.saida} ({os.path.getsize(args.saida) // 1024} KB)")


if __name__ == "__main__":
    main()
