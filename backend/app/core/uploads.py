import io
import os
import warnings

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError


_CHUNK_SIZE = 64 * 1024
_FORMAT_TO_EXTENSION = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


async def read_upload_limited(
    file: UploadFile,
    max_bytes: int,
    *,
    max_size_label: str,
) -> bytes:
    """Interrompe a leitura assim que o upload ultrapassa o limite configurado."""
    content = bytearray()
    while chunk := await file.read(_CHUNK_SIZE):
        content.extend(chunk)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Arquivo excede {max_size_label}.",
            )
    return bytes(content)


async def sanitize_image_upload(
    file: UploadFile,
    *,
    max_bytes: int,
    max_size_label: str,
    allowed_extensions: list[str],
) -> tuple[bytes, str]:
    """Valida a imagem, aplica orientação e a regrava sem EXIF/metadados."""
    allowed = {"jpg" if ext.lower() == "jpeg" else ext.lower() for ext in allowed_extensions}
    supplied_ext = os.path.splitext(file.filename or "")[-1].lower().lstrip(".")
    supplied_ext = "jpg" if supplied_ext == "jpeg" else supplied_ext
    if supplied_ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Extensão '{supplied_ext}' não permitida.",
        )

    raw = await read_upload_limited(file, max_bytes, max_size_label=max_size_label)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
            image.load()
        detected_ext = _FORMAT_TO_EXTENSION.get(image.format or "")
        if not detected_ext or detected_ext not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Conteúdo do arquivo não é uma imagem permitida.",
            )

        image = ImageOps.exif_transpose(image)
        if detected_ext == "jpg" and image.mode != "RGB":
            image = image.convert("RGB")
        elif detected_ext in {"png", "webp"} and image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA")

        output = io.BytesIO()
        save_format = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[detected_ext]
        save_options = {"quality": 90, "optimize": True} if detected_ext in {"jpg", "webp"} else {"optimize": True}
        image.save(output, format=save_format, **save_options)
        return output.getvalue(), detected_ext
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Conteúdo do arquivo não é uma imagem válida.",
        )
