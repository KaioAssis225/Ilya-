# Teste do PDF do pedido com Outlook

Esta alternativa usa a caixa `procgh@outlook.com` pelo Microsoft Graph e não
depende da verificação DNS de `ilya.com.br`. O Resend pode continuar configurado,
mas não é chamado enquanto `ORDER_EMAIL_PROVIDER=microsoft_graph`.

## Variáveis do worker

```ini
ORDER_EMAIL_MODE=test
ORDER_EMAIL_PROVIDER=microsoft_graph
ORDER_EMAIL_TEST_ALLOWLIST=procgh@outlook.com
ORDER_EMAIL_FROM=Ilya Pedidos <procgh@outlook.com>
ORDER_EMAIL_REPLY_TO=procgh@outlook.com
ORDER_EMAIL_PDF_RENDERER=playwright
MICROSOFT_GRAPH_CLIENT_ID=<id do aplicativo público>
MICROSOFT_GRAPH_REFRESH_TOKEN=<segredo obtido com consentimento>
MICROSOFT_GRAPH_TENANT=consumers
MICROSOFT_GRAPH_SENDER_EMAIL=procgh@outlook.com
```

A API recebe `ORDER_EMAIL_MODE=test`, `ORDER_EMAIL_PROVIDER=microsoft_graph` e
a mesma allowlist. Os segredos do Graph são necessários somente no worker.

O aplicativo Microsoft precisa aceitar contas pessoais, ser cliente público e
ter a permissão delegada `Mail.Send`. O consentimento solicita também
`offline_access`, que fornece o refresh token armazenado no Railway. Nunca
grave o token em código, commit, log ou chat.

## Validação

1. Manter a allowlist apenas com um endereço controlado.
2. Usar **Enviar e-mail de teste** em um pedido cujo PDF tenha menos de 3 MB.
3. Confirmar o remetente, Reply-To e o PDF na caixa de entrada e nos Itens
   Enviados da conta Outlook.
4. Conferir no histórico do pedido o estado **Aceito pelo serviço**.
5. Só ampliar a allowlist depois do teste.

O endpoint `sendMail` responde `202 Accepted` sem identificador e não oferece os
eventos de entregue/devolvido usados pelo Resend. Portanto, esta alternativa
confirma aceitação pela Microsoft e presença em Itens Enviados, não entrega ao
destinatário. Além disso, o Graph não aplica automaticamente a chave de
idempotência: uma interrupção rara entre o `202` e o commit no banco pode
duplicar o envio. Esses limites devem ser aceitos antes de usar o Outlook em
produção.
