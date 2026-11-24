#!/usr/bin/env bash
# Antes e depois da protecao contra IDOR (#114).
#
# Roda o MESMO teste (cloud/function/test_idor.py) em dois pontos da historia:
#   antes  = commit d44b301, de antes da verificacao de dono (qualquer usuario lia
#            qualquer sensor trocando o deviceId);
#   depois = o commit atual (HEAD), com exigir_dono em todas as rotas com ID.
# No "antes" os testes de bloqueio FALHAM (prova de que o ataque funcionava); no
# "depois" passam.
#
# Uso, da raiz do repositorio, com as dependencias da API instaladas
# (pip install -r cloud/function/requirements.txt):
#   MISSAO_CODIGO=<codigo> bash seguranca/testes/idor_antes_depois.sh
# Sem MISSAO_CODIGO, os arquivos saem como SEM-CODIGO-idor-antes.txt e -depois.txt.
#
# Ajustes para o teste rodar no commit antigo (anotados no README da pasta seguranca):
# - o commit antigo nao tem test_idor.py nem o Cosmos falso (test_falsos.py): os dois
#   sao copiados do commit atual para uma copia temporaria do d44b301 (git worktree);
# - no "antes" roda so a classe TestAtaqueEntreEmpresas, que usa apenas o que existe
#   nos dois commits. Rota que nao existia em d44b301 (dispositivos, predict/sensor)
#   aparece como "skipped" la.

set -uo pipefail

MISSAO_CODIGO="${MISSAO_CODIGO:-SEM-CODIGO}"
ANTES_COMMIT="d44b301"
TESTES_ANTES="test_idor.TestAtaqueEntreEmpresas"
TESTES_DEPOIS="test_idor"

RAIZ="$(git rev-parse --show-toplevel)"
EVIDENCIAS="$RAIZ/seguranca/evidencias"
SAIDA_ANTES="$EVIDENCIAS/${MISSAO_CODIGO}-idor-antes.txt"
SAIDA_DEPOIS="$EVIDENCIAS/${MISSAO_CODIGO}-idor-depois.txt"

TMP="$(mktemp -d)"
ANTES="$TMP/antes"
limpar() {
    git -C "$RAIZ" worktree remove --force "$ANTES" >/dev/null 2>&1
    rm -rf "$TMP"
}
trap limpar EXIT

# Tira caminhos da maquina de quem rodou (pasta temporaria, usuario, site-packages).
sem_caminho_local() {
    sed -E \
        -e 's#File "[^"]*[/\\](cloud[/\\]function[/\\])#File "\1#' \
        -e 's#File "[^"]*site-packages[/\\]#File "<site-packages>/#' \
        -e 's#File "[^"]*[/\\][Ll]ib[/\\]#File "<python>/lib/#'
}

rodar() {  # rodar <pasta cloud/function> <testes> <titulo> <commit> <arquivo>
    local pasta="$1" testes="$2" titulo="$3" commit="$4" arquivo="$5" codigo
    {
        echo "# $titulo"
        echo "# codigo de missao: $MISSAO_CODIGO"
        echo "# commit: $commit"
        echo "# comando: cd cloud/function && python -m unittest $testes -v"
        echo "# gerado em: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
        echo
    } > "$arquivo"
    (cd "$pasta" && PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python -m unittest "$testes" -v 2>&1) | sem_caminho_local >> "$arquivo"
    codigo="${PIPESTATUS[0]}"
    echo >> "$arquivo"
    echo "# saida do unittest: $codigo (0 = todos passaram)" >> "$arquivo"
    return "$codigo"
}

echo "Criando copia temporaria do commit $ANTES_COMMIT..."
git -C "$RAIZ" worktree add --detach "$ANTES" "$ANTES_COMMIT" >/dev/null 2>&1 || {
    echo "ERRO: nao consegui criar o worktree de $ANTES_COMMIT" >&2
    exit 2
}
cp "$RAIZ/cloud/function/test_idor.py" "$RAIZ/cloud/function/test_falsos.py" \
    "$ANTES/cloud/function/"

ANTES_SHA="$(git -C "$ANTES" rev-parse --short HEAD)"
DEPOIS_SHA="$(git -C "$RAIZ" rev-parse --short HEAD)"
if [ -n "$(git -C "$RAIZ" status --porcelain -- cloud/function)" ]; then
    DEPOIS_SHA="$DEPOIS_SHA (com alteracoes nao commitadas em cloud/function)"
fi

rodar "$ANTES/cloud/function" "$TESTES_ANTES" \
    "IDOR ANTES: commit $ANTES_COMMIT, sem verificacao de dono (o ataque deve funcionar)" \
    "$ANTES_SHA" "$SAIDA_ANTES"
r_antes=$?
rodar "$RAIZ/cloud/function" "$TESTES_DEPOIS" \
    "IDOR DEPOIS: exigir_dono em todas as rotas com ID (o ataque deve ser bloqueado)" \
    "$DEPOIS_SHA" "$SAIDA_DEPOIS"
r_depois=$?

echo "antes  ($ANTES_COMMIT): saida $r_antes -> ${SAIDA_ANTES#"$RAIZ"/}"
echo "depois ($DEPOIS_SHA): saida $r_depois -> ${SAIDA_DEPOIS#"$RAIZ"/}"
if [ "$r_antes" -ne 0 ] && [ "$r_depois" -eq 0 ]; then
    echo "OK: no antes o ataque funcionou (testes de bloqueio falharam); no depois foi bloqueado."
    exit 0
fi
echo "ATENCAO: resultado diferente do esperado (antes deve falhar, depois deve passar)." >&2
exit 1
