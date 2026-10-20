-- PostgreSQL database dump
-- Dumped from database version 16.4
-- Dumped by pg_dump version 16.4
-- Synthetic dataset for Ilya restore verification (P17) — NO real or personal data.

BEGIN;

CREATE TABLE public.markets (
    code VARCHAR(8) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    is_enabled BOOLEAN NOT NULL
);

CREATE TABLE public.users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE,
    role VARCHAR(32) NOT NULL
);

CREATE TABLE public.user_markets (
    user_id VARCHAR(36) NOT NULL REFERENCES public.users(id),
    market_code VARCHAR(8) NOT NULL REFERENCES public.markets(code),
    PRIMARY KEY (user_id, market_code)
);

CREATE TABLE public.catalogs (
    id VARCHAR(36) PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    market_code VARCHAR(8) NOT NULL REFERENCES public.markets(code)
);

CREATE TABLE public.products (
    id VARCHAR(36) PRIMARY KEY,
    product_code VARCHAR(64) NOT NULL,
    catalog_id VARCHAR(36) NOT NULL REFERENCES public.catalogs(id),
    description VARCHAR(255) NOT NULL
);

CREATE TABLE public.product_markets (
    product_id VARCHAR(36) NOT NULL REFERENCES public.products(id),
    market_code VARCHAR(8) NOT NULL REFERENCES public.markets(code),
    PRIMARY KEY (product_id, market_code)
);

CREATE TABLE public.clients (
    id VARCHAR(36) PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    market_code VARCHAR(8) NOT NULL REFERENCES public.markets(code),
    name VARCHAR(120) NOT NULL
);

CREATE TABLE public.orders (
    id VARCHAR(36) PRIMARY KEY,
    order_number VARCHAR(64) NOT NULL UNIQUE,
    market_code VARCHAR(8) NOT NULL REFERENCES public.markets(code),
    client_id VARCHAR(36) NOT NULL REFERENCES public.clients(id),
    status VARCHAR(32) NOT NULL
);

CREATE TABLE public.order_items (
    id VARCHAR(36) PRIMARY KEY,
    order_id VARCHAR(36) NOT NULL REFERENCES public.orders(id),
    product_id VARCHAR(36) NOT NULL REFERENCES public.products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO public.markets (code, name, is_enabled) VALUES
    ('BR', 'Brazil', TRUE),
    ('EU', 'European Union', TRUE);

INSERT INTO public.users (id, email, role) VALUES
    ('00000000-0000-0000-0000-000000000001', 'canary-br@synthetic.ilya.invalid', 'admin'),
    ('00000000-0000-0000-0000-000000000002', 'canary-eu@synthetic.ilya.invalid', 'admin');

INSERT INTO public.user_markets (user_id, market_code) VALUES
    ('00000000-0000-0000-0000-000000000001', 'BR'),
    ('00000000-0000-0000-0000-000000000002', 'EU');

INSERT INTO public.catalogs (id, code, market_code) VALUES
    ('10000000-0000-0000-0000-000000000001', 'CAT-BR-001', 'BR'),
    ('10000000-0000-0000-0000-000000000002', 'CAT-EU-001', 'EU');

INSERT INTO public.products (id, product_code, catalog_id, description) VALUES
    ('20000000-0000-0000-0000-000000000001', 'PROD-BR-001', '10000000-0000-0000-0000-000000000001', 'Synthetic product BR'),
    ('20000000-0000-0000-0000-000000000002', 'PROD-EU-001', '10000000-0000-0000-0000-000000000002', 'Synthetic product EU');

INSERT INTO public.product_markets (product_id, market_code) VALUES
    ('20000000-0000-0000-0000-000000000001', 'BR'),
    ('20000000-0000-0000-0000-000000000002', 'EU');

INSERT INTO public.clients (id, code, market_code, name) VALUES
    ('30000000-0000-0000-0000-000000000001', 'CLI-BR-001', 'BR', 'Synthetic Client BR'),
    ('30000000-0000-0000-0000-000000000002', 'CLI-EU-001', 'EU', 'Synthetic Client EU');

INSERT INTO public.orders (id, order_number, market_code, client_id, status) VALUES
    ('40000000-0000-0000-0000-000000000001', 'ORD-BR-001', 'BR', '30000000-0000-0000-0000-000000000001', 'confirmed'),
    ('40000000-0000-0000-0000-000000000002', 'ORD-EU-001', 'EU', '30000000-0000-0000-0000-000000000002', 'confirmed');

INSERT INTO public.order_items (id, order_id, product_id, quantity) VALUES
    ('50000000-0000-0000-0000-000000000001', '40000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 1),
    ('50000000-0000-0000-0000-000000000002', '40000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', 1);

COMMIT;
