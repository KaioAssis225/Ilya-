# Backup completo do estado atual do site em produção:
#   - dados/  → JSON de cada entidade exportada da API (catálogo, clientes,
#               representantes, pedidos com assinaturas, usuários)
#   - uploads/ → todas as fotos com o nome original do servidor (restauráveis)
#   - repo.bundle → clone completo do repositório git (código + histórico)
#   - LEIA-ME.txt → instruções de restauração
# Uso: python backup_site.py  (pede login admin) — ou ILYA_EMAIL/ILYA_SENHA no ambiente.
import os
import sys
import json
import getpass
import subprocess
import urllib.request
import zipfile
from datetime import date

API = "https://ilya-production-7857.up.railway.app/api/v1"
BASE = API.replace("/api/v1", "")
RAIZ = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(RAIZ, "backups", f"ilya-backup-{date.today().isoformat()}")

# endpoint → nome do arquivo (todas as rotas de listagem são paginadas)
ENTIDADES = {
    "products": "produtos",
    "clients": "clientes",
    "representatives": "representantes",
    "orders": "pedidos",
    "users": "usuarios",
    "product-groups": "grupos_ipi",
    "product-types": "subgrupos",
    "optional-categories": "categorias_opcionais",
    "optionals": "opcionais",
}

_PAGINA = 200  # menor 'le' entre as rotas de listagem


def post_json(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def get_json(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def get_todos(endpoint: str, token: str) -> list:
    """Pagina com skip/limit até esgotar; rotas sem paginação retornam direto."""
    try:
        primeira = get_json(f"{API}/{endpoint}?skip=0&limit={_PAGINA}", token)
    except Exception:
        return get_json(f"{API}/{endpoint}", token)  # rota sem skip/limit
    if not isinstance(primeira, list):
        return primeira
    itens, skip = list(primeira), _PAGINA
    while len(primeira) == _PAGINA:
        primeira = get_json(f"{API}/{endpoint}?skip={skip}&limit={_PAGINA}", token)
        itens.extend(primeira)
        skip += _PAGINA
    return itens


def coletar_urls_de_fotos(obj, urls: set) -> None:
    """Varre qualquer JSON coletando valores photo_url/*_photo_url."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and "photo" in k and v.startswith(("/static/", "http")):
                urls.add(v)
            else:
                coletar_urls_de_fotos(v, urls)
    elif isinstance(obj, list):
        for item in obj:
            coletar_urls_de_fotos(item, urls)


def main() -> None:
    email = os.environ.get("ILYA_EMAIL") or input("E-mail ou usuário (admin): ")
    senha = os.environ.get("ILYA_SENHA") or getpass.getpass("Senha: ")

    print("Autenticando...")
    token = post_json(f"{API}/auth/login", {"identifier": email, "password": senha})["access_token"]

    os.makedirs(os.path.join(PASTA, "dados"), exist_ok=True)
    os.makedirs(os.path.join(PASTA, "uploads"), exist_ok=True)

    fotos: set = set()
    for endpoint, nome in ENTIDADES.items():
        print(f"Exportando {nome}...")
        try:
            dados = get_todos(endpoint, token)
        except Exception as e:
            print(f"  [AVISO] {nome} falhou: {e}", file=sys.stderr)
            continue
        with open(os.path.join(PASTA, "dados", f"{nome}.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        registros = len(dados) if isinstance(dados, list) else 1
        print(f"  {registros} registros")
        coletar_urls_de_fotos(dados, fotos)

    print(f"Baixando {len(fotos)} arquivos de imagem (nomes originais do servidor)...")
    baixadas, falhas = 0, 0
    for url in sorted(fotos):
        full = url if url.startswith("http") else BASE + url
        nome_arq = os.path.basename(url.split("?")[0])
        try:
            urllib.request.urlretrieve(full, os.path.join(PASTA, "uploads", nome_arq))
            baixadas += 1
        except Exception as e:
            falhas += 1
            print(f"  [ERRO] {nome_arq}: {e}", file=sys.stderr)
    print(f"  {baixadas} baixadas" + (f", {falhas} falhas" if falhas else ""))

    print("Empacotando o repositório git (código + histórico completo)...")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=RAIZ).stdout.strip()
    subprocess.run(["git", "bundle", "create", os.path.join(PASTA, "repo.bundle"), "--all"],
                   cwd=RAIZ, check=True, capture_output=True)

    with open(os.path.join(PASTA, "LEIA-ME.txt"), "w", encoding="utf-8") as f:
        f.write(f"""BACKUP DO PROJETO ILYA — {date.today().isoformat()}
Commit do código no momento do backup: {commit}

CONTEÚDO
  dados/     JSONs de todas as entidades exportadas da API de produção
             (produtos, clientes, representantes, pedidos com assinaturas,
             usuários — sem hashes de senha —, grupos, subgrupos, opcionais)
  uploads/   Todas as imagens com o nome original do servidor
             (restauráveis direto no volume app/static/uploads do Railway)
  repo.bundle  Repositório git completo. Restaurar com:
               git clone repo.bundle ilya-restaurado

RESTAURAÇÃO DOS DADOS
  Os JSONs seguem os schemas da API. Para reimportar produtos/clientes/
  representantes em massa, o caminho suportado é o importador CSV
  (Manual_Importacao_CSV.md) ou requisições POST aos mesmos endpoints.
  As senhas de usuários NÃO estão no backup (a API não expõe hashes) —
  usuários restaurados precisarão de nova senha temporária.

OBSERVAÇÃO
  Este backup reflete o que a API expõe. O dump SQL direto do PostgreSQL
  (fonte da verdade, inclui hashes e histórico interno) pode ser feito no
  painel do Railway: Database → Backups / pg_dump.
""")

    zip_path = f"{PASTA}.zip"
    print("Compactando...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for pasta_atual, _, arquivos in os.walk(PASTA):
            for arq in arquivos:
                caminho = os.path.join(pasta_atual, arq)
                z.write(caminho, os.path.relpath(caminho, os.path.dirname(PASTA)))

    print(f"\nBackup concluído:\n  Pasta: {PASTA}\n  Zip:   {zip_path}")


if __name__ == "__main__":
    main()
