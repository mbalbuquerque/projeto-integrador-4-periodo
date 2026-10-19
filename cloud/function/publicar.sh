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
python - <<'PY'
import zipfile
arquivos = ["function_app.py", "contrato.py", "seguranca.py", "cadastros.py",
            "host.json", "requirements.txt"]
with zipfile.ZipFile("publicar.zip", "w") as z:
    for nome in arquivos:
        z.write(nome)
PY

echo "3/3 Deploy"
az functionapp deployment source config-zip -g "$GRUPO" -n "$FUNCAO" \
  --src publicar.zip --build-remote true
rm -f publicar.zip
echo "Publicado."
