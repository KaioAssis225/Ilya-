# P11 — identidades técnicas e cenários autorizados

## Contrato

Use duas identidades distintas com papel `benchmark_readonly`: uma com **somente**
o vínculo ativo BR, outra com **somente** o vínculo ativo EU. Ambas devem ter
`can_approve_tax=false`, nenhuma permissão de plataforma, nenhuma carteira
comercial e `must_change_password=false` após o provisionamento controlado.
O mercado vem do token emitido no login; query string ou cabeçalho não escolhe
outro mercado. A conta EU só opera quando o mercado EU estiver habilitado.

Nenhuma conta ou senha é criada pelo código ou versionada. O operador autorizado
cria as identidades no procedimento administrativo da homologação, guarda senha
no secret manager do executor e vincula uma identidade a exatamente um mercado.
Dados de pedidos e produtos usados para medição são sintéticos e estáveis.

## Execução

O benchmark histórico mantém `BENCHMARK_API_TOKEN` para diagnósticos existentes.
Para P11, injete pelo secret manager `ILYA_BENCHMARK_USERNAME`,
`ILYA_BENCHMARK_PASSWORD`, `ILYA_BENCHMARK_MARKET` (`BR` ou `EU`) e
`BENCHMARK_TARGET_URL` (origem HTTPS). Execute uma vez por mercado:

```text
python ops/benchmark_production_api.py --mode smoke --commercial
```

`--commercial` acrescenta GET de produtos, pedidos e dashboard ao health e
`auth/me`. O catálogo em `ops/benchmark_scenarios.py` fixa caminhos, limites e
templates de rota. Somente o mercado do token é medido. A ferramenta autentica
antes da medição, confirma papel/mercado/vínculo único em `/auth/me`, mantém o
token em memória e faz novo login se receber 401. Senha e token não entram em
argumentos, relatório ou log. A latência do login não integra a amostra.

Se houver fixtures de detalhe, configure `ILYA_BENCHMARK_PRODUCT_CODE` e
`ILYA_BENCHMARK_ORDER_CODE` com códigos sintéticos exclusivos no mercado.
O benchmark procura esses códigos na listagem autenticada, exige correspondência
exata de código e mercado, e usa o UUID resolvido apenas em memória. O relatório
registra o template da rota, sem o código ou o UUID.

O modo `load` continua sujeito à allowlist de homologação já existente; não
use `--commercial` para carga sem janela e limites aprovados. P12 executará os
baselines em sete horários distintos. P15 usará o mesmo princípio para a sonda.

## Verificações pendentes do checkpoint

Com dados sintéticos, confirme 200 nas leituras autorizadas, 403 em mutações
de produtos/pedidos e em autogestão indevida, 401 após revogação, e ausência de
acesso cruzado BR/EU. Confira que logs e JSON de saída têm apenas status,
tempos, tamanho e template de rota; nunca corpo, cabeçalho Authorization,
cookie, nome, e-mail ou código identificador de cliente.

## Rotação e revogação

1. Em janela controlada, crie a nova senha no secret manager para **uma** conta
   técnica, sem copiá-la para shell history, arquivo `.env` ou CI em texto.
2. Atualize o segredo do executor; rode apenas smoke de leitura e confira o
   mercado, 403 de mutação e relatório sem dados pessoais.
3. Invalide sessões antigas (`auth_version`/revogação administrativa) e retire
   a senha anterior. Repita para a outra identidade.
4. Em suspeita de vazamento, suspenda o vínculo ou a conta, revogue sessões e
   interrompa benchmark/sonda antes de criar credencial substituta.

Se a capacidade `benchmark_readonly` não estiver aplicada pela migration no
ambiente, não substitua por `admin`, `produtos` ou `cliente`: esses papéis têm
mutações. O rollback operacional é revogar as duas identidades e desligar a
execução autenticada. A validação de RBAC e o ensaio de rotação ainda dependem
da homologação e do checkpoint combinado.
