# Operação segura de retenção e legal hold

**Versão:** 0.1 — fundação não destrutiva
**Data:** 05/08/2026

## Objetivo

Permitir que o administrador identifique registros que alcançaram os prazos da
matriz de retenção, bloqueie casos que precisam ser preservados e aprove um
relatório. Esta versão **não exclui nem anonimiza registros automaticamente**.

## Legal hold

Um legal hold suspende o descarte por disputa, cobrança, garantia,
fiscalização, investigação ou obrigação legal. Pode ser aplicado a:

- cliente;
- representante;
- pedido/orçamento.

Um hold de cliente ou representante também bloqueia os pedidos vinculados. A
criação registra motivo, responsável, data e expiração opcional. A liberação
exige senha atual do administrador e justificativa.

O motivo deve ser objetivo. Não copiar documentos, senhas, dados de saúde ou
outros dados pessoais desnecessários para o campo livre.

## Simulação (`dry-run`)

O endpoint administrativo `POST /api/v1/privacy/retention-reviews/dry-run`
gera uma fotografia auditável:

| Categoria | Prazo | Referência provisória | Ação apenas proposta |
|---|---:|---|---|
| Cliente sem pedido | 730 dias | `clients.updated_at` | excluir se continuar sem vínculo |
| Orçamento/pedido aberto | 730 dias | `orders.updated_at` | revisão manual |
| Pedido finalizado/cancelado | 3.650 dias | `orders.updated_at` | anonimizar após revisão |
| Representante | 5 anos após encerramento | indisponível | não avaliado |

`updated_at` é uma aproximação conservadora enquanto não existem
`last_activity_at`, `finalized_at`, `cancelled_at` e
`relationship_ended_at`. O relatório declara essa limitação.

Legal holds ativos são excluídos da lista de candidatos e contabilizados
separadamente. Holds de cliente/representante são herdados pelos pedidos.

## Aprovação

O administrador pode aprovar uma fotografia mediante confirmação da senha. A
aprovação:

- registra autor, data, política, quantidade e identificador de correlação;
- não executa descarte;
- é recusada quando a fotografia excede 5.000 candidatos e foi truncada;
- não substitui a revalidação de legal hold e elegibilidade no futuro.

Não existe endpoint de `execute` nem método `DELETE` no módulo de retenção.

## Interface administrativa

A seção **Admin → Governança de retenção** permite:

- gerar a simulação completa;
- comparar registros vencidos, bloqueados e candidatos por categoria;
- consultar até os 100 primeiros candidatos da fotografia na tela;
- criar um legal hold diretamente a partir de um candidato;
- consultar e liberar holds ativos;
- aprovar o relatório mediante senha atual.

A interface repete de forma explícita que aprovação não executa descarte e não
apresenta botões de exclusão ou execução no painel de retenção.

## Próximos requisitos antes de qualquer descarte

1. Criar timestamps canônicos para atividade e encerramento.
2. Definir os prazos ainda pendentes na matriz.
3. Paginar candidatos em tabela própria para volumes acima de 5.000.
4. Implementar dupla confirmação e revalidação transacional.
5. Criar modo canário com limite pequeno e rollback lógico.
6. Validar restauração de backup sem reintrodução operacional.
7. Autorizar cada categoria separadamente após revisão jurídica/contábil.
