# Platform-wide WhatsApp reservation message templates (singleton)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('whatsapp', '0022_groupoutreachconfig_cached_eligible_participants'),
    ]

    operations = [
        migrations.CreateModel(
            name='WhatsAppReservationMessageConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('config_key', models.CharField(default='default', editable=False, max_length=50, unique=True, verbose_name='config key')),
                ('templates', models.JSONField(
                    blank=True,
                    default=dict,
                    help_text='Dict message_type -> template text. Use {{variable}} for placeholders.',
                    verbose_name='templates',
                )),
            ],
            options={
                'verbose_name': 'WhatsApp reservation message config',
                'verbose_name_plural': 'WhatsApp reservation message configs',
            },
        ),
    ]
