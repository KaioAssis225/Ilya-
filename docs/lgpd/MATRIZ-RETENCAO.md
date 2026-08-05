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
| RET-07 | Notificações | sem expiração automática | curto prazo após leitura ou encerramento do evento, a definir | exclusão automatizada | Produto + Jurídico |
| RET-08 | Solicitações de titular | operações técnicas passam a gerar trilha estruturada em `privacy_events` | prazo suficiente para provar atendimento, ainda a definir | anonimização ou descarte seguro após prazo | Prazo pendente |
| RET-09 | Assinaturas e convites | assinatura histórica sem prazo; convite expira em 10 min, mas linha permanece | assinatura acompanha o pedido por até 10 anos; prazo técnico da linha de convite ainda a definir | apagar imagem/hash/convite ao fim do prazo e revogar imediatamente quando necessário | Assinatura aprovada; convite pendente |
| RET-10 | Logs | depende do provedor/máquina | prazo curto proporcional ao risco; diferenciar segurança, aplicação e backup | rotação e eliminação automatizadas | Segurança + DPO |
| RET-11 | Backups | 7 diários, 4 semanais, 6 mensais; criptografados | manter GFS atual, confirmar se 6 meses atende obrigações e risco | expiração automática local e off-site; registrar destruição | Infra + Jurídico |
| RET-12 | Outbox/webhooks | sem expiração automática | pendentes até resolução; entregues por prazo técnico curto; dead letter revisada | apagar payload e preservar métrica agregada | Integrações + DPO |
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

## Pendências antes de liberar os jobs

- prazo de notificações;
- prazo de logs no Railway/Vercel;
- prazo de eventos entregues/dead letter;
- prazo da trilha de solicitações/operações de privacidade;
- confirmação de expiração dos arquivos na cópia off-site.

Os jobs de clientes, representantes, orçamentos, pedidos e assinaturas só devem
ser criados na fase de implementação após definição de:

- qual evento/timestamp representa “último contato” e “encerramento”;
- como registrar legal hold;
- como anonimizar sem quebrar chaves e histórico;
- como impedir que restauração de backup reintroduza dado já eliminado.
