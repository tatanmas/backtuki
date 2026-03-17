# External revenue: organizer optional (orphan records), already_paid for pre-platform revenue

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0007_payableline_invoice_reference'),
    ]

    operations = [
        migrations.AddField(
            model_name='externalrevenuerecord',
            name='already_paid',
            field=models.BooleanField(
                default=False,
                help_text='Revenue already paid/transferred to organizer before platform (pre-platform events)',
                verbose_name='already paid',
                db_index=True,
            ),
        ),
        migrations.AlterField(
            model_name='externalrevenuerecord',
            name='organizer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name='external_revenue_records',
                to='organizers.organizer',
                verbose_name='organizer',
            ),
        ),
    ]
