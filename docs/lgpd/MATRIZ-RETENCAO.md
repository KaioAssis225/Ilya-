# Matriz inicial de retenção e descarte

**Versão:** 1.0 — política aprovada
**Data:** 05/08/2026

Os prazos abaixo foram aprovados pelo responsável da Ilya em 05/08/2026. Eles
não substituem prazo legal específico mais longo nem impedem revisão por
jurídico/contabilidade. Em caso de disputa, cobrança, garantia, fiscalização,
investigação ou obrigação legal, aplica-se legal hold até o encerramento.

| ID | Categoria | Regra atual comprovada | Regra-alvo | Forma de término | Aprovação |
|---|---|---|---|---|---|
| RET-01 | Cliente sem pedido | sem expiração automática | 2 anos após o último contato ou atividade registrada | excluir se não houver vínculo; anonimizar se houver referência que precise ser preservada | Aprovado |
| RET-02 | Representante | sem expiração automática | durante a relação com a Ilya e por 5 anos após o encerramento | anonimizar ou excluir quando não houver vínculos/obrigação | Aprovado |
| RET-03 | Usuário ativo | enquanto conta existir | duração do vínculo e encerramento do acesso | excluir credencial; anonimizar vínculos quando permitido | RH/Comercial + Jurídico |
| RET-04 | Refresh tokens | TTL de 7 dias; evidência técnica de tokens expirados/revogados por 30 dias | manter configuração atual, revisada anualmente | job de limpeza já existente | Segurança |
| RET-05 | Orçamento não convertido | sem expiração automática | 2 anos após a última atualização | excluir/anonimizar dados pessoais e preservar somente métrica agregada | Aprovado |
| RET-06 | Pedido finalizado ou cancelado, itens e snapshots | sem expiração automática | 10 anos após finalização/cancelamento | anonimizar dados pessoais; preservar somente o mínimo necessário para histórico e obrigação aplicável | Aprovado |
| RET-06A | Histórico do pedido | acompanha o pedido, sem prazo próprio | mesmo prazo de 10 anos do pedido | anonimizar o autor e detalhes pessoais ao término | Aprovado |
| RET-07 | Notificações | marco `read_at` implementado | 90 dias após leitura; 365 dias após criação quando não lida | simulação; descarte somente após revisão | Aprovado |
| RET-08 | Solicitações de titular | operações técnicas geram trilha estruturada em `privacy_events` | 5 anos após o evento | revisão e minimização manual | Aprovado |
| RET-08A | Registro de incidentes com dados pessoais | cadastro estruturado administrativo | mínimo de 5 anos contados do registro | reavaliar ao fim do prazo; legal hold e obrigação adicional prevalecem | Obrigação regulatória |
| RET-09 | Assinaturas e convites | assinatura histórica acompanha o pedido; convite expira em 10 min | assinatura acompanha o pedido por até 10 anos; metadados do convite por 30 dias após expiração/consumo/revogação | simulação; apagar metadados somente após revisão | Aprovado |
| RET-10 | Logs | depende do provedor/máquina | 6 meses para registro de acesso quando aplicável; 180 dias propostos para logs técnicos | confirmar cobertura e rotação nos provedores | Pendente externo |
| RET-11 | Backups | 7 diários, 4 semanais, 6 mensais; criptografados | manter GFS atual, confirmar se 6 meses atende obrigações e risco | expiração automática local e off-site; registrar destruição | Infra + Jurídico |
| RET-12 | Outbox/webhooks | `delivered_at` e `dead_lettered_at` implementados | entregues por 90 dias; `dead_letter` até resolução manual | simular remoção do payload entregue; nunca eliminar falha não resolvida | Aprovado |
| RET-13 | Arquivos/imagens de produto | sem descarte de órfãos comprovado | enquanto produto estiver ativo e janela curta após substituição | job de órfãos e exclusão no storage | Produto + Infra |

## Regras de implementação

1. Nenhum job deve excluir dados fora da regra aprovada na linha correspondente.
2. Jobs devem ser idempotentes, paginados e executados fora do horário crítico.
3. Toda execução deve registrar categoria, período, quantidade, resultado e
   identificador de correlação, sem copiar o conteúdo pessoal descartado.
4. Legal hold deve suspender o descarte do registro afetado.
5. A eliminação deve alcançar banco, arquivos, caches e operadores. Backups
   imutáveis podem expirar pelo ciclo normal, sem serem restaurados para uso
   corrente do dado eliminado.
6. O responsável deve testar restauração sem reintroduzir dados já eliminados
   em produção.
7. A matriz deve ser revisada no mínimo anualmente.
8. A aprovação de um relatório `dry-run` não autoriza descarte automático; a
   elegibilidade e os legal holds devem ser revalidados na mesma transação de
   uma futura execução.
9. **Exclusão manual de pedido pelo administrador** (`DELETE /orders/{id}`,
   reaberta em 13/08/2026 por decisão do Alto Comando): é a única via de
   eliminação fora dos jobs. Não é automática — depende de ação humana
   deliberada com papel `admin` — e emite `order.deleted` na outbox, para que
   consumidores externos não fiquem com projeção órfã. Fica registrada aqui
   porque **conflita com RET-06** quando aplicada a pedido finalizado ou
   cancelado, cuja guarda prevista é de 10 anos: nesses casos o caminho
   correto continua sendo cancelar, e o uso da exclusão deve ser restrito a
   registros sem valor fiscal (testes, duplicidades, lançamentos errados).
   Cada exclusão é registrada em log com o pedido e o autor.

## Pendências antes de liberar os jobs

- prazo de logs no Railway/Vercel;
- confirmação de expiração dos arquivos na cópia off-site.

Os marcos canônicos de atividade do cliente, encerramento do representante e
finalização/cancelamento do pedido já estão registrados pelo sistema. Os jobs
de descarte continuam proibidos até a definição de:

- como anonimizar sem quebrar chaves e histórico;
- como impedir que restauração de backup reintroduza dado já eliminado.
