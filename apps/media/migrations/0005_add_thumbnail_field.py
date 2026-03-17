# Generated manually for media library thumbnails (fast grid loading)

from django.db import migrations, models
import apps.media.models


class Migration(migrations.Migration):

    dependencies = [
        ('media', '0004_add_media_asset_tags'),
    ]

    operations = [
        migrations.AddField(
            model_name='mediaasset',
            name='thumbnail',
            field=models.ImageField(
                blank=True,
                editable=False,
                help_text='Auto-generated 300x300 thumbnail for grid display',
                null=True,
                upload_to=apps.media.models.get_thumbnail_upload_path,
                verbose_name='thumbnail',
            ),
        ),
    ]
