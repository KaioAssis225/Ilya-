# Baixa todas as fotos de produtos do site em produção para a pasta ./fotos,
# nomeando cada arquivo com a descrição do produto.
# Uso: python baixar_fotos.py  (pede login) — ou defina ILYA_EMAIL/ILYA_SENHA no ambiente.
import os
import re
import sys
import getpass
import urllib.request
import json

API = "https://ilya-production-7857.up.railway.app/api/v1"
PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fotos")


def post_json(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def get_json(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def nome_seguro(descricao: str) -> str:
    # Remove caracteres inválidos em nomes de arquivo no Windows,
    # incluindo quebras de linha presentes em algumas descrições
    nome = re.sub(r'[<>:"/\\|?*\r\n\t]', " ", descricao)
    nome = re.sub(r"\s+", " ", nome).strip().rstrip(".")
    return nome[:150] or "sem-descricao"


def main() -> None:
    email = os.environ.get("ILYA_EMAIL") or input("E-mail ou usuário: ")
    senha = os.environ.get("ILYA_SENHA") or getpass.getpass("Senha: ")

    print("Autenticando...")
    token = post_json(f"{API}/auth/login", {"identifier": email, "password": senha})["access_token"]

    print("Buscando catálogo...")
    produtos = get_json(f"{API}/products?limit=1000", token)
    com_foto = [p for p in produtos if p.get("photo_url")]
    print(f"{len(produtos)} produtos no catálogo, {len(com_foto)} com foto.")

    os.makedirs(PASTA, exist_ok=True)
    usados: dict[str, int] = {}
    baixadas, falhas = 0, 0

    for p in com_foto:
        url = p["photo_url"]
        if url.startswith("/"):
            url = API.replace("/api/v1", "") + url
        ext = os.path.splitext(url.split("?")[0])[1] or ".png"

        base = nome_seguro(p["description"])
        # Descrições repetidas ganham sufixo com o código do produto
        if base in usados:
            usados[base] += 1
            nome = f"{base} ({p.get('product_code', usados[base])}){ext}"
        else:
            usados[base] = 0
            nome = f"{base}{ext}"

        destino = os.path.join(PASTA, nome)
        try:
            urllib.request.urlretrieve(url, destino)
            baixadas += 1
            print(f"  [OK] {nome}")
        except Exception as e:
            falhas += 1
            print(f"  [ERRO] {nome}: {e}", file=sys.stderr)

    print(f"\nConcluído: {baixadas} fotos salvas em {PASTA}" + (f" ({falhas} falhas)" if falhas else ""))


if __name__ == "__main__":
    main()
