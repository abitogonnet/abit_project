from io import BytesIO
from pathlib import Path
from uuid import uuid4

from django.core.files.base import ContentFile
from django.utils.text import get_valid_filename
from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
except ImportError:  # pragma: no cover
    register_heif_opener = None
else:
    register_heif_opener()


MAX_SOURCE_IMAGE_BYTES = 50 * 1024 * 1024
MAX_IMAGE_DIMENSION = 2560


def normalize_uploaded_image(uploaded_file, fallback_name):
    if getattr(uploaded_file, "size", 0) > MAX_SOURCE_IMAGE_BYTES:
        raise ValueError("La imagen supera el máximo permitido de 50 MB.")

    source_file = getattr(uploaded_file, "file", uploaded_file)
    if hasattr(source_file, "seek"):
        source_file.seek(0)

    with Image.open(source_file) as image:
        image.load()
        image = ImageOps.exif_transpose(image)
        image = _to_rgb(image)
        if max(image.size) > MAX_IMAGE_DIMENSION:
            image.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                Image.Resampling.LANCZOS,
            )

        output = BytesIO()
        image.save(output, format="JPEG", quality=88, optimize=True)

    base_name = Path(getattr(uploaded_file, "name", "") or fallback_name).stem
    safe_name = get_valid_filename(base_name) or fallback_name
    normalized = ContentFile(
        output.getvalue(),
        name=f"{safe_name}-{uuid4().hex}.jpg",
    )
    normalized.content_type = "image/jpeg"
    normalized._catalog_normalized = True
    return normalized


def _to_rgb(image):
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba_image = image.convert("RGBA")
        background = Image.new("RGB", rgba_image.size, (255, 255, 255))
        background.paste(rgba_image, mask=rgba_image.getchannel("A"))
        return background

    if image.mode != "RGB":
        return image.convert("RGB")

    return image
