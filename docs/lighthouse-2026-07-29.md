# Otimização Lighthouse — 2026-07-29

## Objetivo

Manter todas as categorias do Lighthouse em pelo menos 95 pontos no carregamento
móvel da página inicial pública.

## Linha de base

Medição da produção antes das alterações (`https://ilya-rust.vercel.app`):

| Categoria | Pontuação |
| --- | ---: |
| Performance | 82 |
| Acessibilidade | 95 |
| Boas práticas | 89 |
| SEO | 82 |

Principais causas: login bloqueado pela restauração de sessão, bundle inicial com
código autenticado, fontes não utilizadas e bloqueadas pela CSP, requisição de
notificações sem usuário, contraste insuficiente, ausência de metadados e
`robots.txt` atendido pelo fallback da SPA.

## Alterações

- A aplicação autenticada passou a ser carregada sob demanda.
- A tela de login aparece enquanto a restauração de sessão ocorre em paralelo.
- Sessão anônima sem cookie retorna `204`, sem registrar um falso erro `401`.
- Notificações só são consultadas quando há usuário autenticado.
- Fontes foram limitadas ao subconjunto latino e deixaram de ser embutidas como
  `data:` incompatível com a CSP.
- Assets versionados receberam cache imutável.
- Contraste e tamanho dos textos da tela de login foram corrigidos.
- Foram adicionados descrição, `robots.txt`, preconnect e favicon SVG.

## Evidência local

Build de produção servido localmente com perfil móvel padrão do Lighthouse 12.8.2,
três execuções consecutivas:

| Execução | Performance | Acessibilidade | Boas práticas | SEO | LCP |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 99 | 100 | 100 | 100 | 1,7 s |
| 2 | 97 | 100 | 100 | 100 | 2,2 s |
| 3 | 99 | 100 | 100 | 100 | 1,7 s |

Também foram aprovados o lint, o build TypeScript/Vite e os 140 testes do backend.
A comprovação definitiva deve ser repetida na URL de produção após o deploy, pois
latência de rede, servidor e infraestrutura não são reproduzidas integralmente
em ambiente local.
