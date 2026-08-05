# Política de prazos auxiliares

**Versão:** 1.0 — aprovada para simulação não destrutiva
**Data:** 05/08/2026
**Responsável pela decisão:** Kaio Vinicius de Assis

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

## Prazos aprovados para inventário e simulação

| Categoria | Proposta inicial | Condição |
|---|---:|---|
| Notificação lida | 90 dias após leitura | preservar apenas enquanto útil ao usuário |
| Notificação não lida | 365 dias após criação | revisar notificações vinculadas a disputa/garantia |
| Convite de assinatura expirado, consumido ou revogado | 30 dias após o último marco | pedido e assinatura seguem sua própria retenção |
| Outbox entregue | 90 dias após entrega | preservar somente métricas agregadas |
| Outbox em `dead_letter` | 180 dias após resolução documentada | nunca apagar pendente, `processing` ou falha não resolvida |
| Evento de operação de privacidade (`privacy_events`) | 5 anos | validar com jurídico; conteúdo já é minimizado |
| Log de aplicação/segurança além do registro obrigatório | 180 dias | ampliar sob incidente, ordem ou legal hold |

## Registro da decisão

- [x] Notificações: 90 dias após leitura e 365 dias se não lidas.
- [x] Convites de assinatura: 30 dias após o último marco.
- [x] Outbox entregue: 90 dias; `dead_letter` exige resolução manual.
- [x] Eventos de privacidade: 5 anos e revisão manual.
- [ ] Confirmar política de logs no Railway e Vercel.
- [ ] Confirmar o enquadramento do art. 15 do Marco Civil.

Os prazos aprovados foram implementados no `dry-run` administrativo. A
aprovação não autoriza descarte automático. Logs dependem de contrato,
configuração dos provedores e validação jurídica externa.
