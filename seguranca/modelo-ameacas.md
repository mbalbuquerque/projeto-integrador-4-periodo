# Modelo de ameaças (resumo da entrega)

Fluxo principal: sensor (ESP32-C3) → API (Azure Functions) → Cosmos DB → painel web.
Versão completa por categoria STRIDE em [`docs/stride.md`](../docs/stride.md).

| Ameaça (STRIDE) | Exemplo no ColdTrack | Impacto | Tratada por |
|---|---|---|---|
| Spoofing | Alguém com a senha vazada de um gestor entra no painel | Vê e apaga sensores, veículos e usuários da empresa | **2FA com código de uso único (TOTP)** no login |
| Elevation of privilege / IDOR | Usuário da empresa A troca o `deviceId` e lê a carga da empresa B | Vazamento de dados de cliente | **Verificação de dono** em toda rota com ID (`exigir_dono`) |
| Spoofing do sensor | Alguém manda leitura falsa para `/api/telemetria` | Alarme falso, ou carga estragada sem alarme | Chave aleatória por sensor, guardada só como SHA-256 (já existia) |
| Denial of service | Força bruta no login | Conta bloqueada e custo na nuvem | Limite por IP e espera crescente no login (já existia) |

## O que continua aberto

- A chave do sensor fica gravada na flash da placa: quem tiver a placa na mão consegue lê-la e forjar aquele sensor.
- O 2FA vale para o gestor; o motorista não tem 2FA.