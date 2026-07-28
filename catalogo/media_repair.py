from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import unquote, urlparse

from django.conf import settings
from django.core.files import File

from .models import Camisa, Chaleco, Cinturon, Combo, Corbata, Traje, Zapato


CATALOG_IMAGE_MODELS = (
    (Traje, ("foto_modelo", "foto_colgado")),
    (Chaleco, ("foto_modelo", "foto_colgado")),
    (Cinturon, ("foto_1", "foto_2")),
    (Corbata, ("foto_1", "foto_2")),
    (Camisa, ("foto_modelo", "foto_colgado")),
    (Zapato, ("foto_modelo", "foto_colgado")),
    (Combo, ("foto",)),
)

KNOWN_UPLOAD_DIRS = {
    "trajes",
    "chalecos",
    "cinturones",
    "corbatas",
    "camisas",
    "zapatos",
    "combos",
}


@dataclass
class MissingCatalogImage:
    model: str
    object_id: int
    field_name: str
    stored_name: str


def normalize_stored_image_name(raw_name: str) -> str:
    if not raw_name:
        return ""

    cleaned = unquote(str(raw_name).strip()).replace("\\", "/")
    parsed = urlparse(cleaned)
    if parsed.scheme and parsed.netloc:
        cleaned = parsed.path

    for prefix in _known_media_prefixes():
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    cleaned = cleaned.lstrip("/")
    parts = [part for part in PurePosixPath(cleaned).parts if part not in {"", "."}]

    for index, part in enumerate(parts):
        if part in KNOWN_UPLOAD_DIRS and index < len(parts) - 1:
            return "/".join(parts[index:])

    return "/".join(parts)


def repair_catalog_media(*, seed_roots: Iterable[Path] | None = None) -> dict:
    seed_paths = _normalize_seed_roots(seed_roots)
    summary = {
        "checked_fields": 0,
        "rewritten_paths": 0,
        "copied_files": 0,
        "missing_files": [],
    }

    for model, field_names in CATALOG_IMAGE_MODELS:
        for instance in model.objects.all().iterator():
            dirty_fields = []

            for field_name in field_names:
                image_field = getattr(instance, field_name)
                stored_name = str(image_field.name or "")
                if not stored_name:
                    continue

                summary["checked_fields"] += 1
                normalized_name = normalize_stored_image_name(stored_name)
                if not normalized_name:
                    continue

                if normalized_name != stored_name:
                    image_field.name = normalized_name
                    dirty_fields.append(field_name)
                    summary["rewritten_paths"] += 1

                if image_field.storage.exists(image_field.name):
                    continue

                source_path = find_seed_file(image_field.name, seed_paths)
                if source_path is None:
                    summary["missing_files"].append(
                        MissingCatalogImage(
                            model=model.__name__,
                            object_id=instance.pk,
                            field_name=field_name,
                            stored_name=image_field.name,
                        )
                    )
                    continue

                with source_path.open("rb") as source_file:
                    saved_name = image_field.storage.save(
                        image_field.name,
                        File(source_file, name=Path(image_field.name).name),
                    )

                if saved_name != image_field.name:
                    image_field.name = saved_name
                    if field_name not in dirty_fields:
                        dirty_fields.append(field_name)

                summary["copied_files"] += 1

            if dirty_fields:
                instance.save(update_fields=dirty_fields)

    return summary


def find_seed_file(target_name: str, seed_roots: Iterable[Path]) -> Path | None:
    normalized_name = normalize_stored_image_name(target_name)
    if not normalized_name:
        return None

    basename = Path(normalized_name).name

    for seed_root in seed_roots:
        direct_match = seed_root / normalized_name
        if direct_match.exists():
            return direct_match

        candidates = list(seed_root.rglob(basename))
        if not candidates:
            continue

        if len(candidates) == 1:
            return candidates[0]

        suffix = Path(normalized_name).as_posix()
        for candidate in candidates:
            if candidate.as_posix().endswith(suffix):
                return candidate

    return None


def _known_media_prefixes() -> list[str]:
    prefixes = ["/media/", "media/"]

    media_url = getattr(settings, "MEDIA_URL", "") or ""
    if media_url and media_url.startswith("/"):
        normalized_media_url = media_url
        if not normalized_media_url.endswith("/"):
            normalized_media_url += "/"
        prefixes.extend([normalized_media_url, normalized_media_url.lstrip("/")])

    return prefixes


def _normalize_seed_roots(seed_roots: Iterable[Path] | None) -> list[Path]:
    configured_roots = list(seed_roots or _default_seed_roots())
    unique_roots = []

    for root in configured_roots:
        path = Path(root)
        if path not in unique_roots and path.exists():
            unique_roots.append(path)

    return unique_roots


def _default_seed_roots() -> list[Path]:
    configured_seed_root = Path(
        getattr(settings, "MEDIA_SEED_ROOT", settings.BASE_DIR / "media")
    )
    return [
        configured_seed_root,
        Path(settings.BASE_DIR) / "media",
    ]
