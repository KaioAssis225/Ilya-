# Análise de aderência à LGPD — Projeto Ilya

**Data da análise:** 05/08/2026
**Branch:** `codex/analise-lgpd-2026-08-05`
**Commit-base analisado:** `b21b765`
**Escopo:** código-fonte, modelos de dados, API, frontend, autenticação,
autorização, logs, integrações, backup e documentação operacional.

> Este documento é uma análise técnica de privacidade e segurança, não um
> parecer jurídico nem uma certificação de conformidade. Bases legais, prazos
> fiscais, contratos, identidade do controlador e decisões de negócio devem ser
> confirmados pela empresa com apoio jurídico/contábil.

## 1. Conclusão executiva

O Projeto Ilya está **parcialmente aderente à LGPD** e possui uma base técnica
de segurança acima da média para o seu porte. Não foi encontrada, nesta
revisão, uma exposição crítica imediata que justifique retirar o sistema do ar.
Entretanto, **ainda não é seguro afirmar que o tratamento está integralmente em
conformidade com a LGPD**.

O principal desequilíbrio é:

- **engenharia e segurança:** maduras;
- **governança, transparência e ciclo de vida dos dados:** incompletos.

### Resultado por domínio

| Domínio | Situação | Resumo |
|---|---|---|
| Segurança técnica | Adequado, com ressalvas | Argon2, JWT curto, refresh token protegido, RBAC, rate limit, CSP, CORS, sanitização de imagens, backups criptografados |
| Direitos do titular | Parcial | Exportação e anonimização existem, mas não cobrem igualmente clientes, representantes e todos os dados associados |
| Transparência | Parcial/insuficiente | Há política pública, porém faltam identificação jurídica completa, operadores, transferências, bases legais definidas e prazos concretos |
| Necessidade e minimização | Parcial | Não há dados sensíveis estruturados, mas endereço completo é obrigatório cedo demais e algumas roles têm acesso amplo |
| Retenção e descarte | Insuficiente | Refresh tokens e backups têm retenção; clientes, representantes, pedidos, históricos e assinaturas não têm matriz nem descarte automatizado |
| Governança e prestação de contas | Insuficiente | Não foi localizado ROPA, RIPD, ato formal do encarregado, política interna de privacidade ou trilha completa de alterações cadastrais |
| Incidentes | Parcial | Existe orientação operacional, mas falta procedimento LGPD com responsáveis, registro e prazo regulatório de 3 dias úteis |
| Terceiros e transferência internacional | Não comprovado | Vercel, Railway e eventuais storages precisam ser inventariados, contratados e avaliados |

## 2. Dados pessoais identificados

### 2.1 Titulares

- clientes finais;
- representantes;
- usuários internos;
- administradores;
- pessoas que criam ou alteram cadastros e pedidos.

### 2.2 Categorias de dados

| Categoria | Exemplos | Local principal |
|---|---|---|
| Identificação | nome, username, identificadores UUID | `users`, `clients`, `representatives` |
| Contato | telefone e e-mail | `clients`, `representatives`, `users` |
| Endereço | CEP, número, endereço, cidade e UF | `clients`, `representatives` |
| Autenticação | hash de senha, versão de autenticação, bloqueio e tentativas | `users`, `refresh_tokens` |
| Relação comercial | cliente, representante, itens, valores, descontos, observações | `orders`, `order_items` |
| Auditoria | usuário responsável, ação, detalhes e timestamps | `order_history`, logs |
| Assinatura | imagens de assinatura e convites de assinatura | `orders`, `signature_invitations` |
| Notificações | mensagens vinculadas ao usuário | `notifications` |
| Integração | IDs técnicos, payload e erros sanitizados | `integration_outbox` |
| Imagens | fotografias de produtos; metadados EXIF são removidos | storage local/objeto |
| Backup | cópia integral das tabelas anteriores | backups locais e off-site |

Não foram identificados campos estruturados para CPF, dados de saúde, religião,
biometria ou outros dados pessoais sensíveis. Contudo, os campos livres
`notes`, `observacao`, mensagens e detalhes de histórico podem receber conteúdo
pessoal ou sensível sem restrição semântica.

## 3. Controles já implementados e validados

### 3.1 Segurança e autenticação

- senhas armazenadas com Argon2 e `PASSWORD_PEPPER`;
- limite de 128 caracteres antes do Argon2, evitando abuso de recurso;
- access token com vida curta e refresh token opaco;
- refresh token persistido apenas como hash e entregue em cookie `HttpOnly`;
- rotação, detecção de reutilização, revogação de sessão e `logout-all`;
- invalidação de JWT por `auth_version`;
- bloqueio temporário após falhas de login;
- mitigação de enumeração por tempo de resposta no login;
- validação de origem contra CSRF nas rotas baseadas em cookie;
- CORS sem wildcard e restrito ao frontend esperado;
- headers CSP, HSTS, frame denial, MIME sniffing e Permissions Policy;
- rate limit e limites de upload/request;
- remoção de EXIF de imagens enviadas.

Evidências principais:

- [`backend/app/core/security.py`](../backend/app/core/security.py)
- [`backend/app/core/origin_guard.py`](../backend/app/core/origin_guard.py)
- [`backend/app/api/routers/auth.py`](../backend/app/api/routers/auth.py)
- [`backend/app/main.py`](../backend/app/main.py)
- [`frontend/vercel.json`](../frontend/vercel.json)

### 3.2 Controle de acesso

- RBAC é aplicado no backend, e não apenas ocultado no frontend;
- cliente acessa apenas o próprio cadastro e os próprios pedidos;
- representante acessa apenas o próprio registro, seus clientes e seus pedidos;
- pedidos têm verificações contra IDOR para cliente e representante;
- alterações de preço e desconto são filtradas por papel;
- operações administrativas sensíveis possuem restrições explícitas.

Evidências:

- [`backend/app/api/deps.py`](../backend/app/api/deps.py)
- [`backend/app/api/routers/clients.py`](../backend/app/api/routers/clients.py)
- [`backend/app/api/routers/reps.py`](../backend/app/api/routers/reps.py)
- [`backend/app/api/routers/orders.py`](../backend/app/api/routers/orders.py)
- [`backend/tests/test_rbac_authorization.py`](../backend/tests/test_rbac_authorization.py)

### 3.3 Direitos do titular já disponíveis

- consulta dos dados associados à conta em `GET /api/v1/auth/my-data`;
- exportação JSON com nova confirmação de senha em
  `POST /api/v1/auth/my-data/export`;
- anonimização self-service de cliente em `POST /api/v1/auth/anonymize`;
- anonimização administrativa de cliente;
- correção cadastral por endpoints de atualização;
- encerramento de sessões;
- exclusão da conta de acesso;
- política de privacidade acessível no frontend.

Evidências:

- [`backend/app/api/routers/auth.py`](../backend/app/api/routers/auth.py)
- [`backend/app/api/routers/clients.py`](../backend/app/api/routers/clients.py)
- [`frontend/src/components/ProfileModal.tsx`](../frontend/src/components/ProfileModal.tsx)
- [`frontend/src/pages/PrivacyPolicyPage.tsx`](../frontend/src/pages/PrivacyPolicyPage.tsx)

### 3.4 Backups

- backup de produção exige criptografia, salvo override explícito;
- criptografia AES-256-CBC com PBKDF2 e 200 mil iterações;
- checksum SHA-256;
- validação do catálogo e teste isolado de restauração;
- retenção GFS: 7 diários, 4 semanais e 6 mensais;
- tarefa diária às 02:00 e cópia off-site;
- segredos e backups estão ignorados pelo Git.

Evidências:

- [`ops/backup_database.py`](../ops/backup_database.py)
- [`ops/backup-production.ps1`](../ops/backup-production.ps1)
- [`ops/install-backup-task.ps1`](../ops/install-backup-task.ps1)
- [`.gitignore`](../.gitignore)

### 3.5 Validações executadas nesta análise

- backend: **179 testes aprovados**;
- frontend: `npm audit --omit=dev` com **0 vulnerabilidades conhecidas**;
- busca em arquivos versionados: nenhum segredo de produção encontrado; apenas
  placeholders e credenciais locais de CI;
- `pip-audit` não estava instalado no ambiente local, mas existe como etapa do
  quality gate do repositório.

## 4. Lacunas e riscos

### LGPD-01 — Registro das operações e bases legais não formalizados

**Prioridade: alta — governança**

Não foi localizado um inventário/ROPA que relacione, para cada tratamento:
titular, dado, origem, finalidade, hipótese legal, compartilhamento, sistema,
responsável, retenção e descarte.

A própria política informa que as bases legais “devem ser definidas”, em vez de
informar quais bases efetivamente sustentam cada finalidade. Isso deixa
incompletos os princípios de finalidade, adequação, necessidade, transparência
e prestação de contas, além do registro exigido pelo art. 37.

**Necessário:**

1. criar o ROPA do Ilya;
2. definir com jurídico a base legal por finalidade;
3. evitar usar consentimento quando execução de contrato ou obrigação legal for
   a base correta;
4. documentar eventual legítimo interesse com teste de balanceamento;
5. versionar e revisar o inventário quando novos recursos forem criados.

### LGPD-02 — Política de privacidade incompleta e parcialmente imprecisa

**Prioridade: alta — transparência**

A política existe, mas não informa adequadamente:

- razão social, CNPJ e endereço do controlador;
- identidade do encarregado ou justificativa formal de dispensa;
- confirmação de que `privacidade@ilya.com` existe e é monitorado;
- bases legais efetivamente adotadas;
- prazos ou critérios concretos de retenção por categoria;
- Vercel, Railway, armazenamento de objetos e demais operadores;
- países/regiões de armazenamento e eventual transferência internacional;
- procedimento, autenticação, prazo e acompanhamento das solicitações;
- informações completas sobre compartilhamento;
- tratamento de logs, backups e histórico;
- estado atual das assinaturas, que estão desativadas no produto, mas podem
  continuar presentes no banco histórico.

**Necessário:** substituir afirmações genéricas por informações reais e
verificáveis antes de publicar nova versão.

### LGPD-03 — Retenção e descarte incompletos

**Prioridade: alta — ciclo de vida**

Há retenção implementada para refresh tokens e backups. Não foi localizada uma
política técnica por categoria nem rotina de descarte para:

- clientes e representantes inativos;
- usuários desativados/anônimos;
- pedidos e itens;
- histórico de pedidos;
- notificações;
- convites de assinatura;
- imagens de assinatura já armazenadas;
- eventos entregues ou mortos da outbox;
- logs de aplicação e da infraestrutura;
- arquivos órfãos no storage.

O texto “pelo tempo necessário” não substitui uma matriz de retenção. O prazo
de pedidos e documentos comerciais deve ser confirmado com jurídico e
contabilidade; não deve ser inventado no código.

**Necessário:**

1. aprovar matriz de retenção;
2. implementar jobs idempotentes de descarte/anonimização;
3. registrar o resultado das execuções;
4. prever legal hold para disputa, auditoria ou obrigação legal;
5. aplicar descarte também a réplicas, backups e operadores, respeitando o ciclo
   técnico de expiração.

### LGPD-04 — Fluxos de direitos não cobrem todo o universo de dados e titulares

**Prioridade: alta — direitos do titular**

O endpoint `my-data` declara retornar “todos os dados pessoais”, mas não inclui,
entre outros:

- tentativas/bloqueios de autenticação;
- atribuições de dashboard;
- ações de histórico atribuídas ao usuário;
- clientes/representantes criados pelo usuário;
- registros de logs e auditoria;
- convites de assinatura emitidos ou consumidos;
- dados técnicos da outbox que identifiquem o usuário.

A anonimização self-service funciona somente para cliente. O representante pode
excluir a conta, mas isso não anonimiza o registro comercial de representante.
Da mesma forma, “Excluir Minha Conta” remove a credencial, mas preserva os dados
do cadastro comercial; o texto da interface pode levar o titular a entender que
todos os dados foram eliminados.

Além disso, exclusão e anonimização não exigem reautenticação por senha, embora
sejam ações irreversíveis. Um bearer token roubado seria suficiente.

**Necessário:**

- renomear e explicar claramente “excluir acesso” versus “eliminar/anonimizar
  dados”;
- exigir reautenticação nas ações irreversíveis;
- criar fluxo equivalente para representantes;
- ampliar o inventário usado na exportação;
- gerar protocolo/status para solicitações feitas fora do self-service;
- prever resposta fundamentada quando a eliminação for impedida por obrigação
  legal.

### LGPD-05 — Papel `produtos` possui acesso amplo a dados pessoais

**Prioridade: alta — necessidade e mínimo privilégio**

`UserRole.produtos` faz parte de `_DIRECTORY_ROLES` e `_ORDER_ROLES`. Portanto,
consegue listar todos os clientes, representantes e pedidos, incluindo dados de
contato e endereço, salvo filtros específicos.

Esse acesso pode ser uma decisão de negócio (“quase administrador”), mas precisa
ser justificado pela necessidade da função. Caso a equipe de produtos precise
apenas do catálogo e de dados agregados de venda, o acesso atual é excessivo.

**Necessário:** confirmar a matriz de responsabilidades e, se não houver
necessidade documentada, remover dados pessoais dessa role ou devolver respostas
minimizadas.

### LGPD-06 — Encarregado e canal de privacidade não comprovados

**Prioridade: alta — governança**

O frontend cita um encarregado e o endereço `privacidade@ilya.com`, mas o
repositório não comprova:

- ato formal de indicação;
- identidade e contato público;
- rotina de monitoramento;
- substituto e prazo interno;
- eventual enquadramento e decisão documentada de dispensa.

**Necessário:** formalizar a decisão conforme o porte e o enquadramento da
empresa, configurar o canal e publicar somente informações verdadeiras.

### LGPD-07 — Operadores e transferências internacionais não comprovados

**Prioridade: alta — terceiros**

O código prova uso de Vercel e Railway e permite object storage e webhooks. O
local físico dos dados, subprocessadores, contratos, DPA, medidas de segurança e
mecanismo de transferência internacional não podem ser confirmados pelo
repositório.

A Resolução CD/ANPD nº 19/2024 disciplina transferências internacionais e
cláusulas-padrão. Se os provedores tratarem dados fora do Brasil, a empresa deve
documentar hipótese e mecanismo válido.

**Necessário:**

- inventariar fornecedores e subprocessadores;
- obter DPA/termos e regiões efetivas;
- preencher avaliação de risco do fornecedor;
- incorporar mecanismo válido de transferência, quando aplicável;
- exigir notificação rápida de incidente e cooperação com direitos do titular;
- repetir a avaliação antes de ativar webhooks com dados pessoais.

### LGPD-08 — Auditoria de leitura e alterações cadastrais é insuficiente

**Prioridade: média-alta — prestação de contas**

Pedidos possuem histórico, mas não foi encontrada trilha estruturada e
protegida para:

- visualização/exportação de dados pessoais;
- criação, edição, anonimização e exclusão de representantes;
- edição de clientes;
- alterações administrativas de usuários e permissões;
- execução de pedidos de titulares;
- descarte por retenção.

Logs textuais ajudam na investigação, mas não substituem uma trilha de auditoria
com evento, autor, alvo, data, resultado, motivo e retenção.

**Necessário:** criar auditoria minimizada, protegida contra alteração, com
acesso restrito e prazo definido. Não gravar senha, token, assinatura ou payload
pessoal completo.

### LGPD-09 — Procedimento de incidente não atende integralmente à Resolução nº 15

**Prioridade: média-alta — resposta a incidentes**

O guia de infraestrutura possui seis passos úteis, mas não contém:

- critério formal de risco/dano relevante;
- controlador e responsáveis por decisão;
- contato de jurídico, DPO, provedores e comunicação;
- relógio regulatório;
- modelos de comunicação;
- registro de incidentes;
- evidência de comunicação aos titulares;
- prazo de **3 dias úteis** para ANPD e titulares quando aplicável;
- complementação fundamentada em até 20 dias úteis, quando necessária.

**Necessário:** criar playbook LGPD, tabela RACI e simulado periódico.

### LGPD-10 — Minimização de endereço e campos livres deve ser reavaliada

**Prioridade: média — necessidade**

Telefone, CEP, endereço, cidade e UF são obrigatórios já no cadastro usado para
orçamento. A finalidade declarada inclui logística e faturamento, mas esses
dados podem não ser necessários enquanto existe apenas uma cotação.

Representantes também possuem endereço completo obrigatório sem finalidade
detalhada na política. Campos livres podem receber dados excessivos.

**Necessário:** avaliar coleta progressiva (contato no orçamento; endereço
completo no fechamento/entrega), adicionar orientação para não inserir dados
sensíveis em observações e revisar a necessidade de cada campo.

### LGPD-11 — Assinaturas estão desativadas, mas o dado histórico continua ativo

**Prioridade: média — dado de alto impacto**

A feature flag impede novos fluxos e o frontend não persiste assinatura no
storage do navegador. Entretanto, as colunas `rep_signature` e
`client_signature` continuam armazenando imagens históricas em texto e não há
prazo de retenção, criptografia de campo ou rotina de descarte.

Mesmo sem classificar automaticamente toda assinatura como biometria, trata-se
de um identificador com alto potencial de fraude e deve receber proteção
reforçada.

**Necessário:** inventariar registros existentes, definir necessidade/prazo,
restringir acesso, considerar criptografia por campo ou storage privado e
eliminar com segurança quando a retenção terminar.

### LGPD-12 — Criptografia e residência dos dados em produção dependem de prova externa

**Prioridade: média — infraestrutura**

O código comprova HTTPS no desenho e criptografia dos backups. Não comprova:

- criptografia do PostgreSQL em repouso;
- criptografia e ACL do volume/object storage;
- região efetiva de banco, logs e backups;
- acesso de suporte dos provedores;
- política real de logs da Railway/Vercel;
- configuração real das variáveis e do Redis.

**Necessário:** guardar evidências do painel/contrato dos provedores e revisar
essas evidências ao menos anualmente.

## 5. Plano recomendado

### Fase 1 — 0 a 15 dias

1. Nomear responsável interno pela adequação e confirmar encarregado/dispensa.
2. Confirmar e testar o canal de privacidade.
3. Criar ROPA e matriz de bases legais.
4. Corrigir a política com identidade jurídica e fornecedores reais.
5. Aprovar uma matriz inicial de retenção.
6. Criar playbook de incidente com prazo de 3 dias úteis.
7. Revisar a necessidade do acesso da role `produtos`.
8. Corrigir o texto de exclusão de conta para não prometer eliminação total.

### Fase 2 — 15 a 45 dias

1. Exigir reautenticação em exclusão e anonimização.
2. Criar anonimização/atendimento para representantes.
3. Completar exportação e protocolo de solicitações.
4. Implementar trilha de auditoria para operações com dados pessoais.
5. Criar jobs de retenção para notificações, convites, outbox, logs e dados
   aprovados na matriz.
6. Revisar assinaturas históricas.
7. Implementar respostas minimizadas por role.

### Fase 3 — 45 a 90 dias

1. Formalizar DPA e subprocessadores de Vercel, Railway e storage.
2. Avaliar e documentar transferências internacionais.
3. Produzir RIPD, se a avaliação indicar alto risco, e mantê-lo revisado.
4. Fazer treinamento de usuários internos.
5. Executar exercício de incidente e solicitação de titular.
6. Criar revisão anual de acessos, fornecedores, retenção e política.

## 6. Separação entre código e responsabilidade da empresa

### Pode ser implementado no código

- reautenticação em ações irreversíveis;
- exportação mais completa;
- anonimização de representantes;
- respostas minimizadas por role;
- auditoria estruturada;
- jobs de retenção;
- limpeza de assinaturas e convites;
- avisos em campos livres;
- protocolos de solicitação;
- testes automatizados dos novos controles.

### Depende da empresa/jurídico/contabilidade

- razão social, CNPJ e endereço do controlador;
- nomeação ou dispensa formal do encarregado;
- existência e monitoramento do e-mail de privacidade;
- escolha e justificativa das bases legais;
- prazos fiscais e comerciais de retenção;
- necessidade real de cada campo e papel;
- contratos/DPA e regiões dos provedores;
- mecanismo de transferência internacional;
- decisão sobre RIPD;
- responsáveis e comunicações de incidente;
- treinamento, sanções internas e revisão periódica.

## 7. Critério para considerar o projeto saudável em LGPD

O projeto poderá ser considerado tecnicamente saudável para LGPD quando:

- o ROPA estiver aprovado e atualizado;
- toda finalidade tiver base legal, necessidade e retenção documentadas;
- a política refletir a operação real;
- todos os titulares tiverem fluxo equivalente e verificável de direitos;
- dados forem eliminados ou anonimizados ao fim do prazo;
- acessos forem mínimos, revisados e auditáveis;
- fornecedores e transferências estiverem contratualmente regularizados;
- incidentes puderem ser avaliados e comunicados dentro do prazo;
- houver evidência das decisões, testes e revisões.

## 8. Referências oficiais

- [Lei nº 13.709/2018 — LGPD](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)
- [ANPD — Comunicação de Incidente de Segurança](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis)
- [ANPD — Relatório de Impacto à Proteção de Dados Pessoais](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/relatorio-de-impacto-a-protecao-de-dados-pessoais-ripd)
- [ANPD — Transferência Internacional de Dados](https://www.gov.br/anpd/pt-br/assuntos/assuntos-internacionais/transferencia-internacional-de-dados)
- [Resolução CD/ANPD nº 19/2024](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-19-de-23-de-agosto-de-2024)
- [ANPD — Guia sobre atuação do encarregado](https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-lanca-guia-sobre-atuacao-do-encarregado)
- [ANPD — Guia de Segurança para Agentes de Pequeno Porte](https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-publica-guia-de-seguranca-para-agentes-de-tratamento-de-pequeno-porte)

---

**Parecer técnico resumido:** a aplicação não está “sem LGPD”; ela já possui
controles reais e úteis. O próximo salto de maturidade depende menos de adicionar
mais headers ou criptografia genérica e mais de provar, para cada dado, **por que
é coletado, quem acessa, com quem é compartilhado, por quanto tempo permanece e
como o titular exerce seus direitos**.

## 9. Atualização de implementação nesta branch

Após a análise inicial, foram implementadas as seguintes mitigações:

- LGPD-01/02/03/06/07/09: criada a estrutura documental em `docs/lgpd/`, com
  ROPA, política de retenção, matriz de acesso, encarregado, fornecedores e
  playbook de incidentes;
- LGPD-04: remoção de acesso e anonimização passaram a exigir senha atual;
- LGPD-04: representante passou a ter anonimização self-service equivalente à
  do cliente;
- LGPD-04: exportação foi ampliada para dados técnicos e ações associadas ao
  titular, sem exportar hashes de senha, hashes de token ou assinaturas;
- LGPD-05: acesso amplo de `produtos` foi formalmente justificado pelo
  responsável e sujeito a revisão trimestral;
- política pública e interface passaram a diferenciar remoção da conta de
  acesso, anonimização e retenção legal.
- criada a trilha persistente `privacy_events` para exportações, anonimizações
  e remoções de acesso, sem armazenar conteúdo exportado, senha ou token;
- incluída anonimização administrativa de representantes, equivalente ao fluxo
  já existente para clientes, desativando todas as contas ativas vinculadas;
- a exclusão automática por retenção permanece deliberadamente desativada até
  serem definidos legal hold, eventos de referência e prazos ainda pendentes.

As lacunas originais permanecem neste relatório como registro histórico. O
estado operacional corrente deve ser consultado em `docs/lgpd/README.md`.
