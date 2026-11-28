#!/usr/bin/env python3
"""Teste de fumaça da stack de produção. Roda NA VPS (só fala com 127.0.0.1).

  python3 smoke_test.py --credentials-file /opt/ilya-acceptance/acceptance.env

Verifica, com a conta SINTÉTICA de homologação (nunca uma conta real):
  1. /health/live e /health/ready do Ilya (19080) e do Estoque (19082)
  2. login no Ilya e sessão BR; troca para EU e volta para BR
  3. leituras de negócio em BR e EU (só GET): catálogos, produtos, foto assinada
     baixada do storage, assinatura adulterada recusada, pedido (cotação) e PDF guardado
  4. login único Ilya -> Estoque: handoff assinado -> /auth/central/exchange
  5. sessão do Estoque (/auth/me) com o papel da conta

A conta vem de ADMIN_EMAIL / ADMIN_PASSWORD no arquivo indicado. A senha é lida
aqui, só vai no corpo do login, e NÃO é impressa. Tokens e a assertion do login
único também nunca são impressos: a saída mostra só status e campos não secretos.

Usa os headers que o navegador mandaria atrás da Vercel (Origin) e repassa o
cookie de refresh à mão (ele é Secure e este teste fala em HTTP local).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ILYA = "http://127.0.0.1:19080"
ESTOQUE = "http://127.0.0.1:19082"
ILYA_ORIGIN = "https://ilya-rust.vercel.app"
ESTOQUE_ORIGIN = "https://ilya-estoque.vercel.app"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'FALHOU'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)
    return ok


def call(method: str, url: str, *, body: dict | None = None, token: str | None = None,
         origin: str | None = None, cookie: str | None = None) -> tuple[int, dict, str | None]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    if cookie:
        headers["Cookie"] = cookie
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, raw, set_cookie = response.status, response.read(), response.headers.get("Set-Cookie")
    except urllib.error.HTTPError as error:
        status, raw, set_cookie = error.code, error.read(), error.headers.get("Set-Cookie")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    return status, payload if isinstance(payload, dict) else {}, set_cookie


def read_credentials(path: Path) -> tuple[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, raw = line.partition("=")
        if key in {"ADMIN_EMAIL", "ADMIN_PASSWORD"}:
            values[key] = raw.strip().strip("'\"")
    if len(values) != 2:
        raise SystemExit("O arquivo precisa ter ADMIN_EMAIL e ADMIN_PASSWORD.")
    return values["ADMIN_EMAIL"], values["ADMIN_PASSWORD"]


def refresh_cookie(set_cookie: str | None) -> str | None:
    return set_cookie.split(";", 1)[0] if set_cookie else None


def fetch_raw(url: str, token: str) -> tuple[int, bytes, str]:
    """GET de um binário (PDF/imagem). Devolve status, corpo e Content-Type."""
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        return error.code, b"", error.headers.get("Content-Type", "")


def call_list(url: str, token: str) -> tuple[int, list]:
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read() or b"[]")
            return response.status, body if isinstance(body, list) else []
    except urllib.error.HTTPError as error:
        return error.code, []


def business_reads(token: str, market: str) -> None:
    """Catálogo, produtos com foto assinada, pedido (cotação) e PDF já gerado.

    Só GET. Não cria pedido, não gera PDF e não dispara e-mail (ORDER_EMAIL_MODE=off).
    O PDF é o documento já guardado do pedido; se o pedido mais recente não tiver
    um, o teste procura nos próximos e só avisa se nenhum tiver.
    """
    status, catalogs = call_list(f"{ILYA}/api/v1/catalogs", token)
    check(f"[{market}] catálogos", status == 200 and len(catalogs) > 0, f"HTTP {status} n={len(catalogs)}")

    status, products = call_list(f"{ILYA}/api/v1/products?limit=50&include_total=false", token)
    check(f"[{market}] produtos", status == 200 and len(products) > 0, f"HTTP {status} n={len(products)}")
    with_photo = next((p for p in products if p.get("photo_url")), None)
    if with_photo is None:
        print(f"  [AVISO] [{market}] nenhum dos 50 primeiros produtos tem foto; foto assinada não testada")
    else:
        # photo_url é um caminho assinado do próprio Ilya (/api/v1/media/...?expires&signature).
        # O download passa pelo storage de objetos (hoje o bucket do Railway).
        status, content, ctype = fetch_raw(ILYA + with_photo["photo_url"], token)
        check(f"[{market}] foto assinada baixa do storage",
              status == 200 and ctype.startswith("image/") and len(content) > 0,
              f"HTTP {status} {ctype} {len(content)} bytes")
        # Assinatura adulterada tem de ser recusada (403).
        broken = with_photo["photo_url"].rsplit("signature=", 1)[0] + "signature=" + "0" * 64
        status, _, _ = fetch_raw(ILYA + broken, token)
        check(f"[{market}] foto com assinatura adulterada é recusada", status == 403, f"HTTP {status}")

    status, orders = call_list(f"{ILYA}/api/v1/orders?limit=10", token)
    if not check(f"[{market}] lista de pedidos", status == 200, f"HTTP {status} n={len(orders)}") or not orders:
        return
    status, order, _ = call("GET", f"{ILYA}/api/v1/orders/{orders[0]['id']}", token=token)
    check(f"[{market}] detalhe do pedido (cotação)",
          status == 200 and bool(order.get("items") is not None) and order.get("market_code") == market,
          f"HTTP {status} mercado={order.get('market_code')} itens={len(order.get('items') or [])}")
    for candidate in orders:
        status, content, ctype = fetch_raw(f"{ILYA}/api/v1/orders/{candidate['id']}/email-document", token)
        if status == 200:
            check(f"[{market}] PDF do pedido",
                  content[:5] == b"%PDF-" and "pdf" in ctype, f"{len(content)} bytes")
            return
    print(f"  [AVISO] [{market}] nenhum dos 10 pedidos mais recentes tem PDF guardado; PDF não testado")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--credentials-file", type=Path, required=True)
    args = parser.parse_args()
    email, password = read_credentials(args.credentials_file)

    print("1) Saúde")
    for name, base in (("Ilya", ILYA), ("Estoque", ESTOQUE)):
        for path in ("/health/live", "/health/ready"):
            status, _, _ = call("GET", base + path)
            check(f"{name} {path}", status == 200, f"HTTP {status}")

    print("2) Login no Ilya (mercados BR e EU)")
    status, payload, set_cookie = call(
        "POST", f"{ILYA}/api/v1/auth/login",
        body={"identifier": email, "password": password}, origin=ILYA_ORIGIN,
    )
    token, cookie = payload.get("access_token"), refresh_cookie(set_cookie)
    if not check("login", status == 200 and bool(token) and bool(cookie), f"HTTP {status}"):
        return finish()
    status, me, _ = call("GET", f"{ILYA}/api/v1/auth/me", token=token)
    check("sessão BR", status == 200 and me.get("active_market") == "BR", f"mercado={me.get('active_market')}")
    markets = sorted(me.get("allowed_markets") or [])
    check("conta tem BR e EU", markets == ["BR", "EU"], f"mercados={markets}")
    check("can_access_stock (link do Estoque disponível)", me.get("can_access_stock") is True)

    status, switched, _ = call(
        "POST", f"{ILYA}/api/v1/auth/switch-market", body={"market": "EU"},
        token=token, origin=ILYA_ORIGIN, cookie=cookie,
    )
    eu_token = switched.get("access_token")
    if check("troca para EU", status == 200 and bool(eu_token), f"HTTP {status}"):
        status, me_eu, _ = call("GET", f"{ILYA}/api/v1/auth/me", token=eu_token)
        check("sessão EU", status == 200 and me_eu.get("active_market") == "EU",
              f"mercado={me_eu.get('active_market')}")
        # Mercado EU não vê o Estoque (regra do Ilya): o link some.
        check("EU sem acesso ao Estoque (esperado)", me_eu.get("can_access_stock") is False)
    status, back, _ = call(
        "POST", f"{ILYA}/api/v1/auth/switch-market", body={"market": "BR"},
        token=token, origin=ILYA_ORIGIN, cookie=cookie,
    )
    br_token = back.get("access_token")
    check("volta para BR", status == 200 and bool(br_token), f"HTTP {status}")
    if not br_token:
        return finish()

    print("3) Leituras de negócio (só GET; nada é gravado nem enviado)")
    business_reads(br_token, "BR")
    status, switched_eu, _ = call(
        "POST", f"{ILYA}/api/v1/auth/switch-market", body={"market": "EU"},
        token=br_token, origin=ILYA_ORIGIN, cookie=cookie,
    )
    if status == 200 and switched_eu.get("access_token"):
        business_reads(switched_eu["access_token"], "EU")
        # Volta ao BR para o login único (o EU não enxerga o Estoque).
        status, back2, _ = call(
            "POST", f"{ILYA}/api/v1/auth/switch-market", body={"market": "BR"},
            token=br_token, origin=ILYA_ORIGIN, cookie=cookie,
        )
        br_token = back2.get("access_token") or br_token

    print("4) Login único Ilya -> Estoque")
    status, link, _ = call("GET", f"{ILYA}/api/v1/stock/link", token=br_token)
    check("origem do Estoque informada pelo Ilya", status == 200 and bool(link.get("origin")),
          f"HTTP {status}")
    status, handoff, _ = call("POST", f"{ILYA}/api/v1/stock/handoff", token=br_token, origin=ILYA_ORIGIN)
    assertion = handoff.get("assertion")
    if not check("Ilya assina a autorização (handoff)", status == 200 and bool(assertion), f"HTTP {status}"):
        return finish()
    status, exchanged, set_cookie_stock = call(
        "POST", f"{ESTOQUE}/api/v1/auth/central/exchange",
        body={"assertion": assertion}, origin=ESTOQUE_ORIGIN,
    )
    stock_token = exchanged.get("access_token")
    check("Estoque aceita a assinatura e abre sessão própria",
          status == 200 and bool(stock_token) and bool(set_cookie_stock), f"HTTP {status}")
    if stock_token:
        status, stock_me, _ = call("GET", f"{ESTOQUE}/api/v1/auth/me", token=stock_token)
        check("sessão no Estoque", status == 200, f"HTTP {status} papel={stock_me.get('role')}")
    # A mesma autorização não pode valer duas vezes (uso único).
    status, _, _ = call("POST", f"{ESTOQUE}/api/v1/auth/central/exchange",
                        body={"assertion": assertion}, origin=ESTOQUE_ORIGIN)
    check("reuso da mesma autorização é recusado", status in (401, 403), f"HTTP {status}")
    return finish()


def finish() -> int:
    print("RESULTADO:", "tudo certo" if not failures else f"{len(failures)} falha(s): {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
