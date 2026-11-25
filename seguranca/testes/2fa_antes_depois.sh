#!/usr/bin/env bash
# Antes e depois do 2FA com TOTP (#113), contra a API em producao.
#
# Prova com a MESMA conta, criada so para o teste e apagada no fim:
#   antes  = 2FA desligado: POST /login so com a senha ja devolve o token;
#   ativa  = POST /2fa/iniciar + POST /2fa/ativar com o codigo TOTP do segredo devolvido;
#   depois = POST /login so com a senha devolve um desafio e nenhum token; o desafio
#            nao abre rota protegida (401); POST /login/2fa com codigo errado da 401
#            e com o codigo certo devolve o token.
# A empresa temporaria e apagada com DELETE /empresa mesmo se o teste parar no meio.
#
# Uso, da raiz do repositorio (precisa de curl e de Python com pyotp:
# pip install pyotp==2.9.0, ou pip install -r cloud/function/requirements.txt):
#   MISSAO_CODIGO=<codigo> bash seguranca/testes/2fa_antes_depois.sh
# Sem MISSAO_CODIGO, o log sai como SEM-CODIGO-2fa-antes-depois.log.
# API_URL troca o alvo (padrao: a API de producao).
#
# Cuidado com os limites da API: POST /empresas aceita 5 cadastros por hora por IP.
# Senha, token, desafio, segredo TOTP e codigos nunca vao para a tela nem para o log.

set -uo pipefail

MISSAO_CODIGO="${MISSAO_CODIGO:-SEM-CODIGO}"
API="${API_URL:-https://func-coldtrack-7319.azurewebsites.net/api}"
API="${API%/}"
PY="${PYTHON:-python}"

RAIZ="$(git rev-parse --show-toplevel)"
LOG="$RAIZ/seguranca/evidencias/${MISSAO_CODIGO}-2fa-antes-depois.log"

if ! "$PY" -c "import pyotp" >/dev/null 2>&1; then
    echo "ERRO: falta o pyotp (pip install pyotp==2.9.0)" >&2
    exit 2
fi

TMP="$(mktemp -d)"
STATUS=""
OK=0
FALHAS=0

# Dados da conta temporaria (gerados aqui; so o e-mail mascarado aparece no log).
SUFIXO="$("$PY" -c "import secrets; print(secrets.token_hex(5))")"
EMAIL="teste-2fa-${SUFIXO}@exemplo.com"
SENHA="$("$PY" -c "import secrets; print(secrets.token_urlsafe(24))")"
EMPRESA_NOME="Teste 2FA ${SUFIXO}"
EMAIL_MASCARADO="t***@exemplo.com"

EMPRESA_ID=""
TOKEN_CADASTRO=""
TOKEN_ANTES=""
TOKEN_DEPOIS=""
DESAFIO=""
URI_TOTP=""

log() { echo "$*" | tee -a "$LOG"; }

# chamar <metodo> <rota> [corpo-json] [token]: grava a resposta em $TMP/corpo e o status em STATUS.
chamar() {
    local metodo="$1" rota="$2" corpo="${3:-}" token="${4:-}"
    local args=(-s -o "$TMP/corpo" -w "%{http_code}" -X "$metodo" --max-time 150
                -H "Content-Type: application/json")
    if [ -n "$token" ]; then
        printf 'Authorization: Bearer %s\n' "$token" > "$TMP/cabecalho"
        args+=(-H "@$TMP/cabecalho")
    fi
    if [ -n "$corpo" ]; then
        printf '%s' "$corpo" > "$TMP/envio"
        args+=(--data-binary "@$TMP/envio")
    fi
    STATUS="$(curl "${args[@]}" "$API/$rota" 2>/dev/null)" || STATUS="000"
    rm -f "$TMP/cabecalho" "$TMP/envio"
}

# campo <nome> [<subcampo>]: le um campo do JSON da ultima resposta (vazio se nao houver).
campo() {
    "$PY" - "$TMP/corpo" "$@" <<'PY' 2>/dev/null
import json, sys
try:
    dado = json.load(open(sys.argv[1], encoding="utf-8"))
    for chave in sys.argv[2:]:
        dado = dado.get(chave) if isinstance(dado, dict) else None
    print("" if dado is None else (str(dado).lower() if isinstance(dado, bool) else dado))
except Exception:
    print("")
PY
}

# json <chave> <valor> ...: monta um objeto JSON com os pares dados.
json() {
    "$PY" -c 'import json, sys; a = sys.argv[1:]; print(json.dumps(dict(zip(a[::2], a[1::2]))))' "$@"
}

# conferir <descricao> <esperado> <obtido>
conferir() {
    if [ "$2" = "$3" ]; then
        OK=$((OK + 1))
        log "  [OK]     $1: esperado $2, obtido $3"
    else
        FALHAS=$((FALHAS + 1))
        log "  [FALHOU] $1: esperado $2, obtido $3"
    fi
}

# Codigo TOTP do segredo (lido da URI otpauth:// pela entrada padrao, nunca pela linha de comando).
codigo_certo() {
    printf '%s' "$URI_TOTP" | "$PY" -c 'import sys, pyotp; print(pyotp.parse_uri(sys.stdin.read().strip()).now())'
}

# Codigo de 6 digitos fora da janela aceita (passo anterior, atual e seguinte).
codigo_errado() {
    printf '%s' "$URI_TOTP" | "$PY" -c '
import sys, time, pyotp
t = pyotp.parse_uri(sys.stdin.read().strip())
agora = time.time()
validos = {t.at(agora + d) for d in (-60, -30, 0, 30, 60)}
n = (int(t.now()) + 500000) % 1000000
while f"{n:06d}" in validos:
    n = (n + 1) % 1000000
print(f"{n:06d}")'
}

limpar() {
    local token tentativa
    log ""
    log "## Limpeza: DELETE /empresa da conta temporaria"
    if [ -z "$EMPRESA_ID" ]; then
        log "  nada a apagar (a empresa nao chegou a ser criada)"
    else
        for token in "$TOKEN_DEPOIS" "$TOKEN_ANTES" "$TOKEN_CADASTRO"; do
            [ -n "$token" ] || continue
            for tentativa in 1 2 3; do
                chamar DELETE empresa "$(json confirmacao "$EMPRESA_ID" senha "$SENHA")" "$token"
                [ "$STATUS" = "202" ] || break
            done
            [ "$STATUS" = "401" ] || break
        done
        conferir "DELETE /empresa apaga a empresa temporaria" 200 "$STATUS"
        chamar POST login "$(json email "$EMAIL" senha "$SENHA")"
        conferir "POST /login da conta apagada e recusado" 401 "$STATUS"
    fi
    rm -rf "$TMP"

    log ""
    log "# passos aprovados: $OK; reprovados: $FALHAS"
    if [ "$FALHAS" -eq 0 ] && [ "$OK" -gt 0 ]; then
        log "# resultado: APROVADO"
        exit 0
    fi
    log "# resultado: REPROVADO"
    exit 1
}
trap limpar EXIT

COMMIT="$(git -C "$RAIZ" rev-parse --short HEAD)"
{
    echo "# 2FA ANTES e DEPOIS, mesma conta, contra a API"
    echo "# codigo de missao: $MISSAO_CODIGO"
    echo "# api: $API"
    echo "# commit do script: $COMMIT"
    echo "# conta temporaria: $EMAIL_MASCARADO (empresa criada e apagada pelo script)"
    echo "# senha, token, desafio, segredo TOTP e codigos nao sao gravados"
    echo "# gerado em: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$LOG"
cat "$LOG"

log ""
log "## Preparacao"
chamar POST empresas "$(json empresa "$EMPRESA_NOME" nome "Teste 2FA" email "$EMAIL" senha "$SENHA")"
conferir "POST /empresas cria a conta temporaria (gestor)" 201 "$STATUS"
if [ "$STATUS" != "201" ]; then
    log "  cadastro recusado; sem conta nao ha teste (429 = limite de 5 cadastros por hora por IP)"
    exit 1
fi
EMPRESA_ID="$(campo usuario empresaId)"
TOKEN_CADASTRO="$(campo token)"

log ""
log "## ANTES: 2FA desligado"
chamar POST login "$(json email "$EMAIL" senha "$SENHA")"
conferir "POST /login so com a senha" 200 "$STATUS"
TOKEN_ANTES="$(campo token)"
conferir "a resposta traz token (sessao aberta sem segundo fator)" sim "$([ -n "$TOKEN_ANTES" ] && echo sim || echo nao)"
chamar GET eu "" "$TOKEN_ANTES"
conferir "GET /eu com esse token" 200 "$STATUS"
conferir "totpAtivo da conta" false "$(campo totpAtivo)"

log ""
log "## Ativacao do 2FA pela API"
chamar POST 2fa/iniciar "" "$TOKEN_ANTES"
conferir "POST /2fa/iniciar devolve a URI otpauth://" 200 "$STATUS"
URI_TOTP="$(campo uri)"
case "$URI_TOTP" in
    otpauth://*) ;;
    *) log "  sem URI otpauth:// na resposta; nao da para seguir"; exit 1 ;;
esac
chamar POST 2fa/ativar "$(json codigo "$(codigo_certo)")" "$TOKEN_ANTES"
conferir "POST /2fa/ativar com o codigo do app autenticador" 200 "$STATUS"
conferir "a resposta traz 10 codigos de recuperacao" 10 \
    "$("$PY" -c 'import json, sys; print(len(json.load(open(sys.argv[1])).get("recuperacao") or []))' "$TMP/corpo" 2>/dev/null)"
: > "$TMP/corpo"

log ""
log "## DEPOIS: 2FA ligado, mesma conta"
chamar POST login "$(json email "$EMAIL" senha "$SENHA")"
conferir "POST /login so com a senha" 200 "$STATUS"
conferir "a resposta traz token" nao "$([ -n "$(campo token)" ] && echo sim || echo nao)"
conferir "a resposta pede o segundo fator (exige2fa)" true "$(campo exige2fa)"
DESAFIO="$(campo desafio)"
conferir "a resposta traz o desafio" sim "$([ -n "$DESAFIO" ] && echo sim || echo nao)"
chamar GET eu "" "$DESAFIO"
conferir "GET /eu usando o desafio como token" 401 "$STATUS"
chamar POST login/2fa "$(json desafio "$DESAFIO" codigo "$(codigo_errado)")"
conferir "POST /login/2fa com codigo errado" 401 "$STATUS"
conferir "a resposta do codigo errado traz token" nao "$([ -n "$(campo token)" ] && echo sim || echo nao)"

# O codigo usado no /2fa/ativar nao vale de novo (anti-reuso): espera o proximo passo de 30 s.
ESPERA=$((30 - $(date +%s) % 30 + 2))
log "  (aguardando ${ESPERA}s pelo proximo codigo: o da ativacao nao pode ser reusado)"
sleep "$ESPERA"
chamar POST login/2fa "$(json desafio "$DESAFIO" codigo "$(codigo_certo)")"
conferir "POST /login/2fa com o codigo certo" 200 "$STATUS"
TOKEN_DEPOIS="$(campo token)"
conferir "a resposta traz token" sim "$([ -n "$TOKEN_DEPOIS" ] && echo sim || echo nao)"
chamar GET eu "" "$TOKEN_DEPOIS"
conferir "GET /eu com o token do segundo passo" 200 "$STATUS"
conferir "totpAtivo da conta" true "$(campo totpAtivo)"
