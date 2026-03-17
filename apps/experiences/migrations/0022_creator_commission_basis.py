# Creator commission: support % of total OR % of Tuki commission

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('experiences', '0021_rename_exp_res_source_idx_experiences_source__aec541_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='experience',
            name='creator_commission_basis',
            field=models.CharField(
                choices=[
                    ('pct_tuki_commission', 'Porcentaje de comisión Tuki'),
                    ('pct_total', 'Porcentaje del total de venta'),
                ],
                default='pct_tuki_commission',
                help_text='Base para calcular comisión: pct_tuki_commission = % de lo que cobra Tuki; pct_total = % del total vendido.',
                max_length=30,
                verbose_name='creator commission basis',
            ),
        ),
    ]
