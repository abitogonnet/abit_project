from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils.text import get_valid_filename
from PIL import Image, ImageOps


def normalize_uploaded_image(uploaded_file, fallback_name):
    source_file = getattr(uploaded_file, "file", uploaded_file)
    if hasattr(source_file, "seek"):
        source_file.seek(0)

    with Image.open(source_file) as image:
        image = ImageOps.exif_transpose(image)
        image = _to_rgb(image)

        output = BytesIO()
        image.save(output, format="JPEG", quality=88, optimize=True)

    base_name = Path(getattr(uploaded_file, "name", "") or fallback_name).stem
    safe_name = get_valid_filename(base_name) or fallback_name
    return ContentFile(output.getvalue(), name=f"{safe_name}.jpg")


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
