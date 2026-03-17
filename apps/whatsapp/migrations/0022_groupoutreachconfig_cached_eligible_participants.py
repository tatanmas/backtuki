# Guardar lista de elegibles en BD para no re-obtener del Node cada vez

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0021_outreach_cached_eligible'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupoutreachconfig',
            name='cached_eligible_participants',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of {id, phone_normalized} for eligible participants; used for sending without re-fetching from Node.',
                verbose_name='Cached eligible participants',
            ),
        ),
    ]
