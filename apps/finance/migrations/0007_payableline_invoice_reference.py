# Boleta de honorarios for creator payables

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0006_bankstatementline_classification'),
    ]

    operations = [
        migrations.AddField(
            model_name='payableline',
            name='invoice_reference',
            field=models.CharField(
                blank=True,
                help_text='Número de boleta de honorarios (obligatorio para creators antes de pagar)',
                max_length=100,
                verbose_name='invoice reference',
            ),
        ),
    ]
