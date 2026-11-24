#!/usr/bin/env bash
# Script para gerar evidências de antes/depois da proteção IDOR
# Uso: bash seguranca/testes/idor_antes_depois.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SEGURANCA_DIR="$REPO_ROOT/seguranca"
EVIDENCIAS_DIR="$SEGURANCA_DIR/evidencias"
ANTES_DIR="C:/tmp/antes"
DEPOIS_DIR="C:/tmp/depois"
MISSAO_CODIGO="XXXXXX"  # Placeholder até o professor passar o código oficial

echo "=== Gerando evidências de IDOR (antes/depois) ==="
echo "Código da missão: $MISSAO_CODIGO"
echo ""

# Verifica se estamos no repo correto
if [ ! -d "$REPO_ROOT/.git" ]; then
    echo "ERRO: Execute a partir da raiz do repositório"
    exit 1
fi

# Commit base para "antes" (d44b301 - antes do IDOR)
ANTES_COMMIT="d44b301"

# Limpa worktrees anteriores se existirem
if [ -d "$ANTES_DIR" ]; then
    echo "Removendo worktree anterior em $ANTES_DIR..."
    git worktree remove --force "$ANTES_DIR" 2>/dev/null || true
    rm -rf "$ANTES_DIR"
fi

if [ -d "$DEPOIS_DIR" ]; then
    echo "Removendo worktree anterior em $DEPOIS_DIR..."
    git worktree remove --force "$DEPOIS_DIR" 2>/dev/null || true
    rm -rf "$DEPOIS_DIR"
fi

# Cria worktree para o commit antigo (antes do IDOR)
echo "Criando worktree para commit $ANTES_COMMIT (antes do IDOR)..."
git worktree add "$ANTES_DIR" "$ANTES_COMMIT"

# Cria worktree para o estado atual (depois do IDOR)
echo "Criando worktree para estado atual (depois do IDOR)..."
git worktree add "$DEPOIS_DIR" HEAD

# Função para rodar testes de IDOR em um worktree
rodar_testes_idor() {
    local worktree_dir="$1"
    local output_file="$2"
    local label="$3"

    echo "Rodando testes de IDOR em $label..."
    cd "$worktree_dir"

    # Determina o Python correto
    PYTHON_CMD="python"
    if command -v "C:/Users/Chupetinha/AppData/Local/Programs/Python/Python312/python.exe" &> /dev/null; then
        PYTHON_CMD="C:/Users/Chupetinha/AppData/Local/Programs/Python/Python312/python.exe"
    fi

    # Instala dependências se necessário
    if [ -f "cloud/function/requirements.txt" ]; then
        "$PYTHON_CMD" -m pip install -q -r cloud/function/requirements.txt 2>/dev/null || true
    fi

    # Roda os testes de IDOR se o arquivo existir
    if [ -f "seguranca/testes/test_idor.py" ]; then
        cd seguranca/testes
        "$PYTHON_CMD" -m pytest test_idor.py -v 2>&1 | tee "$output_file"
        local exit_code=${PIPESTATUS[0]}
        if [ $exit_code -eq 0 ]; then
            echo "✓ Testes de IDOR passaram em $label" | tee -a "$output_file"
        else
            echo "✗ Testes de IDOR falharam em $label (esperado para o 'antes')" | tee -a "$output_file"
        fi
    else
        echo "AVISO: test_idor.py não encontrado em $worktree_dir (commit anterior ao IDOR)" | tee "$output_file"
        echo "Isso é esperado - o commit antigo não tem os testes de IDOR implementados." | tee -a "$output_file"
    fi
}

# Roda testes no commit antigo (ANTES)
ANTES_OUTPUT="$EVIDENCIAS_DIR/${MISSAO_CODIGO}-idor-antes.txt"
echo ""
echo "=== TESTE ANTES (commit $ANTES_COMMIT) ==="
rodar_testes_idor "$ANTES_DIR" "$ANTES_OUTPUT" "ANTES (commit $ANTES_COMMIT)"

# Roda testes no estado atual (DEPOIS)
DEPOIS_OUTPUT="$EVIDENCIAS_DIR/${MISSAO_CODIGO}-idor-depois.txt"
echo ""
echo "=== TESTE DEPOIS (HEAD atual) ==="
rodar_testes_idor "$DEPOIS_DIR" "$DEPOIS_OUTPUT" "DEPOIS (HEAD atual)"

# Limpa worktrees
echo ""
echo "Limpando worktrees temporários..."
git worktree remove --force "$ANTES_DIR" 2>/dev/null || true
git worktree remove --force "$DEPOIS_DIR" 2>/dev/null || true
rm -rf "$ANTES_DIR" "$DEPOIS_DIR"

# Resumo
echo ""
echo "=== RESUMO ==="
echo "Arquivos gerados:"
echo "  - $ANTES_OUTPUT"
echo "  - $DEPOIS_OUTPUT"
echo ""
echo "Compare os resultados para verificar a proteção IDOR implementada."
echo "No 'antes', espera-se falhas (acesso indevido permitido)."
echo "No 'depois', espera-se sucesso (bloqueio com 404)."