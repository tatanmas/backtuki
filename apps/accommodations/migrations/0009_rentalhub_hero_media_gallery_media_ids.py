# RentalHub: hero_media_id and gallery_media_ids for superadmin image library

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accommodations", "0008_unit_type_tower_flexible"),
    ]

    operations = [
        migrations.AddField(
            model_name="rentalhub",
            name="hero_media_id",
            field=models.UUIDField(
                blank=True,
                help_text="MediaAsset UUID for hero image (superadmin library)",
                null=True,
                verbose_name="hero image from media library",
            ),
        ),
        migrations.AddField(
            model_name="rentalhub",
            name="gallery_media_ids",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of MediaAsset UUIDs for the hub gallery (superadmin library)",
                verbose_name="gallery media asset IDs",
            ),
        ),
    ]
