# Generated manually: allow avif in MediaAsset file field

import apps.media.models
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('media', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mediaasset',
            name='file',
            field=models.ImageField(
                upload_to=apps.media.models.get_media_upload_path,
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'gif', 'avif']
                    )
                ],
                verbose_name='file',
            ),
        ),
    ]
