from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from django.core.files import File

from .media_repair import CATALOG_IMAGE_MODELS, normalize_stored_image_name


@dataclass
class CatalogMediaMigrationResult:
    references_checked: int = 0
    files_found: int = 0
    migrated: int = 0
    already_persistent: int = 0
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def migrate_catalog_media(
    *,
    source_root,
    destination_storage,
    dry_run=False,
    check_destination=True,
):
    source_root = Path(source_root).resolve()
    result = CatalogMediaMigrationResult()

    for model, field_names in CATALOG_IMAGE_MODELS:
        for instance in model.objects.all().iterator():
            for field_name in field_names:
                field_file = getattr(instance, field_name)
                raw_name = getattr(field_file, "name", "") or ""
                if not raw_name:
                    continue

                result.references_checked += 1
                stored_name = normalize_stored_image_name(raw_name)
                reference = (
                    f"{model.__name__}#{instance.pk}.{field_name} "
                    f"({raw_name})"
                )
                if not stored_name:
                    result.missing.append(reference)
                    continue

                try:
                    if (
                        check_destination
                        and destination_storage.exists(stored_name)
                    ):
                        result.already_persistent += 1
                        if raw_name != stored_name and not dry_run:
                            model.objects.filter(pk=instance.pk).update(
                                **{field_name: stored_name}
                            )
                        continue
                except Exception as exc:
                    result.errors.append(
                        f"{reference}: no se pudo consultar destino: {exc}"
                    )
                    continue

                source_path = _safe_source_path(source_root, stored_name)
                if source_path is None or not source_path.is_file():
                    result.missing.append(reference)
                    continue

                result.files_found += 1
                if dry_run:
                    result.migrated += 1
                    continue

                saved_name = ""
                try:
                    with source_path.open("rb") as source:
                        saved_name = destination_storage.save(
                            stored_name,
                            File(source, name=source_path.name),
                        )
                    model.objects.filter(pk=instance.pk).update(
                        **{field_name: saved_name}
                    )
                    result.migrated += 1
                except Exception as exc:
                    if saved_name:
                        try:
                            destination_storage.delete(saved_name)
                        except Exception:
                            pass
                    result.errors.append(f"{reference}: {exc}")

    return result


def _safe_source_path(source_root, stored_name):
    relative = PurePosixPath(stored_name)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = (source_root / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(source_root)
    except ValueError:
        return None
    return candidate
