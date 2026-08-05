# Proposta de prazos auxiliares

**Versão:** 0.1 — proposta para decisão
**Data:** 05/08/2026

## Limite desta proposta

A LGPD não fixa um prazo geral para todos os dados. A ANPD esclarece que o prazo
depende da finalidade e da situação concreta; terminado o tratamento, a
eliminação é a regra, ressalvadas as hipóteses do art. 16. Portanto, os valores
abaixo não foram ativados como exclusão automática.

Referências oficiais:

- [LGPD, arts. 15 e 16](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm);
- [Perguntas frequentes da ANPD — prazo de tratamento](https://www.gov.br/anpd/pt-br/acesso-a-informacao/perguntas-frequentes/perguntas-frequentes);
- [Marco Civil da Internet, art. 15](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm);
- [Comunicação de incidente — ANPD](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis).

## Prazos legalmente identificados

| Categoria | Prazo | Estado no Ilya |
|---|---:|---|
| Registro de incidente com dados pessoais | mínimo de 5 anos a partir do registro | implementado; sem exclusão |
| Registro de acesso à aplicação, quando o art. 15 do Marco Civil for aplicável | 6 meses, sob sigilo e segurança | confirmar cobertura e exportação no Railway/Vercel |

Logs técnicos gerais não são automaticamente iguais ao “registro de acesso à
aplicação”, que envolve data/hora de uso e endereço IP. A empresa deve confirmar
com assessoria jurídica se o Ilya se enquadra no art. 15 e se os provedores
contratados entregam a guarda necessária.

## Recomendação técnica sujeita a aprovação

| Categoria | Proposta inicial | Condição |
|---|---:|---|
| Notificação lida | 90 dias após leitura | preservar apenas enquanto útil ao usuário |
| Notificação não lida | 365 dias após criação | revisar notificações vinculadas a disputa/garantia |
| Convite de assinatura expirado, consumido ou revogado | 30 dias após o último marco | pedido e assinatura seguem sua própria retenção |
| Outbox entregue | 90 dias após entrega | preservar somente métricas agregadas |
| Outbox em `dead_letter` | 180 dias após resolução documentada | nunca apagar pendente, `processing` ou falha não resolvida |
| Evento de operação de privacidade (`privacy_events`) | 5 anos | validar com jurídico; conteúdo já é minimizado |
| Log de aplicação/segurança além do registro obrigatório | 180 dias | ampliar sob incidente, ordem ou legal hold |

## Decisões necessárias

- [ ] Aprovar ou ajustar notificações.
- [ ] Aprovar ou ajustar convites de assinatura.
- [ ] Aprovar ou ajustar outbox/webhooks.
- [ ] Aprovar ou ajustar eventos de privacidade.
- [ ] Confirmar política de logs no Railway e Vercel.
- [ ] Confirmar o enquadramento do art. 15 do Marco Civil.

Até essas decisões serem registradas, nenhum job novo de descarte deve ser
habilitado. A próxima implementação segura é um inventário não destrutivo por
categoria, seguido de simulação e aprovação separada.
