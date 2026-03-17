# Bank statement line classification for reconciliation

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0005_bankaccount_bankstatementline_costcenter_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='bankstatementline',
            name='movement_type',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=30,
                verbose_name='movement type',
            ),
        ),
        migrations.AddField(
            model_name='bankstatementline',
            name='classification_note',
            field=models.TextField(blank=True, verbose_name='classification note'),
        ),
        migrations.AddField(
            model_name='bankstatementline',
            name='matched_payout',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bank_statement_lines',
                to='finance.payout',
                verbose_name='matched payout',
            ),
        ),
        migrations.AddField(
            model_name='bankstatementline',
            name='matched_vendor_payment',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bank_statement_lines',
                to='finance.vendorpayment',
                verbose_name='matched vendor payment',
            ),
        ),
        migrations.AddField(
            model_name='bankstatementline',
            name='matched_processor_settlement',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bank_statement_lines',
                to='finance.processorsettlement',
                verbose_name='matched processor settlement',
            ),
        ),
        migrations.AddField(
            model_name='bankstatementline',
            name='matched_journal_entry',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bank_statement_lines',
                to='finance.journalentry',
                verbose_name='matched journal entry',
            ),
        ),
    ]
