# Plano de atualização — avisos do backend

Data: 2026-08-14  
Branch analisada: `codex/integracao-app-access-isolada`  
Escopo: somente avisos de testes/dependências. Nenhuma alteração na `main`.

## Estado atual

- Suíte backend: **299 testes aprovados**.
- Avisos: **28** na execução mais recente.
- Não há falha funcional associada aos avisos.
- O `.env` da raiz é carregado corretamente quando os testes são executados no diretório `backend`.
- A integração com Estoque permanece fora da `main` e não será alterada neste plano.

## Inventário e risco

| Item | Origem | Risco | Impacto | Recomendação |
|---|---|---:|---|---|
| `HTTP_422_UNPROCESSABLE_ENTITY` | Testes próprios | ★☆☆☆☆ | Apenas aviso de API depreciada | Substituir pelo nome atual nos testes |
| `HTTP_413_REQUEST_ENTITY_TOO_LARGE` | Teste próprio | ★☆☆☆☆ | Apenas aviso de API depreciada | Substituir pelo nome atual no teste |
| `asyncio.iscoroutinefunction` | `slowapi` 0.1.10 | ★★☆☆☆ | Ruído nos testes; futura incompatibilidade possível | Atualizar somente após validar compatibilidade |
| `TestClient`/`httpx` | FastAPI/Starlette | ★★☆☆☆ | Aviso de compatibilidade do cliente de testes | Avaliar atualização coordenada de `httpx`/Starlette |
| Python 3.14 + dependências | Ambiente local | ★★★☆☆ | Pode revelar incompatibilidades fora dos testes unitários | Fixar versão suportada no CI antes de atualizar |
| Filtrar warnings | Configuração de testes | ★★☆☆☆ | Oculta sinais sem corrigir a origem | Usar apenas para avisos externos conhecidos |

## Plano seguro

### Fase 0 — checkpoint

- Concluída antes deste plano.
- Branch de referência e backups locais preservados.

### Fase 1 — alterações sem risco funcional

1. Trocar apenas os nomes depreciados nos testes Starlette.
2. Executar a suíte completa.
3. Confirmar que o resultado continua `299 passed`.

Risco esperado: ★☆☆☆☆.

### Fase 2 — compatibilidade de dependências

1. Criar ambiente isolado, sem alterar o ambiente de produção.
2. Avaliar atualização do `slowapi` e do conjunto FastAPI/Starlette/httpx.
3. Executar testes, build da imagem e smoke test de migrations.
4. Comparar OpenAPI, autenticação, rate limiting e uploads.

Risco esperado: ★★☆☆☆ a ★★★☆☆.

### Fase 3 — decisão de runtime

- Manter Python 3.13 no CI/produção até confirmar suporte completo de todas as dependências ao Python 3.14.
- Não atualizar Python e dependências críticas no mesmo change set.

Risco esperado: ★★★☆☆.

### Fase 4 — limpeza opcional

- Adicionar filtros de warnings somente depois de corrigir os avisos próprios.
- Registrar cada filtro com pacote, versão e motivo.

Risco esperado: ★★☆☆☆.

## Critérios para aprovação

- Nenhuma alteração na `main` durante as fases de teste.
- Suíte backend verde.
- Build frontend e imagem backend verdes.
- Migrations com único `head`.
- Smoke test de inicialização aprovado.
- Nenhuma regressão em autenticação, autorização, pedidos, catálogo ou clientes.
- Integração Estoque permanece isolada.

## Ordem recomendada

1. Corrigir nomes depreciados nos testes.
2. Rodar os 299 testes.
3. Fazer avaliação isolada de dependências.
4. Só então decidir se alguma atualização merece PR separado.

