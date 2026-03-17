# Generated manually for hero slider (like Erasmus)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('travel_guides', '0003_alter_travelguide_destination'),
    ]

    operations = [
        migrations.AddField(
            model_name='travelguide',
            name='hero_slides',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of { "media_id": "uuid", "caption": "" } for hero slider. If non-empty, hero is shown as slider; else hero_media_id/hero_image used.',
                verbose_name='hero slider slides',
            ),
        ),
    ]
