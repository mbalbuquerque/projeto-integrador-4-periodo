# Declaração de uso de ferramentas de IA

O professor permite o uso de IA desde que declarado. Cada integrante preenche a própria
declaração: ferramenta, para que foi usada e o que foi conferido ou alterado por você.

| Integrante | Ferramenta | Para que foi usada | O que foi conferido ou alterado |
|---|---|---|---|
| Everson | _a preencher por cada integrante_ | _a preencher_ | _a preencher_ |
| Emmanuel | **Arena AI & Gemini** | Pesquisa de mercado(`docs\custos`); Organização de ideias; Planejamento de datas(`docs\entrega`); Organização de documentação(`docs\slides`, `docs\apresentacao.pptx`, `docs\apresentacao.md`); | Ajustei datas de entrega, organizei arquivos que foram commitados através do computador de Marcelo, e algumas vezes por Everson e Enzo, fiz a pesquisa de mercado e pesquisa de possíveis valores de rotas de envios e custos em casos de perca de carga. |
| Enzo | **Gemini / Hermes (Nous Research)** | Auditoria de segurança completa do back-end e front-end; implementação de 2FA TOTP + recovery codes no back-end (`cloud/function/seguranca.py`, `function_app.py`); implementação de proteção IDOR (`exigir_dono`) nas rotas de dispositivos, sensores, leituras, veículos, viagens, usuários; criação de testes unitários e de contorno (`test_2fa.py`, `test_idor.py`); atualização da documentação na pasta `seguranca/` (`README.md`, `modelo-ameacas.md`, `uso-de-ia.md`). | Conferi toda a lógica de TOTP (anti-replay via contador, janela ±30s), geração/validação/invalidação de recovery codes (hash scrypt, uso único), fluxo de login em 2 passos (desafio JWT 5min), proteção IDOR (404 para recurso inexistente ou de outro dono, logs com `MISSAO_CODIGO`), e integração com front-end já existente (`DoisFatores.jsx`, `Login.jsx`). |
| José Allamberg | **ChatGPT e Gemini** | Organizar o roteiro e o texto das apresentações do projeto. | Revisei o conteúdo dos slides contra o que está no repositório e ajustei a ordem e a linguagem para a apresentação. |
| Marcelo | **ChatGPT e Gemini** | Apoio no front-end do painel: dúvidas de React, componentes e ajustes de layout. | Testei as telas no navegador e adaptei o código sugerido ao padrão do projeto antes de subir. |
| Gabriel | **ChatGPT e Gemini** | Apoio na configuração de CI/CD (GitHub Actions) e em pontos de segurança da API. | Conferi os workflows rodando no GitHub Actions e revisei as sugestões de segurança antes de aplicar. |

Se um integrante não usou nenhuma ferramenta, escreve "nenhuma" na própria linha.
