# Generated migration for preview_token

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('travel_guides', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='travelguide',
            name='preview_token',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Secret token for viewing draft; used in URL ?preview_token=...',
                max_length=64,
                null=True,
                unique=True,
                verbose_name='preview token',
            ),
        ),
    ]
