# Checklist LGPD de fornecedores e operadores

Preencher uma ficha por Railway, Vercel, storage, backup off-site, receptor de
webhook e futuro serviço de e-mail/SMS.

| Campo | Resposta/evidência |
|---|---|
| Razão social e país | |
| Serviço/finalidade | |
| Papel: operador/suboperador | |
| Categorias de dados | |
| Região de armazenamento | |
| Subprocessadores | |
| Transferência internacional e mecanismo | |
| Criptografia em trânsito e repouso | |
| Controle de acesso/MFA | |
| Logs e prazo de retenção | |
| Backup, expiração e destruição | |
| Prazo de notificação de incidente | |
| Apoio a direitos dos titulares | |
| Exclusão/devolução ao fim do contrato | |
| DPA/contrato e versão | |
| Responsável e data da revisão | |

## Critério de aceite

Não ativar fornecedor que trate dados pessoais sem:

- finalidade e instruções documentadas;
- medidas de segurança proporcionais;
- compromisso de incidente compatível com os três dias úteis da Ilya;
- subprocessadores e transferências conhecidos;
- exclusão/devolução ao término;
- responsável interno e evidência contratual.

## Resend — envio transacional de pedidos

Configuração técnica planejada: domínio `ilya.com.br`, região São Paulo,
Return-Path `send.ilya.com.br`, rastreamento de abertura e cliques desativado.
O operador receberá nome/endereço do destinatário e a cópia PDF do pedido.

Antes de alterar `ORDER_EMAIL_ENABLED` para `true`, preencher nesta ficha a
razão social/país, subprocessadores, retenção de conteúdo e logs, exclusão,
transferências, DPA, prazo de incidente e responsável/data da revisão. A
verificação técnica do domínio não substitui esse aceite organizacional.
