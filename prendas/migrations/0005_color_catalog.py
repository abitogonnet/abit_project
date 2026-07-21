import unicodedata

from django.db import migrations, models


DEFAULT_COLORS = [
    "Azul Oscuro", "Azul Francia", "Blanca", "Gris Perla", "Gris Topo",
    "Celeste", "Rosa", "Verde Pistacho", "Verde Oscuro", "Petroleo",
    "Bordo", "Violeta", "Beige", "Marron", "Negro", "Gris",
]
RESTRICTED_CATEGORIES = {"SACO", "PANTALON", "CAMISA", "ZAPATOS", "CINTURON"}
SAFE_ALIASES = {
    "azul osc": "Azul Oscuro", "azul ocs": "Azul Oscuro", "osc": "Azul Oscuro",
    "verde osuro": "Verde Oscuro", "pistacho": "Verde Pistacho",
}


def key(value):
    clean = " ".join((value or "").split()).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", clean) if not unicodedata.combining(c))


def canonical_name(value):
    clean = " ".join((value or "").split())
    alias = SAFE_ALIASES.get(key(clean))
    if alias:
        return alias
    return " ".join(word.capitalize() for word in clean.split())


def build_catalog_and_normalize(apps, schema_editor):
    Color = apps.get_model("prendas", "Color")
    Prenda = apps.get_model("prendas", "Prenda")
    canonical = {}
    for name in DEFAULT_COLORS:
        canonical[key(name)] = name
    for value in Prenda.objects.filter(categoria__in=RESTRICTED_CATEGORIES).exclude(color="").values_list("color", flat=True).distinct():
        normalized = canonical_name(value)
        canonical.setdefault(key(normalized), normalized)
    for normalized_key, name in canonical.items():
        Color.objects.get_or_create(clave_normalizada=normalized_key, defaults={"nombre": name})
    for prenda in Prenda.objects.filter(categoria__in=RESTRICTED_CATEGORIES).exclude(color="").iterator():
        normalized = canonical.get(key(canonical_name(prenda.color)), canonical_name(prenda.color))
        if prenda.color != normalized:
            Prenda.objects.filter(pk=prenda.pk).update(color=normalized)


class Migration(migrations.Migration):
    dependencies = [("prendas", "0004_normalize_restricted_colors")]
    operations = [
        migrations.CreateModel(
            name="Color",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=40)),
                ("clave_normalizada", models.CharField(editable=False, max_length=40, unique=True)),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["nombre"]},
        ),
        migrations.RunPython(build_catalog_and_normalize, migrations.RunPython.noop),
    ]
