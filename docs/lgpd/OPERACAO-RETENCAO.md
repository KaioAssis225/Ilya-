# Operação segura de retenção e legal hold

**Versão:** 0.2 — marcos canônicos não destrutivos
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

| Categoria | Prazo | Referência canônica | Ação apenas proposta |
|---|---:|---|---|
| Cliente sem pedido | 730 dias | `clients.last_activity_at` | excluir se continuar sem vínculo |
| Orçamento/pedido aberto | 730 dias | `orders.updated_at` | revisão manual |
| Pedido finalizado/cancelado | 3.650 dias | `orders.finalized_at` ou `orders.cancelled_at` | anonimizar após revisão |
| Representante | 5 anos após encerramento | `representatives.relationship_ended_at` | anonimizar após revisão |
| Notificação lida | 90 dias | `notifications.read_at` | excluir após revisão |
| Notificação não lida | 365 dias | `notifications.created_at` | excluir após revisão |
| Convite de assinatura | 30 dias | maior marco entre expiração, consumo e revogação | remover metadados após revisão |
| Webhook entregue | 90 dias | `integration_outbox.delivered_at` | remover payload e preservar métrica |
| Webhook em `dead_letter` | até resolução | `integration_outbox.dead_lettered_at` | resolver manualmente; nunca excluir automaticamente |
| Evento de privacidade | 5 anos | `privacy_events.created_at` | revisão manual antes de minimizar |

Os registros históricos recebem backfill conservador a partir de `updated_at`
ou `created_at`. Novas operações passam a registrar os marcos no momento em que
ocorrem. A data de atividade do cliente é renovada quando seu cadastro ou pedido
é criado/alterado, finalizado, cancelado, notificado ou assinado.

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
- encerrar o vínculo de um representante mediante senha e justificativa,
  registrando o marco de retenção e revogando suas sessões ativas.

A interface repete de forma explícita que aprovação não executa descarte e não
apresenta botões de exclusão ou execução no painel de retenção.

## Próximos requisitos antes de qualquer descarte

Não há execução destrutiva nesta versão. Caso a empresa decida implementá-la,
serão requisitos obrigatórios:

1. paginar candidatos em tabela própria para volumes acima de 5.000;
2. dupla confirmação e revalidação transacional;
3. modo canário com limite pequeno e rollback lógico;
4. validação de restauração sem reintrodução operacional;
5. autorização separada de cada categoria após revisão jurídica/contábil.
