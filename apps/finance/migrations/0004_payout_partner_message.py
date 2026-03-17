from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0003_financeplatformsettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='payout',
            name='partner_message',
            field=models.TextField(blank=True, verbose_name='partner message'),
        ),
    ]
