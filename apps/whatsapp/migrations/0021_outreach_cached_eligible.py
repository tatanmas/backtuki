# Outreach: cache de elegibles para no recalcular en cada carga

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0020_rename_whatsapp_gr_config__b0b0b0_idx_whatsapp_gr_config__7d5a88_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupoutreachconfig',
            name='cached_eligible_count',
            field=models.PositiveIntegerField(blank=True, help_text='Last computed count of eligible participants; refreshed on demand.', null=True, verbose_name='Cached eligible count'),
        ),
        migrations.AddField(
            model_name='groupoutreachconfig',
            name='cached_eligible_at',
            field=models.DateTimeField(blank=True, help_text='When eligible_count was last computed.', null=True, verbose_name='Cached eligible at'),
        ),
        migrations.AddField(
            model_name='groupoutreachconfig',
            name='cached_participants_total',
            field=models.PositiveIntegerField(blank=True, help_text='Total participants in group when eligible count was computed.', null=True, verbose_name='Cached participants total'),
        ),
        migrations.AlterField(
            model_name='groupoutreachconfig',
            name='min_delay_seconds',
            field=models.PositiveIntegerField(default=120, help_text='Minimum seconds between two sends (e.g. 600 for 10 min base).', verbose_name='Min delay (seconds)'),
        ),
        migrations.AlterField(
            model_name='groupoutreachconfig',
            name='max_delay_seconds',
            field=models.PositiveIntegerField(default=300, help_text='Maximum seconds between two sends (e.g. 660 = 10 min + 0–60 s jitter).', verbose_name='Max delay (seconds)'),
        ),
    ]
