# Modelo de ameaças (resumo da entrega)

Fluxo principal: sensor (ESP32-C3) → API (Azure Functions) → Cosmos DB → painel web.
Versão completa por categoria STRIDE em [`docs/stride.md`](../docs/stride.md).

| Ameaça (STRIDE) | Exemplo no ColdTrack | Impacto | Tratada por |
|---|---|---|---|
| **Spoofing** | Alguém com a senha vazada de um gestor entra no painel | Vê e apaga sensores, veículos e usuários da empresa | **2FA com código de uso único (TOTP)** no login (`cloud/function/seguranca.py` + `function_app.py` rotas `/2fa/*`, `/login/2fa`) |
| **Elevation of privilege / IDOR** | Usuário da empresa A troca o `deviceId` e lê a carga da empresa B | Vazamento de dados de cliente | **Verificação de dono** em toda rota com ID (`exigir_dono` em `function_app.py`) |
| **Spoofing do sensor** | Alguém manda leitura falsa para `/api/telemetria` | Alarme falso, ou carga estragada sem alarme | Chave aleatória por sensor, guardada só como SHA-256 (já existia) |
| **Denial of service** | Força bruta no login | Conta bloqueada e custo na nuvem | Limite por IP e espera crescente no login (já existia) |
| **Information Disclosure** | Usuário acessa leituras de sensor de outra empresa via `?deviceId=` | Vazamento de temperatura/carga de cliente | `exigir_dono("sensor", deviceId, usuario)` em `GET /api/leituras` e `GET /api/predict/sensor` |
| **Tampering** | Gestor malicioso altera veículo/viagem de outro gestor via `PUT /api/veiculos/{id}` | Dados de frota corrompidos | `exigir_dono("veiculo", id, usuario)` e `exigir_dono("viagem", id, usuario)` nas rotas PUT/DELETE |

## O que continua aberto

- A chave do sensor fica gravada na flash da placa: quem tiver a placa na mão consegue lê-la e forjar aquele sensor.
- O 2FA vale para o gestor; o motorista não tem 2FA.
- O Cosmos DB não tem criptografia em repouso gerenciada pelo cliente (usa chaves Microsoft).