# Migration: add gallery_items and backfill from gallery_media_ids

from django.db import migrations, models


def backfill_gallery_items(apps, schema_editor):
    Accommodation = apps.get_model("accommodations", "Accommodation")
    for acc in Accommodation.objects.all():
        if not acc.gallery_media_ids:
            continue
        acc.gallery_items = [
            {"media_id": str(mid), "room_category": None, "sort_order": i}
            for i, mid in enumerate(acc.gallery_media_ids)
        ]
        acc.save(update_fields=["gallery_items"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0002_accommodation_reservation"),
    ]

    operations = [
        migrations.AddField(
            model_name="accommodation",
            name="gallery_items",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of {media_id, room_category, sort_order}. Order of display; room_category from ROOM_CATEGORIES or null. When saving, gallery_media_ids is synced from this.",
                verbose_name="gallery items with order and room category",
            ),
        ),
        migrations.RunPython(backfill_gallery_items, noop_reverse),
    ]
