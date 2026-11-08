#!/usr/bin/env bash
# Publica a Azure Function do ColdTrack.
#
# Requer: Azure CLI logado na assinatura do projeto (az login) e Python.
# Uso (na pasta cloud/function):  bash publicar.sh
set -euo pipefail

GRUPO="rg-coldtrack"
FUNCAO="func-coldtrack-7319"

cd "$(dirname "$0")"

echo "1/3 Testes"
python -m unittest

echo "2/3 Pacote"
rm -rf __pycache__ publicar.zip
# A lista de arquivos e a mesma do workflow publicar-api.yml: pacote.txt.
python - <<'PY'
import zipfile
with open("pacote.txt", encoding="utf-8") as f:
    arquivos = [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
with zipfile.ZipFile("publicar.zip", "w") as z:
    for nome in arquivos:
        z.write(nome)
PY

echo "3/3 Deploy"
az functionapp deployment source config-zip -g "$GRUPO" -n "$FUNCAO" \
  --src publicar.zip --build-remote true
rm -f publicar.zip
echo "Publicado."
