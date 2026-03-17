# Generated manually for media library tags (Notion-style filtering)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('media', '0003_alter_mediaasset_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='mediaasset',
            name='tags',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of tag strings for filtering (e.g. ['playa', 'alojamiento'])",
                verbose_name='tags',
            ),
        ),
    ]
