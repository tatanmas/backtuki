import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0002_rename_finance_paya_payee_i_22cc68_idx_finance_pay_payee_i_9415d6_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='FinancePlatformSettings',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('default_next_payment_date', models.DateField(blank=True, db_index=True, null=True, verbose_name='default next payment date')),
                ('default_schedule_frequency', models.CharField(default='manual', max_length=20, verbose_name='default schedule frequency')),
                ('payout_notes', models.TextField(blank=True, verbose_name='payout notes')),
            ],
            options={
                'verbose_name': 'finance platform settings',
                'verbose_name_plural': 'finance platform settings',
            },
        ),
    ]
