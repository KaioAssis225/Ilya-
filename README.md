# Projeto Ilya — Monorepo

Este repositório contém a transposição de nível de produção para o **Projeto Ilya**, um sistema para catálogo de móveis, banco de dados de clientes/representantes externos e fechamento/geração de orçamentos e pedidos com snapshots históricos de segurança e controle de acesso baseado em papéis (RBAC).

---

## 🛠️ Stack Tecnológica

### Backend (`/backend`)
*   **Core:** Python 3.12, FastAPI (Assíncrono)
*   **Banco de Dados:** SQLAlchemy 2.0 (Async Engine via `asyncpg`), PostgreSQL 16
*   **Migrations:** Alembic
*   **Segurança:** Argon2id (`argon2-cffi`) com Pepper dinâmico, JWT (`python-jose`)
*   **Uploads:** Upload multipart direto em disco (`static/uploads/`) com armazenamento de UUID no banco

### Frontend (`/frontend`)
*   **Core:** React 19 (TypeScript), Vite 8
*   **CSS / Estilo:** Tailwind CSS v4, Fontes Google (Cormorant Garamond + Inter), Animações Customizadas
*   **Server State:** TanStack Query v5 (React Query)
*   **Routing & Auth:** React Router Dom v7, Axios com Interceptores de Autenticação (Silent Refresh)
*   **Utilitários:** jsPDF (geração client-side de orçamentos A4 com fotos, swatches coloridos e dimensões adaptativas Ø/L×P×A), Lucide React (ícones)

> **Block 12 (Medidas Especiais, Opcionais Relacionais & Seed de Luxo)** — implementado em 2026-06-26:
> catálogo de opcionais de cor/material (`optionals` + `product_optionals` N-to-N), flag `is_circular` em produtos e itens de pedido, remoção de `price` do produto (preço passa a ser negociado pelo vendedor em `unit_price` no orçamento), seed de luxo com 5 produtos ILY-001–005 e 29 opcionais em 8 categorias.

---

## 📁 Estrutura de Diretórios

```text
Ilya/
├── backend/
│   ├── alembic/              # Scripts de Migrations do Alembic
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py       # Injeção de dependências (get_db, get_current_user, require_roles)
│   │   │   └── routers/      # Rotas REST (products, clients, reps, orders, auth)
│   │   ├── core/
│   │   │   ├── config.py     # Leitura de variáveis do .env via pydantic-settings
│   │   │   ├── security.py   # Utilitários de hash (Argon2id) e JWT
│   │   │   └── permissions.py# Middlewares de controle RBAC
│   │   ├── models/           # Mapeamentos SQLAlchemy (User, Product, Order, etc.)
│   │   ├── schemas/          # Modelos Pydantic v2 de validação de Request/Response
│   │   └── main.py           # Inicialização e middlewares da API
│   ├── Dockerfile
│   ├── requirements.txt      # Dependências Python
│   ├── seed.py               # Popula 20 produtos padrão do catálogo
│   └── seed_admin.py         # Cria o administrador configurado no .env
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── client.ts     # Instância Axios com auto silent refresh (erro 401)
│   │   ├── components/       # Componentes compartilhados e ProtectedRoute
│   │   ├── contexts/         # AuthContext (gerenciador de token em memória)
│   │   ├── hooks/            # Hooks React Query (useAuth, useProducts, useOrders, etc.)
│   │   ├── lib/              # Motor do jsPDF (generatePDF.ts)
│   │   ├── pages/            # Telas (CadastroPage, OrcamentoPage, PedidosPage, LoginPage)
│   │   ├── App.tsx           # Configuração de rotas privadas/públicas
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── .env                      # Configurações de ambiente (segredos de criptografia)
└── docker-compose.yml        # Orquestração do PostgreSQL 16 e do container de Backend
```

---

## 🛡️ Segurança & Controle de Acesso (RBAC)

O sistema implementa 3 níveis de acesso no banco de dados:

1.  **`admin`**: Acesso completo a todas as entidades, incluindo exclusões e gerenciamento de usuários.
2.  **`vendedor`** (Gestor): Permissão para gerenciar produtos (cadastros/fotos) e visualizar todos os pedidos e clientes do sistema.
3.  **`representante`** (Vendedor Externo): Permissão para visualizar produtos, gerenciar clientes e emitir orçamentos/pedidos. 
    *   *Logical Multi-tenancy:* O representante é vinculado a um registro na tabela `representatives` (via `rep_id`). Suas consultas de listagem de pedidos são filtradas para retornar estritamente os pedidos criados sob o seu `rep_id`. Ele também é impedido de realizar spoofing ao criar pedidos.

### Hash de Senhas (Argon2id + Pepper)
A senha no banco de dados é salva com hash `Argon2id` acrescido do segredo local `PASSWORD_PEPPER` configurada nas variáveis de ambiente.

---

## 💾 Modelo de Banco de Dados (PostgreSQL)

```mermaid
erDiagram
    users {
        uuid id PK
        varchar email UK
        varchar hashed_password
        varchar role
        uuid rep_id FK
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }
    refresh_tokens {
        uuid id PK
        uuid user_id FK
        varchar token_hash UK
        timestamp expires_at
        boolean revoked
        timestamp created_at
        timestamp updated_at
    }
    optionals {
        uuid id PK
        varchar category
        varchar color_name
        varchar photo_path
        timestamp created_at
        timestamp updated_at
    }
    product_optionals {
        uuid product_id FK
        uuid optional_id FK
    }
    products {
        uuid id PK
        varchar product_code UK
        text description
        boolean is_circular
        numeric altura
        numeric largura
        numeric profundidade
        varchar photo_path
        timestamp created_at
        timestamp updated_at
    }
    clients {
        uuid id PK
        varchar name
        varchar phone
        varchar email
        varchar cep
        varchar address
        varchar city
        varchar state
    }
    representatives {
        uuid id PK
        varchar name
        varchar phone
        varchar email
        varchar cep
        varchar address
        varchar city
        varchar state
    }
    orders {
        uuid id PK
        varchar code UK
        varchar orc_id UK
        uuid client_id FK
        uuid rep_id FK
        numeric total_value
        text notes
        timestamp created_at
    }
    order_items {
        uuid id PK
        uuid order_id FK
        varchar product_code
        text description
        boolean is_circular
        numeric altura
        numeric largura
        numeric profundidade
        varchar opt_aluminio
        varchar opt_tecido
        varchar opt_corda
        integer qty
        numeric unit_price
    }

    users ||--o| representatives : "associado_a"
    users ||--o{ refresh_tokens : "possui"
    orders ||--o{ order_items : "contem"
    orders ||--|| clients : "gerado_para"
    orders ||--o| representatives : "emitido_por"
    products ||--o{ product_optionals : "tem"
    optionals ||--o{ product_optionals : "associado_em"
```

> [!NOTE]
> **Snapshots de Histórico:** A tabela `order_items` armazena os valores de dimensões e opcionais no momento exato do fechamento do pedido. Isso impede que alterações futuras no catálogo de produtos alterem retroativamente o histórico financeiro e técnico de pedidos antigos.

---

## 🚀 Como Executar Localmente

### 1. Requisitos
*   Docker e Docker Compose instalados.
*   Node.js instalado (para rodar o servidor de desenvolvimento do frontend).

### 2. Configurando as Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto (use o `.env.example` como base). As variáveis fundamentais de segurança são:
```ini
SECRET_KEY=sua_chave_secreta_jwt_gerada
PASSWORD_PEPPER=seu_pepper_secreto_para_argon2
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ilya_db
```

### 3. Subindo o Banco e o Backend (via Docker Compose)
Na raiz do monorepo, execute:
```bash
docker compose up --build -d
```
Isso iniciará:
*   O banco PostgreSQL acessível somente pela rede interna do Docker.
*   O backend FastAPI na porta `8000` (Swagger disponível em `http://localhost:8000/docs`).

### 4. Carga de Dados Inicial (Seeds)
Execute o carregamento de produtos e o usuário administrador inicial executando os scripts no container de backend:
```bash
# Semente de 20 produtos padrão do protótipo
docker compose exec backend python seed.py

# Criar o usuário admin inicial
docker compose exec backend python seed_admin.py
```
O administrador é criado a partir de `ADMIN_EMAIL` e `ADMIN_PASSWORD` do
arquivo `.env`. Não existem credenciais padrão no repositório. O seed não
redefine a senha quando o usuário já existe.

### 5. Executando o Frontend (React/Vite)
Navegue para a pasta frontend, instale dependências e inicie o servidor:
```bash
cd frontend
npm install
npm run dev
```
O frontend estará acessível em `http://localhost:5173/`.

## Backup e continuidade

O procedimento de backup verificável, criptografia, retenção, teste de
restauração e automação no Windows está documentado em
[`docs/GUIA_INFRA_OPERACOES.md`](docs/GUIA_INFRA_OPERACOES.md).
