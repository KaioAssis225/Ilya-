"""Bloco 72 — Carga Direta de Fotos no Servidor (Railway).

As fotos não moram no banco: o Postgres só guarda o caminho (`photo_path`).
Os arquivos reais ficam no volume persistente do Railway (`app/static/uploads`).
Este script baixa um .zip de fotos hospedado externamente e extrai seu
conteúdo direto nesse volume, sem passar pelas telas/endpoints da aplicação.

Uso (dentro do container/terminal do Railway, a partir de backend/):
    ZIP_PHOTOS_URL="https://.../fotos.zip" python -m app.download_photos
"""
import os
import sys
import tempfile
import zipfile

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"ERRO: variável de ambiente '{name}' não definida.")
        print("Defina ZIP_PHOTOS_URL apontando para o link direto do .zip antes de executar este script.")
        sys.exit(1)
    return value


def download_and_extract() -> None:
    zip_url = _require_env("ZIP_PHOTOS_URL")
    target_dir = settings.UPLOAD_DIR
    os.makedirs(target_dir, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".zip")
    os.close(tmp_fd)
    try:
        print(f"Baixando ZIP de fotos: {zip_url}")
        with httpx.stream("GET", zip_url, follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
        size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
        print(f"Download concluído: {size_mb:.1f} MB")

        print(f"Extraindo para o volume persistente: {target_dir}")
        extracted = 0
        with zipfile.ZipFile(tmp_path) as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue
                # os.path.basename ignora subpastas do zip e bloqueia zip-slip (../../etc)
                filename = os.path.basename(member.filename)
                if not filename:
                    continue
                dest_path = os.path.join(target_dir, filename)
                with zf.open(member) as source, open(dest_path, "wb") as dest:
                    dest.write(source.read())
                extracted += 1
        print(f"{extracted} arquivo(s) extraído(s) com sucesso em '{target_dir}'.")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            print("ZIP temporário removido — sem vazamento de disco.")


if __name__ == "__main__":
    download_and_extract()
