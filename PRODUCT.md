# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Representantes externos e internos — público principal.** Usam o Ilya para apresentar o catálogo, cadastrar clientes, configurar produtos, elaborar orçamentos e acompanhar pedidos. Trabalham em escritórios, showrooms, feiras, visitas comerciais e em deslocamento, alternando entre desktop e dispositivos móveis.

**Admin** — controla o sistema, cria usuários e acessa todos os dados.

**Cadastros** — mantém clientes e representantes conforme suas permissões.

**Produtos** — mantém o catálogo de móveis, tipos, grupos e opcionais.

**Executivo** — acompanha indicadores agregados no dashboard, sem acessar registros comerciais individuais.

**Cliente** — consulta os próprios pedidos. O fluxo histórico de assinatura eletrônica está preservado, mas a criação de novas assinaturas permanece desativada até nova decisão e homologação.

## Product Purpose

O Ilya é um sistema de gestão comercial B2B para uma fabricante e distribuidora de móveis de alto padrão. Ele centraliza catálogo, opcionais configuráveis, clientes, representantes, orçamentos, pedidos, perfis de faturamento e histórico comercial.

Seu objetivo principal é permitir que o representante produza rapidamente um orçamento profissional, correto e visualmente compatível com os produtos vendidos. Sucesso significa reduzir o esforço entre apresentar um móvel e entregar uma proposta clara ao cliente, especialmente durante atendimentos presenciais, feiras e showrooms.

## Positioning

O Ilya combina a praticidade de uma ferramenta operacional com uma experiência própria do ramo de móveis de alto padrão. Diferentemente de um ERP genérico, sua navegação, catálogo visual e fluxo de orçamento são construídos em torno da venda consultiva de móveis configuráveis.

O diferencial central é permitir que representantes internos e externos montem orçamentos com agilidade sem apresentar ao cliente uma interface industrial, genérica ou desconectada da identidade do produto físico.

## Operating Context

- Atendimento comercial em escritório, showroom, feira ou visita ao cliente.
- Uso primário em desktop, com uso móvel relevante e não secundário para representantes em campo.
- Consulta visual do catálogo com fotos, dimensões, grupos, tipos e opcionais de acabamento.
- Cadastro ou seleção de cliente durante o processo comercial.
- Configuração de itens, quantidades, descontos e perfil de faturamento antes do fechamento.
- Geração de orçamento e PDF profissional para apresentação ao cliente.
- Conversão e acompanhamento do orçamento ou pedido com preservação do histórico.
- Operação sujeita a regras de carteira, perfil, desconto, RBAC, retenção e LGPD.

## Capabilities and Constraints

- Catálogo de móveis com tipos, grupos, subgrupos, fotos, dimensões e opcionais configuráveis.
- Cadastro de clientes e representantes, incluindo CPF ou CNPJ quando aplicável.
- Perfis de faturamento e regras comerciais resolvidos e protegidos no servidor.
- Orçamentos e pedidos com desconto por item, IPI, observações e snapshots históricos.
- Geração de PDF no navegador com informações e imagens do orçamento.
- Controle de acesso por papéis e isolamento dos dados vinculados ao representante ou cliente.
- Dashboard executivo com informações agregadas.
- Importação de dados, notificações e integração assíncrona por webhooks/outbox.
- Frontend web responsivo em React e backend FastAPI com PostgreSQL.
- A experiência móvel deve suportar o trabalho real do representante e não ser uma versão degradada do desktop.
- Segurança, rastreabilidade, retenção e conformidade LGPD são restrições permanentes do produto.
- Assinaturas eletrônicas permanecem desativadas até nova decisão, testes completos e homologação.

## Brand Commitments

**Nome:** Ilya.

**Personalidade:** luxuosa, refinada e discreta.

**Voz:** segura, direta e profissional, sem frieza nem exageros.

A experiência deve condizer com o ramo de móveis de alto padrão e transmitir o mesmo cuidado percebido nos produtos físicos. O visual distinto é parte funcional da confiança comercial, não apenas decoração.

Devem ser evitadas interfaces com aparência de ERP industrial genérico ou de SaaS corporativo indiferenciado. A identidade visual específica permanece documentada separadamente em `DESIGN.md`.

## Evidence on Hand

- Código funcional do monorepo em `C:\Users\koian\OneDrive\Documentos\Ilya-`.
- Documentação operacional, histórica e de segurança em `C:\Users\koian\OneDrive\Desktop\Programador\Programador\Projeto Ilya`.
- Catálogo, fotografias e dados reais de produtos presentes nos fluxos e ativos do projeto.
- Histórico de migrations, testes backend, auditorias, pentests e correções versionadas.
- Relatórios de deploy e verificações de produção registrados na documentação externa.
- Não há depoimentos, estudos de caso, métricas comerciais comparativas ou afirmações públicas de desempenho aprovadas; trabalhos futuros não devem fabricá-los.

## Product Principles

1. **Orçamento sem atrito** — reduzir passos, retrabalho e espera entre a escolha do produto e a entrega da proposta.
2. **O sistema deve condizer com o que vende** — cada interação deve sustentar a percepção de qualidade associada aos móveis de alto padrão.
3. **Praticidade com segurança comercial** — tornar o fluxo simples sem enfraquecer regras de preço, desconto, carteira, autorização ou histórico.
4. **Mobilidade real** — atender representantes em campo, feiras e showrooms com a mesma confiança oferecida no desktop.
5. **Clareza gera confiança** — informações, estados e ações devem ser previsíveis para evitar erros durante o atendimento ao cliente.

## Accessibility & Inclusion

WCAG AA é o padrão mínimo. Textos de corpo devem manter contraste de pelo menos 4.5:1, todos os controles interativos precisam de foco visível e estados não podem depender exclusivamente de cor. Animações devem respeitar `prefers-reduced-motion`. Responsividade, áreas de toque e legibilidade móvel são requisitos do trabalho de campo dos representantes.
