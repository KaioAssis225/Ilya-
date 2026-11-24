"""Copia os buckets do Ilya para um snapshot privado na VPS.

Recebe em stdin um objeto JSON com as configurações OBJECT_STORAGE,
OBJECT_STORAGE_EU e COMMENT_ATTACHMENTS. Execute com boto3 e monte uma
pasta privada e persistente em /snapshots.
"""

import hashlib
import json
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


SOURCES = {
    "br": "OBJECT_STORAGE",
    "eu": "OBJECT_STORAGE_EU",
    "anexos": "COMMENT_ATTACHMENTS",
}


def copy_object(client, bucket, destination, obj):
    key = obj["Key"]
    parts = key.split("/")
    if any(part in {"", ".", ".."} for part in parts) or "\\" in key:
        raise ValueError("O bucket contém uma chave incompatível com o filesystem")

    path = destination.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    response = client.get_object(Bucket=bucket, Key=key, IfMatch=obj["ETag"])
    body = response["Body"]
    try:
        with path.open("xb") as output:
            shutil.copyfileobj(body, output, length=1024 * 1024)
    finally:
        body.close()

    if path.stat().st_size != obj["Size"]:
        raise RuntimeError("O tamanho do objeto copiado diverge do inventário")
    with path.open("rb") as copied:
        sha256 = hashlib.file_digest(copied, "sha256").hexdigest()
    return {"key": key, "bytes": obj["Size"], "etag": obj["ETag"], "sha256": sha256}


def main():
    settings = json.load(sys.stdin)
    root = Path("/snapshots")
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    with tempfile.TemporaryDirectory(prefix=".ilya-media-", dir=root) as temporary:
        staging = Path(temporary)
        manifest = {}
        for label, prefix in SOURCES.items():
            endpoint = settings[f"{prefix}_ENDPOINT"]
            if urlsplit(endpoint).scheme != "https":
                raise ValueError("A origem dos arquivos precisa usar HTTPS")
            bucket = settings[f"{prefix}_BUCKET"]
            style = settings.get(f"{prefix}_ADDRESSING_STYLE")
            if label == "eu" and not style:
                style = settings.get("OBJECT_STORAGE_ADDRESSING_STYLE")
            style = "virtual" if style in (None, "", "virtual-host") else style
            client = boto3.client(
                "s3", endpoint_url=endpoint, region_name=settings.get(f"{prefix}_REGION") or "auto",
                aws_access_key_id=settings[f"{prefix}_ACCESS_KEY_ID"],
                aws_secret_access_key=settings[f"{prefix}_SECRET_ACCESS_KEY"],
                config=Config(signature_version="s3v4", s3={"addressing_style": style},
                              retries={"mode": "standard", "max_attempts": 4},
                              connect_timeout=5, read_timeout=30),
            )
            destination = staging / label
            destination.mkdir()
            pages = client.get_paginator("list_objects_v2").paginate(Bucket=bucket)
            objects = [obj for page in pages for obj in page.get("Contents", [])]
            print(f"{label}: copiando {len(objects)} objetos", flush=True)
            with ThreadPoolExecutor(max_workers=4) as pool:
                manifest[label] = list(pool.map(
                    lambda obj: copy_object(client, bucket, destination, obj), objects,
                ))

        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        snapshot = root / f"ilya-media-{stamp}-{staging.name.removeprefix('.ilya-media-')}"
        staging.rename(snapshot)
    print(f"Snapshot verificado: {snapshot.name}")
    for label, objects in manifest.items():
        print(f"  {label}: {len(objects)} objetos, {sum(obj['bytes'] for obj in objects)} bytes")


if __name__ == "__main__":
    try:
        main()
    except (BotoCoreError, ClientError, KeyError, OSError, RuntimeError, ValueError) as exc:
        code = exc.response.get("Error", {}).get("Code") if isinstance(exc, ClientError) else None
        print(f"Falha ao criar o snapshot: {type(exc).__name__} {code or ''}", file=sys.stderr)
        raise SystemExit(1)
