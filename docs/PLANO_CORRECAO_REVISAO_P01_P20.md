# Plano de correção após a revisão P01–P20

**Estado em 20/10/2026:** R01–R11 implementados e validados localmente; aceite
empírico de P12/P13/P14 ainda pendente. Base da revisão: `26da1b6d`.
Este documento reúne os achados verificados no checkout, a triagem
do DeepSeek Flash (low) e a revisão independente do Claude Opus (high). O Codex
orquestra, confere os diffs e registra os resultados; Fable não participa.

## 1. Evidência de partida e limites

- Backend sem integração: **713 testes passaram**. Frontend: **86 testes Vitest
  passaram** e build passou. Suíte rápida de operações: **33 passaram, 1 falhou**
  (`ops/test_synthetic_monitor.py`, marcador de e-mail/CPF no alerta). O lint
  estrito `oxlint --max-warnings=0` falhou com dois avisos. Estes números são
  baseline da revisão, não validação das futuras correções.
- Não houve, nesta revisão, rodada de integração PostgreSQL/MinIO, E2E noturno
  nem as sete janelas autenticadas de homologação. P12/P13/P14 seguem com
  aceite empírico pendente, mesmo que o código e os documentos estejam presentes.
- Cada entrega abaixo tem teste focado. Fazer **uma** rodada local ampla após
  integrar as correções, sem repetir pytest/Vitest/build inteiro a cada tarefa.
  Não executar carga real, deploy, push nem ativar sonda comercial para elaborar
  ou validar estaticamente este plano.

## 2. Ordem e responsáveis sugeridos

| ID | Prioridade | Executor / esforço | Alteração delimitada | Critério de aceite focado |
|---|---|---|---|---|
| R01 · P13 | P0 | Opus / high | Fazer a CLI de carga falhar antes de qualquer requisição se não houver p95 do P12 ou teto absoluto aprovado. `--dry-run` continua possível sem baseline, mas não equivale a autorização para carga. | Teste da CLI sem limite: saída não zero e transporte falso com zero chamadas. Caminho válido mantém os limites no relatório. |
| R02 · P13 | P0 | Opus / high | Ligar à CLI uma fonte **real e autenticada** de conexões/timeout de pool; definir se `/internal/metrics` de P10 cobre todos os workers/réplicas ou se é necessário sinal do PostgreSQL. Valor ausente/erro de scrape deve bloquear carga, nunca virar zero. Não gravar token nem séries sensíveis no JSON. | Probe falso confirma injeção, timeout e teto disparando abort; falha do probe interrompe a execução. Revisão do contrato da fonte antes de rede real. |
| R03 · P13 | P0 | Opus / high | Guardar timestamp monotônico por amostra e avaliar taxa de erro em janela deslizante de 120 s após o aquecimento; documentar a regra para tráfego insuficiente. | Testes com relógio falso: falhas antigas saem da janela, surto recente >5% dispara e recuperação não depende da média histórica. |
| R04 · P13 | P1 | DeepSeek / medium | Propagar `scenario_id` em cada amostra e agrupar relatório por essa identidade; `route_template` permanece metadado. Corrigir também o caso de produtos `include_total` ligado/desligado. | Dois cenários na mesma rota geram duas linhas com amostras e percentis próprios. Nenhuma duplicação no total. |
| R05 · P13 | P1 | DeepSeek / low | Fazer `--dry-run` com URL fornecida validar a allowlist de homologação sem abrir rede; se não houver URL, declarar explicitamente que a allowlist não foi verificada. Hoje o retorno do dry-run ocorre antes de `check_load_allowed`. | Host não permitido falha offline; dry-run sem URL nunca afirma validação da allowlist. |
| R06 · P15 | P0 | Opus / high | Exigir HTTPS na **sonda comercial** antes do login, sem prejudicar health local sem credencial. Preservar o bloqueio de redirect já existente. Rejeitar userinfo, query e caminho inesperado na origem credenciada. | URLs HTTP/malformadas causam erro antes de `_request`; senha não aparece em mensagem, log ou artefato. |
| R07 · P15 | P0 | Opus / medium | Se `SYNTHETIC_COMMERCIAL_ENABLED=true`, falta de credencial BR ou EU vira erro de configuração e saída não zero. `skipped_inactive` fica reservado à sonda deliberadamente desligada. Conferir efeito no scheduler e nos alertas. | Teste para cada mercado ausente e para sonda desligada; execução habilitada incompleta não produz `ok=true`. |
| R08 · P15 | P1 | DeepSeek / low | Restringir a sanitização de `Cookie` ao campo sensível, sem engolir conteúdo subsequente da mesma linha. Manter proteção para cookies com atributos e dados pessoais próximos. | O teste atual de alerta passa sem relaxar asserções; casos negativos provam ausência de segredo, e-mail e CPF. |
| R09 · P17 | P1 | DeepSeek / medium | Espelhar a ordem operacional de `frontend/e2e/README.md` no nightly: infra, migrations/seed, backend, frontend e espera HTTP/health antes do Playwright. Encerrar os contêineres também em falha. | Inspeção do workflow e smoke Chromium local com stack descartável; teste falha cedo se frontend/backend não estiverem prontos. |
| R10 · P17 | P1 | DeepSeek / medium | Declarar projetos desktop Chromium, mobile Chromium e WebKit no Playwright e selecionar explicitamente o projeto da matriz com `--project`; remover a variável de perfil inoperante. | `playwright test --list --project=<perfil>` mostra apenas o projeto esperado; perfil inválido falha. Validar YAML/actionlint. |
| R11 · P20 | P2 | DeepSeek / low | Eliminar os dois avisos `react(set-state-in-effect)` em `PlatformPage.tsx` e `RetentionGovernancePanel.tsx`, então mudar o script de lint de 46 para `--max-warnings=0`. Preservar carregamento inicial e refresh após ação. | Oxlint zero; testes de componentes afetados, Vitest completo e build no checkpoint combinado. |

P13 e P15 são frentes independentes, mas **R01–R03 e R06–R07 precedem qualquer
execução de carga ou sonda credenciada**. R04–R05 completam a confiabilidade do
relatório e do dry-run. P17 e P20 podem avançar em paralelo sem tocar esses
arquivos. Fazer commits separados por frente para facilitar revisão e reversão.

## 3. Checkpoints sem repetição

1. **Por frente:** executar apenas os testes novos/afetados e revisão estática
   do diff. Para P13, usar transporte, relógio e probe falsos; para P15, nenhuma
   credencial real. Para P17, primeiro inspecionar workflow/config e listar
   projetos sem navegador; para P20, lint estrito dos arquivos afetados.
2. **Após integrar R01–R11:** uma rodada local: `ops/test_benchmark_canary.py`,
   `ops/load/test_load_generator.py`, `ops/test_synthetic_monitor.py` e testes
   de CI/restore pertinentes; backend `-m "not integration"`; frontend lint 0,
   Vitest e build. Esperado: corrigir a falha ops observada e preservar os
   713/86 testes de partida. Registrar contagens novas e duração, sem exigir
   números idênticos se forem adicionados testes.
3. **Gate de infraestrutura:** PostgreSQL/Redis/MinIO descartáveis para
   integrações relevantes; um smoke E2E Chromium local e verificação dos três
   perfis com `--list`. O nightly completo de três repetições e as matrizes de
   navegador entram no checkpoint P20/final, após o workflow estar apto.
4. **Gate externo posterior:** homologação representativa, contas BR/EU,
   coletor de métricas, janela e limites aprovados. Só então executar P12 em
   sete horários distintos e, depois, a rampa P13. P14a–d só prosseguem se
   essas medições apontarem gargalo. Sem evidência, registrar "aceite pendente".

## 4. Dependências e decisões em aberto

- **Fonte de pressão do banco:** `/internal/metrics` de P10 tem token e métricas
  de pool por processo. Um scrape de uma réplica pode subestimar o uso total.
  Antes de implementar R02, fixar um coletor que cubra todos os workers ou um
  sinal do PostgreSQL, com custo e permissões restritos. A falha da coleta deve
  impedir a carga.
- **Primeira rampa:** P13 não cria seu próprio baseline. Usar p95 de P12 para
  o mesmo cenário/mercado/ambiente ou um teto absoluto aprovado e registrado.
  Não criar uma exceção silenciosa para “primeira execução”.
- **Diretórios:** a conta `benchmark_readonly` do P11 não pode ler dados de
  clientes/representantes. A cobertura de P12/P13 desses cenários depende de
  decisão de acesso sintético restrito; não trocar pelo papel admin.
- **Homologação:** responsável define ambiente, janela, orçamento de custo,
  rollback e acesso às contas técnicas. Nenhuma dessas decisões é exigida para
  iniciar R01–R11, mas todas condicionam o aceite empírico.

## 5. Risco e definição de pronto

- R01 pode quebrar scripts que omitem baseline; localizar invocações antes de
  mudar a CLI. R02 pode confundir métricas por processo com total do banco.
  R06 pode bloquear configurações locais com HTTP, o que é esperado no fluxo
  credenciado. R07 pode criar alertas novos para configuração incompleta;
  verificar essa transição no scheduler. R09–R10 podem expor instabilidade
  WebKit/mobile real e aumentar a duração do nightly; não mascarar com retry.
- O plano de **código** estará pronto quando R01–R11 e seus gates focados
  passarem, o checkpoint combinado estiver verde e o workflow não prometer
  cobertura que não executa. A **campanha P01–P20** só terá aceite global após
  os gates externos de P12/P13 e as decisões condicionais de P14 documentadas.

## 6. Execução local e evidências (20/10/2026)

- **P13, R01–R05:** limite p95 obrigatório fora do dry-run; probe autenticado de
  `/internal/metrics` que falha fechado; somente 1 réplica × 1 worker até existir
  coleta agregada; janela deslizante de 120 s; estatísticas por identidade do
  cenário; dry-run valida a allowlist quando recebe URL. A série de início do
  processo passou a preservar precisão suficiente para detectar reinício.
  Commit `82c4a003`. Os 74 testes focados passaram; dry-run sem URL retornou
  `allowlist_status: unverified` sem rede.
- **P15, R06–R08:** origem comercial exige HTTPS e validação antes do login;
  credenciais BR/EU ausentes com sonda habilitada produzem `config_error` e
  saída 2; cookies, inclusive valores entre aspas e atributos, são redigidos
  sem engolir texto/PII posterior. O scheduler usa título próprio para erro de
  configuração e considera ambos os títulos na recuperação. Commit `f187256e`.
  Os 20 testes focados e 24 subcasos passaram.
- **P17, R09–R10:** nightly inicia backend/frontend após migrations e seed,
  aguarda disponibilidade e seleciona os projetos Chromium desktop, Chromium
  mobile e WebKit por `--project`. Commit `eef4510d`. A listagem mostrou 18
  casos, seis por projeto, e o YAML/Compose foram validados.
- **P20, R11:** lint exige zero aviso; carregamento inicial e refresh dos
  componentes afetados foram ajustados. Commit `c69f8793`. Lint e build
  passaram.
- **Checkpoint combinado:** 105 testes operacionais e 26 subcasos passaram;
  backend sem integração: 713 passaram; Vitest: 86 passaram; lint com zero
  aviso e build passaram. Integrações PostgreSQL/Redis/MinIO passaram em banco
  descartável separado do seed E2E. As seis jornadas Chromium passaram juntas,
  sem retry, após correções adicionais de CORS, seletor da senha, domínio de
  e-mail aceito pela API, traduções e preços obrigatórios no seed EU. O seed
  Após o ajuste final do formulário, seus quatro testes específicos, lint e
  build passaram novamente. O seed atualizado passou duas execuções idempotentes e uma primeira execução em
  banco novo; o banco novo continha zero e-mails `.invalid`, quatro preços EU
  e descrição inglesa.
- **Limites do checkpoint:** neste checkout Windows em unidade de rede, o
  bind mount do frontend no Docker não expôs `package-lock.json`; o smoke usou
  Vite local com API, Postgres, Redis e MinIO em contêineres descartáveis. A
  imagem de testes do backend não contém `ops/`, então o teste de diagnóstico
  fora da marca de integração foi ignorado apenas na coleta dentro da imagem;
  a suíte de integração marcada passou. Chromium mobile e WebKit foram
  listados, sem executar navegadores reais nesta rodada. Nenhuma carga real,
  sonda comercial credenciada, deploy ou push foi feita.
- **Aceite externo:** ainda exige ambiente de homologação, contas técnicas,
  coletor/topologia coberta, teto de latência aprovado ou baseline P12 e janela
  autorizada. P12 requer sete horários válidos; P13 requer rampa real com
  abortos observáveis; P14 permanece condicional às medições. Esses itens não
  são comprovados pelos testes locais acima.
