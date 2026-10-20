# P12 — baseline autenticado BR/EU

**Estado:** ferramenta e roteiro em preparação; **nenhum baseline medido**. Este
documento é o modelo para a execução posterior em homologação. Não contém
resultados reais nem altera metas de deploy.

## Pré-condições de execução

1. Concluir o gate focado de P11: aplicar a migration em banco descartável,
   verificar autorização de leitura/mutação, revogação e sigilo. Provisionar uma
   identidade `benchmark_readonly` exclusiva para BR e outra para EU no secret
   manager da homologação. Nunca usar conta humana ou de produção.
2. Registrar commit, versão do backend, configuração de workers/pool, classe de
   PostgreSQL/Redis, volume e perfil dos dados sintéticos, estado do cache,
   quantidade de réplicas, rota de rede, fuso e carga externa observada. Se a
   homologação não for representativa, declarar quais comparações ficam inválidas.
3. Fixar um conjunto de dados estável durante a leitura paginada. Definir sete
   janelas em horários distintos e registrar UTC de início e fim de cada uma.
   Mudança de versão ou de volume entre janelas exige nova série, sem misturar
   percentis de configurações diferentes.
4. Autorizar separadamente a comparação por Vercel rewrite. Sem essa autorização,
   medir apenas Railway direto. Para comparação, usar as duas origens na mesma
   janela, com mesmo cenário, mercado, versão e aquecimento.

## Execução por janela

Executar o comando abaixo **duas vezes**, uma para cada mercado, com variáveis
fornecidas pelo secret manager. O arquivo de saída deve ficar fora do Git, em
armazenamento controlado. O login e a verificação de `/auth/me` acontecem antes
das amostras comerciais; a latência do login não compõe seus percentis.

```text
BENCHMARK_TARGET_URL=<origem HTTPS da homologação>
BENCHMARK_VERCEL_URL=<origem HTTPS autorizada, opcional>
BENCHMARK_ENVIRONMENT=homologacao
ILYA_BENCHMARK_USERNAME=<identidade do mercado>
ILYA_BENCHMARK_PASSWORD=<segredo injetado>
ILYA_BENCHMARK_MARKET=BR ou EU
python ops/benchmark_production_api.py --mode baseline --commercial --output <artefato privado>.json
```

O modo `baseline` faz cinco warmups por cenário/origem e tenta obter 30
respostas válidas por cenário/origem. Exigir `expected_status=200` nos cenários
comerciais. Conferir `valid_count >= 30`, `auth_failure_count=0`,
`unexpected_status_count=0` e o código de saída. O número de tentativas pode
exceder 30; preservar os contadores de 4xx, 5xx, timeout e rede. `p95` e `p99`
com menos de 30 respostas válidas são **INCONCLUSIVOS**; 30 é mínimo operacional,
não intervalo de confiança suficiente para aprovar SLO. Reportar a série por
cenário, mercado, origem e janela, sem juntar amostras de contextos diferentes.

## Catálogo e lacunas verificadas no código

| Família | Contrato real | Cobertura automatizada atual | Lacuna para o baseline completo |
|---|---|---|---|
| Produtos | `GET /api/v1/products`: `limit` 1–1000, `include_total` booleano, `skip`, `q`, `type`, `group_id`, `catalog_id`, ordenação | Primeira página `limit=20` com `include_total=false` e `true`; detalhe opcional por código sintético | `limit=100/1000`, busca exata/parcial, tipo/grupo/catálogo, ordenações e página profunda dependem de fixtures e cenários adicionais. `POST /products/batch` é escrita HTTP, embora apenas leia dados; o canário P11 bloqueia POST. |
| Pedidos | `GET /api/v1/orders`: `limit` 1–100, `cursor`, filtros; resposta usa `X-Next-Cursor` e `X-Has-More` | Primeira página `limit=20`; detalhe opcional por código sintético | Página seguinte e prova de IDs sem repetição/omissão exigem captura do cursor e conjunto estável; buscas, filtros e histórico não estão no catálogo. O papel P11 não autoriza `/orders/history`. |
| Dashboard | `GET /api/v1/dashboard/overview`: datas, `rep_id`, `region`, `ranking_limit` 5–500 | Janela padrão de 30 dias, `ranking_limit=5` | Janelas 180/365 dias, filtros e ranking máximo exigem datas/fixtures controladas. |
| Diretórios | `GET /clients`, `/representatives`, `/catalogs`, `/product-types`, `/product-groups`, `/optionals` | Nenhum | O canário P11 só autoriza GET de produtos, pedidos, dashboard e `/auth/me`. `require_directory_access` também exclui `benchmark_readonly`. **Não tentar com outro papel**: acordar um modo de leitura sintética restrita antes de medir diretórios. |

Um HTTP 200 isolado não prova contrato. Na execução completa, validar forma
mínima (`list` nas listagens; em pedidos `id`, `code`, `created_at`), quantidade
de itens e cabeçalhos técnicos. Para cursor, comparar as páginas por IDs apenas
em memória: sem duplicatas, ordenação monotônica e, com conjunto congelado,
sem lacunas frente ao inventário de referência. Persistir somente contagens e
resultado da verificação; não registrar IDs ou corpos.

## Modelo de relatório por janela e cenário

Preencher uma linha por mercado, origem, janela e cenário; anexar o JSON bruto
sanitizado da ferramenta em armazenamento privado. Campos não instrumentados
ficam `não medido`, nunca zero. `throughput` do modo sequencial é taxa observada
na janela, **não** capacidade de carga (P13). Correlacionar `queries/request`
com métricas de P10 pelo template de rota e versão; sem coletor, marcar ausente.

| Janela UTC | Mercado | Origem | Cenário/template | Commit/versão | Válidas/tentativas | p50/p95/p99/máx. ms | 4xx/5xx/auth/rede/timeout | RPS observado | Payload comprimido/descomprimido B | Queries/request | Limitações |
|---|---|---|---|---|---:|---|---|---:|---|---:|---|
| E1 — preencher | BR/EU | Railway/Vercel | preencher | preencher | preencher | preencher ou INCONCLUSIVO | preencher | não medido | não medido | não medido | preencher |

Resumo da série: E1, E2, E3, E4, E5, E6 e E7 com horários distintos, mesmo
contrato e metadados comparáveis. Se houver 429 ou limite da identidade, reportar
como erro e interromper a série para diagnóstico; não tratá-lo como latência
comercial normal. Metas provisórias de p95 (<500 ms diretórios, <800 ms listas,
<1500 ms dashboard) são somente observação até análise e aprovação humana.

## Sigilo e armazenamento

- Nunca colocar URL privada, senha, bearer, cookie, CPF/CNPJ, e-mail, telefone,
  nomes, código identificador de cliente, corpo de pedido ou UUID em relatório,
  commit, prompt ou log. Quando precisar comparar corpos, calcular hash
  normalizado e tamanho **em memória**; armazenar somente o resumo sem payload.
- Não versionar relatórios reais. Revisar artefatos e logs sanitizados antes de
  enviar ao bucket controlado, com acesso e retenção definidos pelo responsável.
- Revogar as contas se a execução deixar de ser necessária ou houver suspeita
  de vazamento. A execução deste bloco não cria contas nem aplica migrations.

## Aceite empírico pendente

P12 só muda para concluído quando houver sete relatórios reais comparáveis,
BR/EU, ao menos 30 amostras 200 por cenário principal/origem, validação de
contrato/cursor, erro, payload, taxa, SQL e metadados de ambiente. As lacunas
de autorização e instrumentação acima precisam ser resolvidas antes desse aceite.
