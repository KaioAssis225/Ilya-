# Implantação segura do Projeto Ilya

## E-mail do PDF do pedido

A publicação do backend mantém esta integração inerte enquanto
`ORDER_EMAIL_MODE` não for configurado. Variáveis previstas, todas somente no
ambiente (nunca grave os valores no repositório):

```dotenv
# ORDER_EMAIL_MODE=
# ORDER_EMAIL_TEST_ALLOWLIST=
# RESEND_API_KEY=
# RESEND_API_BASE_URL=
# RESEND_WEBHOOK_SECRET=
# ORDER_EMAIL_FROM=
# ORDER_EMAIL_REPLY_TO=
# ORDER_EMAIL_TIMEOUT_SECONDS=
# ORDER_EMAIL_POLL_SECONDS=
# ORDER_EMAIL_LOCAL_DIR=
```

O worker é um processo separado (`python -m app.workers.order_email_sender`);
o processo web não consome esta fila. Em produção os PDFs exigem o bucket do
mercado correspondente, e o diretório local serve apenas a desenvolvimento e
testes.

Este documento define o processo mínimo para publicar mudanças sem repetir a indisponibilidade ocorrida em 17 de julho de 2026.

## Base validada

- Referência local: `production-stable-2026-07-20`
- Commit correspondente: `013e459`
- O conteúdo desse commit é igual ao estado corrigido de `33314ed`.
- Em 20 de julho de 2026, o frontend público, `/health`, `/health/live` e `/health/ready` responderam com sucesso.

A tag é uma referência local e não deve ser enviada ao remoto sem uma decisão explícita de publicação.

## Falhas identificadas no incidente

1. O primeiro pacote de escala executava `seed_admin.py` obrigatoriamente. Sem as variáveis opcionais do administrador, o processo encerrava antes de iniciar a API. Isso foi corrigido em `33314ed`.
2. O teste posterior em banco vazio revelou um segundo risco: a conexão que mantinha o advisory lock ficava com uma transação aberta, enquanto `CREATE INDEX CONCURRENTLY` esperava essa transação terminar. A API e a migration aguardavam uma à outra indefinidamente.
3. A conexão de lock agora usa `AUTOCOMMIT`, preservando a exclusão mútua sem manter snapshot/transação aberta.
4. O workflow `Quality Gate` inicia a imagem de produção contra PostgreSQL temporário e exige `/health/ready`, impedindo a repetição dessas falhas em pull requests futuros.

## Regra principal

Banco, inicialização do servidor, backend e frontend não devem ser alterados no mesmo deploy. Cada etapa precisa passar pela homologação e possuir uma forma de reversão antes de seguir para produção.

## Fluxo obrigatório

1. Criar uma branch a partir da última versão comprovadamente estável.
2. Trabalhar em uma única categoria de mudança por vez.
3. Abrir pull request e aguardar o workflow `Quality Gate` concluir com sucesso.
4. Publicar primeiro em homologação.
5. Testar login, permissões, cadastros, orçamento, pedidos, PDF e upload.
6. Fazer backup e testar a leitura do arquivo antes de migrations de produção.
7. Publicar uma única etapa e acompanhar saúde, logs e tempo de resposta.
8. Somente iniciar a etapa seguinte após um período estável.

## Migrations

- Executar previamente em um banco temporário criado do zero.
- Executar também sobre uma cópia anonimizada da produção.
- Rodar consultas de pré-verificação de duplicidades e dados incompatíveis.
- Preferir migrations aditivas e compatíveis com a versão anterior da API.
- Não aplicar downgrade automático em produção.
- Não criar usuário administrador durante o boot da aplicação.
- Antes de múltiplas réplicas, mover migrations para uma tarefa exclusiva de implantação.

O código aceita três modos de inicialização:

- `python startup.py`: fluxo legado, migra e depois inicia a API.
- `python startup.py migrate`: executa somente migrations, sem alterar usuários.
- `python startup.py serve`: inicia somente a API.

O modo legado permanece como padrão para não modificar a produção por acidente. Antes da expansão horizontal, configurar uma tarefa exclusiva com `python startup.py migrate`, validar sua conclusão e somente então configurar o serviço web com `python startup.py serve`.

## Critérios para liberar produção

- Frontend: lint e build aprovados.
- Backend: todos os testes aprovados.
- Container: imagem de produção construída e inicialização validada sem variáveis opcionais de administrador.
- Banco: migrations aprovadas em banco temporário e homologação.
- Segurança: nenhum segredo incluído no commit.
- Operação: backup recente, rollback definido e pessoa responsável acompanhando o deploy.

## Verificação depois do deploy

- `/health/live` deve responder imediatamente.
- `/health/ready` deve confirmar banco e dependências.
- Login deve funcionar para administrador, cadastros, produtos, representante e cliente.
- Criar um pedido de teste e abrir o PDF.
- Conferir erros 5xx, tempo de resposta e uso de conexões do PostgreSQL.

## Corte BR/EU

Para a entrega multimercado, manter `EUROPE_MARKET_ENABLED=false` e
`markets.EU.is_enabled=false` durante a publicação. Após backup e ensaio em uma
cópia anonimizada, aplicar a cadeia até `catalog_dimensions_r6_20261002` e só
então publicar o backend e o frontend compatíveis.

Antes de habilitar EU, verificar pela sessão própria de plataforma:

- a conta inicial possui `platform_admin` e `activate_market`;
- clientes e representantes EU ativos pertencem a Portugal;
- cada produto disponível pertence fisicamente a EU e referencia somente
  catálogo, tipo, categorias e opcionais EU;
- cada produto disponível possui Lojista, Corporativo e PVP em EUR;
- o IVA de cada produto foi aprovado nominalmente;
- foto sem assinatura recebe 403 e a URL assinada abre no catálogo e no PDF;
- login, orçamento, pedido e PDF funcionam em pt-PT e EUR.

O endpoint de ativação repete as validações persistidas. Valores, SKUs e taxas
concretas são cadastrados e revisados manualmente; a migration não cria itens EU.

## Reversão

- Frontend: restaurar o deployment anterior na Vercel.
- Backend: voltar ao último commit compatível com o estado atual do banco.
- Banco: não reverter migrations destrutivamente durante uma emergência; interromper gravações e restaurar o backup quando necessário.
- Após a reversão, registrar o motivo e reproduzir a falha em homologação antes de tentar novamente.


## Separação entre Migration de Pré-Deploy e Processo Web — P16

O Bloco P16 separa explicitamente a execução de migrations do start do processo web, eliminando a reexecução de Alembic e de `seed_admin.py` em restarts e réplicas horizontais.

### Estado de preparação no repositório (concluído localmente na branch)

- `backend/railway.json` mantém:
  - `"preDeployCommand": ["runuser -u ilya -- python startup.py migrate"]`
  - `"healthcheckPath": "/health/ready"`
- `backend/Dockerfile.prod` passa a definir:
  - `CMD ["python", "startup.py", "serve"]`

Com isso, o `preDeployCommand` é o **único** ponto que executa migrations no deploy, e o container web (incluindo restarts de worker e réplicas horizontais) apenas inicia o Uvicorn via `serve`, sem rodar Alembic nem `seed_admin.py`.

### Aceite operacional na Railway (pendente de conferência humana)

O estado acima está **preparado no repositório**, mas o aceite operacional na Railway **ainda está pendente** e exige conferência humana no painel, cobrindo no mínimo:

- **Start Command efetivo** do serviço web (se o painel sobrescrever o `CMD` do `Dockerfile.prod`, deve refletir `python startup.py serve`, não `all`).
- **Janela de mudança** acordada para a publicação.
- **Responsável de rollback** nomeado e disponível durante a janela.

Sem esse aceite registrado, o deploy em produção não deve ser liberado.

### Roteiro de Homologação (5 ensaios obrigatórios antes de produção)

1. **Ensaio 1 — Deploy sem migration nova**
   Verificar que o `preDeployCommand` roda **uma única vez** e que o container web sobe em modo `serve`.

2. **Ensaio 2 — Deploy com migration aditiva compatível**
   Medir e registrar o tempo entre o início do deploy e `/health/ready` retornando 200.

3. **Ensaio 3 — Reinício do processo web**
   Confirmar nos logs que **nenhuma migration é executada** no restart do worker.

4. **Ensaio 4 — Duas réplicas iniciando próximas**
   Confirmar ausência de **lock contention de DDL** no boot web (as réplicas apenas sobem `serve`).

5. **Ensaio 5 — Falha simulada de migration no pre-deploy e rollback**
   Confirmar que a falha no `preDeployCommand` **aborta a publicação da nova versão** e **preserva a versão anterior saudável**; em seguida, executar rollback para a imagem anterior compatível.

### Procedimento de Rollback de P16

- **No painel/serviço (Railway):**
  - Restaurar a imagem/deployment anterior; **ou**
  - Definir temporariamente o Start Command explícito `python startup.py all`, caso o `preDeployCommand` esteja desabilitado no ambiente.
- **No repositório:**
  - Reverter `CMD ["python", "startup.py", "serve"]` para `CMD ["python", "startup.py"]` em `backend/Dockerfile.prod`.
- **Nunca** executar `alembic downgrade` automático em produção.
