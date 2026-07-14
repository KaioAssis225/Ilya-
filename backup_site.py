"""Exportação lógica da API e das fotos referenciadas do Projeto Ilya.

Este arquivo complementa o pg_dump, mas não o substitui. Ele não consegue
copiar arquivos órfãos existentes no volume do Railway.

Uso:
    $env:ILYA_EMAIL = "administrador"
    $env:ILYA_SENHA = "..."
    $env:BACKUP_ENCRYPTION_PASSWORD = "..."
    py -3.12 backup_site.py
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


API = os.environ.get(
    "ILYA_API_URL", "https://ilya-production-7857.up.railway.app/api/v1"
).rstrip("/")
BASE = API.removesuffix("/api/v1")
ROOT = Path(__file__).resolve().parent
CREATED_AT = datetime.now()
BACKUP_DIR = ROOT / "backups" / f"ilya-site-{CREATED_AT.strftime('%Y%m%dT%H%M%S')}"
PAGE_SIZE = 200

ENTITIES = {
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


def request_json(url: str, token: str | None = None, body: dict | None = None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    method = "GET"
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def get_all(endpoint: str, token: str):
    first = request_json(f"{API}/{endpoint}?skip=0&limit={PAGE_SIZE}", token)
    if not isinstance(first, list):
        return first
    items = list(first)
    skip = PAGE_SIZE
    while len(first) == PAGE_SIZE:
        first = request_json(f"{API}/{endpoint}?skip={skip}&limit={PAGE_SIZE}", token)
        items.extend(first)
        skip += PAGE_SIZE
    return items


def collect_photo_urls(value, urls: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, str) and "photo" in key and child.startswith(("/static/", "http")):
                urls.add(child)
            else:
                collect_photo_urls(child, urls)
    elif isinstance(value, list):
        for child in value:
            collect_photo_urls(child, urls)


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "IlyaBackup/2.0"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256(path)}  {path.name}\n", encoding="ascii"
    )


def apply_retention(folder: Path) -> None:
    candidates: list[tuple[datetime, Path]] = []
    for path in folder.glob("ilya-site-*.zip*"):
        if path.suffix == ".sha256":
            continue
        try:
            stamp = datetime.strptime(path.name.split("ilya-site-", 1)[1][:15], "%Y%m%dT%H%M%S")
        except (ValueError, IndexError):
            continue
        candidates.append((stamp, path))
    candidates.sort(reverse=True)
    now = datetime.now()
    keep = {path for stamp, path in candidates if stamp >= now - timedelta(days=7)}
    weeks: set[tuple[int, int]] = set()
    months: set[tuple[int, int]] = set()
    for stamp, path in candidates:
        iso = stamp.isocalendar()
        week = (iso.year, iso.week)
        month = (stamp.year, stamp.month)
        if len(weeks) < 4 and week not in weeks:
            weeks.add(week)
            keep.add(path)
        if len(months) < 6 and month not in months:
            months.add(month)
            keep.add(path)
    for _, path in candidates:
        if path not in keep:
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".sha256").unlink(missing_ok=True)


def find_openssl() -> str | None:
    found = shutil.which("openssl")
    if found:
        return found
    candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "usr" / "bin" / "openssl.exe"
    return str(candidate) if candidate.exists() else None


def encrypt_zip(zip_path: Path) -> Path:
    password = os.environ.get("BACKUP_ENCRYPTION_PASSWORD")
    if not password:
        if os.environ.get("ALLOW_UNENCRYPTED_BACKUP") == "1":
            return zip_path
        zip_path.unlink(missing_ok=True)
        raise RuntimeError(
            "Defina BACKUP_ENCRYPTION_PASSWORD. ALLOW_UNENCRYPTED_BACKUP=1 "
            "só deve ser usado em armazenamento protegido."
        )
    openssl = find_openssl()
    if not openssl:
        zip_path.unlink(missing_ok=True)
        raise RuntimeError("OpenSSL não encontrado; o ZIP sem criptografia foi removido.")
    encrypted = zip_path.with_suffix(zip_path.suffix + ".enc")
    partial = encrypted.with_suffix(encrypted.suffix + ".partial")
    try:
        result = subprocess.run([
            openssl, "enc", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "200000",
            "-in", str(zip_path), "-out", str(partial),
            "-pass", "env:BACKUP_ENCRYPTION_PASSWORD",
        ], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode:
            raise RuntimeError(f"Falha ao criptografar o ZIP: {result.stderr.strip()}")
        if not partial.is_file() or partial.stat().st_size <= zip_path.stat().st_size:
            raise RuntimeError("A criptografia do ZIP gerou um arquivo incompleto.")
        partial.replace(encrypted)
        return encrypted
    finally:
        partial.unlink(missing_ok=True)
        zip_path.unlink(missing_ok=True)


def build_manifest(commit: str, counts: dict[str, int], photo_urls: set[str],
                   export_errors: list[str], photo_errors: list[str]) -> dict:
    files: dict[str, dict[str, object]] = {}
    for path in BACKUP_DIR.rglob("*"):
        if path.is_file() and path.name != "manifesto.json":
            files[str(path.relative_to(BACKUP_DIR))] = {
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
    return {
        "criado_em": CREATED_AT.isoformat(timespec="seconds"),
        "api": API,
        "commit": commit,
        "registros": counts,
        "fotos_encontradas": len(photo_urls),
        "falhas_exportacao": export_errors,
        "falhas_fotos": photo_errors,
        "completo": not export_errors and not photo_errors,
        "arquivos": files,
    }


def main() -> int:
    email = os.environ.get("ILYA_EMAIL") or input("E-mail ou usuário administrador: ")
    password = os.environ.get("ILYA_SENHA") or getpass.getpass("Senha: ")
    print("Autenticando...")
    token = request_json(f"{API}/auth/login", body={"identifier": email, "password": password})["access_token"]

    data_dir = BACKUP_DIR / "dados"
    uploads_dir = BACKUP_DIR / "uploads"
    data_dir.mkdir(parents=True)
    uploads_dir.mkdir(parents=True)
    photo_urls: set[str] = set()
    counts: dict[str, int] = {}
    export_errors: list[str] = []

    for endpoint, name in ENTITIES.items():
        print(f"Exportando {name}...")
        try:
            data = get_all(endpoint, token)
            (data_dir / f"{name}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            counts[name] = len(data) if isinstance(data, list) else 1
            collect_photo_urls(data, photo_urls)
        except Exception as exc:  # mantém evidência parcial e sinaliza falha ao final
            export_errors.append(f"{name}: {exc}")
            print(f"  ERRO: {exc}", file=sys.stderr)

    photo_errors: list[str] = []
    seen_names: dict[str, str] = {}
    print(f"Baixando {len(photo_urls)} fotografia(s)...")
    for url in sorted(photo_urls):
        full_url = url if url.startswith("http") else BASE + url
        name = os.path.basename(url.split("?", 1)[0])
        if not name:
            photo_errors.append(f"URL sem nome de arquivo: {url}")
            continue
        if name in seen_names and seen_names[name] != full_url:
            photo_errors.append(f"Colisão de nome {name}: {seen_names[name]} / {full_url}")
            continue
        seen_names[name] = full_url
        try:
            download(full_url, uploads_dir / name)
        except Exception as exc:
            photo_errors.append(f"{name}: {exc}")

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(
        ["git", "bundle", "create", str(BACKUP_DIR / "repo.bundle"), "--all"],
        cwd=ROOT, check=True, capture_output=True,
    )
    (BACKUP_DIR / "LEIA-ME.txt").write_text(
        "Este é um complemento lógico. A fonte de verdade é o pg_dump criado por "
        "ops/backup_database.py. Os uploads incluem somente fotos referenciadas pela API.\n",
        encoding="utf-8",
    )
    manifest = build_manifest(commit, counts, photo_urls, export_errors, photo_errors)
    (BACKUP_DIR / "manifesto.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    zip_path = BACKUP_DIR.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in BACKUP_DIR.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(BACKUP_DIR.parent))
    with zipfile.ZipFile(zip_path, "r") as archive:
        damaged = archive.testzip()
        if damaged:
            raise RuntimeError(f"Arquivo corrompido dentro do ZIP: {damaged}")
    final_path = encrypt_zip(zip_path)
    write_checksum(final_path)
    shutil.rmtree(BACKUP_DIR)
    apply_retention(final_path.parent)
    print(f"Backup lógico gerado: {final_path}")
    if export_errors or photo_errors:
        raise RuntimeError(
            f"Backup parcial: {len(export_errors)} exportação(ões) e "
            f"{len(photo_errors)} fotografia(s) falharam."
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if BACKUP_DIR.exists():
            shutil.rmtree(BACKUP_DIR, ignore_errors=True)
        print(f"ERRO: {exc}", file=sys.stderr)
        raise SystemExit(1)
