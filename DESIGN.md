# Design

## Theme

Light. Fundo linho claro com acentos dourados e tipografia marrom-café escuro. Sem modo escuro — o sistema é usado em ambientes de trabalho iluminados (escritório, showroom).

## Color Palette

| Token | Hex | Uso |
|---|---|---|
| `--bg` | `#f8f6f2` | Fundo geral (corpo da página) |
| `--surface` | `#ffffff` | Cards, modais, painéis, tabelas |
| `--surface-alt` | `#fbfaf8` | Cabeçalhos de tabela, rodapés de card |
| `--surface-warm` | `#f5ede3` | Card de adicionar produto (tom âmbar suave) |
| `--border` | `#e8e0d6` | Bordas de inputs, cards, divisórias |
| `--border-warm` | `#e8dccb` | Bordas de cards de produto/âmbar |
| `--ink` | `#2c2420` | Texto principal (marrom-café escuro) |
| `--ink-mid` | `#4a3f38` | Texto secundário, valores de tabela |
| `--ink-muted` | `#9d8d81` | Labels, placeholders, metadata |
| `--ink-faint` | `#a89a8e` | Placeholders de input |
| `--ink-ghost` | `#c8bdb5` | Ícones inativos, divisórias suaves |
| `--gold` | `#8b6914` | Acento primário: CTAs, badges, links ativos, destaques |
| `--gold-hover` | `#7a5c10` | Hover de botão primário |
| `--gold-dark` | `#725510` | Active de botão primário |
| `--gold-bg` | `rgba(139,105,20,0.10)` | Fundo suave de badges dourados |
| `--terracotta` | `#b25e50` | Aba Produtos (cadastro), ações destrutivas suaves |
| `--mineral` | `#507a9b` | Aba Representantes (cadastro) |
| `--olive` | `#648261` | Aba Clientes (cadastro) |
| `--danger` | `#b91c1c` (red-700) | Ações destrutivas (excluir) |
| `--success` | `#80b280` (verde suave) | Bolinhas de status assinado |
| `--error` | vermelho suave | Bolinhas de status pendente |

## Typography

**Display / Títulos:** Cormorant Garamond (400, 500, 600) — serif elegante para h1, h2, h3 e marcas textuais (ex: letreiro ILYA no loading). `letter-spacing: 0.02em`.

**Interface / Corpo:** Inter (400, 500, 600) — sans-serif humanista para todo o texto de UI, labels, tabelas, inputs, botões.

**Código / SKUs:** `font-mono` (Tailwind default) — para códigos de produto (ILY-001) e códigos de pedido (PED-0001, ORC-0001).

Hierarquia de tamanho:
- Títulos de página: `text-base font-semibold` uppercase com tracking
- Títulos de modal: `text-lg font-semibold`
- Labels de campo: `text-xs font-bold uppercase tracking-wider text-[--ink-muted]`
- Corpo de tabela: `text-sm`
- Metadata/SKU: `text-xs` ou `text-[10px]`

## Components

### Botões
- **Primário** (`.btn-primary`): fundo `--gold`, texto branco, uppercase, `tracking-wide`, `rounded-lg`, sombra dourada no hover.
- **Secundário** (`.btn-secondary`): fundo branco, borda `--border`, texto `--ink`.
- **Perigo** (`.btn-danger`): fundo red-700.

### Inputs (`.input`)
Fundo branco, borda `--border`, `rounded-lg`, foco com ring `--gold/25` e borda `--gold/60`. Placeholder `--ink-faint`.

### Modais
- **Overlay** (`.modal-overlay`): `bg-[#2c2420]/30 backdrop-blur-sm`, `fadeIn 0.15s`.
- **Panel** (`.modal-panel`): fundo branco, borda `--border`, `rounded-xl`, `shadow-2xl`, `slideUp 0.18s`.

### Tabelas
- Header: `bg-[#fbfaf8]`, texto `--ink-muted`, uppercase, `text-xs`.
- Linhas: hover `bg-[#fcfbf9]`, separação `divide-[--border]`.
- Miniaturas: 48×48px desktop, 40×40px modal, `rounded-lg`, `border border-[--border]`.

### Cards de Seção (`.card-section`)
Fundo branco, `border border-[--border]`, `rounded-xl`, `shadow-sm`.

### Badges / Status
- Código de pedido: fundo `--gold-bg`, texto `--gold`, `font-mono font-bold`.
- Status de assinatura: bolinha 8px — verde (#22c55e) se assinado, vermelha (#ef4444) se pendente.

### Sidebar de Abas (Cadastro)
Abas empilhadas com cor de destaque por categoria:
- Produtos: `#b25e50` (terracota)
- Representantes: `#507a9b` (mineral)
- Clientes: `#648261` (oliva)
- Tipos / Opcionais: neutro `--ink-muted`

### Loading Premium (ILYA Overlay)
- Fundo: `bg-[#1a1410]/88 backdrop-blur-sm`
- Letreiro ILYA: Cormorant Garamond, 80px, gradiente dourado animado (`lightSweep`)
- Subtítulo: `text-[11px] tracking-[0.55em]` âmbar, pulsação (`fadeInOut`)
- Barra de progresso: linha de 1px, gradiente dourado, `progressLine 3s`
- Halo radial: `pulseRadial` dourado suave no fundo

## Layout

Grid de duas colunas em páginas principais:
- **Orçamento**: `lg:grid-cols-[1fr_360px]` — conteúdo à esquerda (1fr), sidebar de configuração à direita (360px fixos).
- **Cadastro**: `md:grid-cols-[220px_1fr]` — sidebar de abas à esquerda (220px), área de dados à direita.

Breakpoints de responsividade: `md` (768px) para Cadastro, `lg` (1024px) para Orçamento e navegação mobile.

Padding padrão: `px-4 lg:px-8`, `py-4 lg:py-6`. Máximo de largura: `max-w-7xl mx-auto`.

## Motion

Keyframes definidos globalmente:
- `fadeIn`: opacidade 0→1, 0.15s ease-out (modais overlay)
- `slideUp`: transform translateY(12px)→0 + opacidade, 0.18s ease-out (modal panels)
- `slideInRight`: para toasts
- `lightSweep`: `background-position` animado para efeito de luz dourada no texto
- `fadeInOut`: pulsação suave (0.4→1→0.4 opacity)
- `progressLine`: largura 0→100% em 3s linear
- `pulseRadial`: escala do halo radial dourado

`prefers-reduced-motion`: animações de loading (`lightSweep`, `pulseRadial`) devem cair para `opacity: 1` sem animação. Modais mantêm fade suave.

## Spacing

Escala de espaço: Tailwind padrão. Padrões frequentes:
- Entre seções de card: `space-y-4` ou `space-y-5`
- Entre labels e inputs: `space-y-1`
- Gap de grid: `gap-6`
- Padding de card: `p-5` (desktop), `p-3.5` (mobile)
- Padding de célula de tabela: `px-4 py-3.5`
