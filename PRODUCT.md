# Product

## Register

product

## Users

**Admin** — controla o sistema completo, cria usuários e acessa todos os dados.
**Vendedor** — time interno de vendas; gera orçamentos, gerencia clientes e pedidos.
**Representante** — vendedor externo (campo, showroom, home office); acessa em mobilidade para criar orçamentos e acompanhar seus próprios pedidos.
**Cadastros** — equipe de suporte; mantém clientes e representantes, sem acesso a pedidos.
**Produtos** — equipe de catálogo; mantém o catálogo de móveis e opcionais.
**Cliente** — usuário final; consulta seus próprios pedidos e assina contratos eletronicamente.

O contexto primário de uso é desktop (vendedores internos, admin), com uso mobile relevante para representantes externos em campo e showrooms.

## Product Purpose

Sistema de gestão comercial B2B para fabricante/distribuidora de móveis de luxo de alto padrão. Centraliza o catálogo de produtos com opcionais configuráveis (alumínio, madeira, tecido, couro, corda), o cadastro de clientes e representantes, a geração de orçamentos detalhados com descontos individuais por item, o histórico de pedidos com snapshots imutáveis e o fluxo de assinatura eletrônica de contratos com link temporário para o cliente.

Sucesso significa: um representante consegue gerar um orçamento profissional com foto do produto, opcionais e valor correto em menos de 3 minutos, e o cliente consegue assinar o contrato sem precisar instalar nada.

## Brand Personality

Luxuoso · Refinado · Discreto

Voz: segura, direta, sem exageros. Tom: profissional mas não frio — a elegância dos móveis físicos deve transparecer na interface digital. Metas emocionais: confiança no sistema, orgulho de usar uma ferramenta à altura do produto que vendem.

## Anti-references

**ERP genérico (SAP, TOTVS, Protheus)** — cinza industrial, densidade de informação sem hierarquia, identidade visual nula, fontes sem cuidado. O Ilya deve parecer o oposto: cada tela tem espaço para respirar, cada detalhe é intencional.

**SaaS B2B americano genérico** — azul corporativo, cards idênticos empilhados, dashboard template com métricas aleatórias. Sem personalidade de marca.

## Design Principles

1. **O produto reflete o produto** — a interface deve comunicar o mesmo cuidado artesanal dos móveis vendidos. Detalhes visuais importam tanto quanto funcionalidade.
2. **Discrição sobre exibicionismo** — luxo não grita. O dourado (#8b6914) é acento, nunca superfície. Espaço em branco é elemento de design.
3. **Clareza sem frieza** — a eficiência de uma ferramenta de trabalho com o calor da identidade premium. Nunca sacrificar legibilidade por estética.
4. **Mobile como extensão do campo** — representantes usam em showroom e em deslocamento. Mobile deve ser tão confortável quanto desktop, não uma versão degradada.
5. **Confiança através da consistência** — paleta contida, tipografia previsível, comportamentos uniformes entre páginas. O usuário nunca deve se perguntar "como isso funciona aqui?".

## Accessibility & Inclusion

WCAG AA mínimo. Contraste de texto ≥ 4.5:1 em todos os elementos de corpo. Foco visível em todos os interativos. Suporte a `prefers-reduced-motion` nas animações de loading (overlay ILYA). Sem dependência de cor como único canal semântico (badges e bolinhas de status usam ícone ou texto complementar).
