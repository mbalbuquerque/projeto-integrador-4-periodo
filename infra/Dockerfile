# Imagem da API do ColdTrack (Azure Functions, Python 3.11).
# Contexto de build: cloud/function
#   docker build -f infra/Dockerfile -t coldtrack-api cloud/function
# Configuração por variáveis de ambiente (ver cloud/function/local.settings.example.json):
#   COSMOS_CONNECTION, COSMOS_DATABASE, COSMOS_CONTAINER, JWT_SECRET,
#   AOAI_ENDPOINT, AOAI_DEPLOY_CHAT, AOAI_DEPLOY_EMBED, AOAI_API_VERSION
# Nenhum segredo entra na imagem.
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true \
    FUNCTIONS_WORKER_RUNTIME=python

COPY requirements.txt /
RUN pip install --no-cache-dir -r /requirements.txt

COPY function_app.py contrato.py seguranca.py cadastros.py chat.py assistente.py limites.py \
     predicao.py modelo_risco.json base_chat.json openapi.json host.json /home/site/wwwroot/
