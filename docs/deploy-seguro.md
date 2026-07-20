# Implantação segura do Projeto Ilya

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

Enquanto `startup.py` executar migrations antes do servidor, qualquer falha de banco ainda poderá impedir o backend de iniciar. Por isso essa mudança deve ocorrer antes da expansão horizontal.

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

## Reversão

- Frontend: restaurar o deployment anterior na Vercel.
- Backend: voltar ao último commit compatível com o estado atual do banco.
- Banco: não reverter migrations destrutivamente durante uma emergência; interromper gravações e restaurar o backup quando necessário.
- Após a reversão, registrar o motivo e reproduzir a falha em homologação antes de tentar novamente.
