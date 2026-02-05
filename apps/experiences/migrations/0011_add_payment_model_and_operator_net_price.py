# Add payment_model, operator_net_price, tuki_collects_online for flexible experience pricing

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('experiences', '0010_add_creator_commission_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='experience',
            name='payment_model',
            field=models.CharField(
                choices=[('full_upfront', 'Full upfront (client pays total online)'), ('deposit_only', 'Deposit only (client pays commission online, rest at experience)')],
                default='full_upfront',
                help_text='full_upfront: Tuki collects total. deposit_only: Tuki collects commission, client pays rest to operator.',
                max_length=20,
                verbose_name='payment model',
            ),
        ),
        migrations.AddField(
            model_name='experience',
            name='operator_net_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Price operator receives per person/base. If null, inferred from price in full_upfront.',
                max_digits=10,
                null=True,
                verbose_name='operator net price',
            ),
        ),
        migrations.AddField(
            model_name='experience',
            name='tuki_collects_online',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Amount Tuki collects online (commission for deposit_only). If null, calculated.',
                max_digits=10,
                null=True,
                verbose_name='tuki collects online',
            ),
        ),
    ]
