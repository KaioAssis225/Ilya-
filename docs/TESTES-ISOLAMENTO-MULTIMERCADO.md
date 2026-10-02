# Matriz negativa de isolamento BR/EU

Esta matriz define os casos que devem permanecer bloqueados ao evoluir schema,
API, interface e PDF. EU é o mercado comercial; nesta liberação, o único país
aceito é PT.

## Sessão e autoridade

| ID | Preparação | Ação proibida | Resultado esperado |
|---|---|---|---|
| ISO-01 | Identidade com vínculo ativo somente em BR | Trocar a sessão para EU | 403; nenhum token EU é emitido. |
| ISO-02 | Identidade com vínculo ativo somente em EU | Consultar rota comercial BR | 403; nenhuma linha BR é retornada. |
| ISO-03 | Mesma identidade com papel vendedor em BR e representante em EU | Usar o token BR numa rota EU, ou conservar o papel BR após a troca | 401/403; o novo token leva o papel do vínculo EU. |
| ISO-04 | Identidade somente de plataforma | Entrar na aplicação comercial ou selecionar BR/EU | 403; a sessão de plataforma continua sem mercado. |
| ISO-05 | Administrador comercial sem capacidade de plataforma | Ativar mercado, gerir capacidades globais ou consultar a outbox global | 403. |
| ISO-06 | Capacidade ou vínculo revogado depois do login | Renovar a sessão anterior | 401/403; a família comercial correspondente é revogada. |

## Cadastros e carteira

| ID | Preparação | Ação proibida | Resultado esperado |
|---|---|---|---|
| ISO-10 | Conta de cliente legada com espelhos globais, sem user_markets ativo | Ler ou criar pedido em qualquer mercado | 403; users.role, home_market e linked_id não concedem acesso. |
| ISO-11 | Representante BR A e cliente BR do representante B | A consultar, alterar ou criar pedido para o cliente de B | 403 ou 404, sem revelar a existência fora da carteira. |
| ISO-12 | UUID de cliente/representante EU conhecido numa sessão BR | Abrir detalhe pelo UUID | 404. |
| ISO-13 | Cadastro EU com country diferente de PT | Criar/alterar cliente, representante ou pedido | 422 enquanto EU_LAUNCH_COUNTRY=PT. |
| ISO-14 | Identidade com papéis diferentes em BR e EU | Alterar vínculo BR e observar o vínculo EU | O registro EU permanece inalterado e a sessão de plataforma permanece válida. |

## Catálogo, preço e pedido

| ID | Preparação | Ação proibida | Resultado esperado |
|---|---|---|---|
| ISO-20 | Mesmo SKU existente em BR e EU | Resolver o SKU sem o mercado ativo | A operação exige mercado e usa somente a linha daquele mercado. |
| ISO-21 | UUID/código de produto EU numa sessão BR | Associar ao pedido, conjunto, catálogo, tipo, categoria ou opcional BR | 404/422; nenhuma referência cruzada é gravada. |
| ISO-22 | Pedido BR e EU com o mesmo orc_id | Buscar o código na sessão BR | Somente o pedido BR é retornado; não ocorre ambiguidade global. |
| ISO-23 | Pedido de outro mercado conhecido por UUID/código | Ler, editar, finalizar, cancelar ou excluir | 404. |
| ISO-24 | Produto EU sem IVA explícito aprovado | Criar ou recalcular pedido EU | 422; não usar IPI, tabela por tipo nem zero como fallback. |
| ISO-25 | Cliente muda de lista depois da criação | Editar itens do pedido BR existente | A lista registrada no pedido é preservada; o cadastro atual não reescreve o snapshot. |
| ISO-26 | Carrinho BR preenchido | Trocar para EU ou para outra identidade | A chave do armazenamento muda; itens BR não aparecem no carrinho EU. |

## Importação, mídia, exportação e visão global

| ID | Preparação | Ação proibida | Resultado esperado |
|---|---|---|---|
| ISO-30 | CSV EU contém referência a dimensão BR | Importar produto | 422; nenhuma linha parcial é confirmada. |
| ISO-31 | CSV EU omite IVA ou traz novo valor | Tornar a taxa faturável automaticamente | A taxa fica pending; aprovação nominal separada é obrigatória. |
| ISO-32 | URL de mídia expirada, adulterada ou assinada para outra chave | Ler o objeto | 403; a assinatura cobre caminho e expiração. |
| ISO-33 | Sessão BR solicita exportação ou relatório comercial | Receber linhas EU | A saída contém somente BR. |
| ISO-34 | Sessão EU solicita dashboard/listagem/paginação | Receber contagem, cursor ou linha BR | A consulta e o cursor permanecem no escopo EU. |
| ISO-35 | Sessão comercial chama governança LGPD global | Ler retenção ou incidentes de outro mercado | 403; somente sessão de plataforma possui essa visão deliberadamente global. |
| ISO-36 | Resposta antiga de uma sessão de plataforma encerrada | Atualizar estado após logout/troca de identidade | A requisição é cancelada ou descartada pela geração da sessão. |

## Critério de manutenção

Cada mudança futura nos blocos de schema, API ou interface deve ligar seus testes
aos IDs afetados acima. Um 404 é preferível quando revelar a existência do
recurso de outro mercado acrescentaria informação ao solicitante.
