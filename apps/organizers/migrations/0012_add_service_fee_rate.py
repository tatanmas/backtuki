# Generated manually for service fee hierarchy implementation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizers', '0011_add_temporary_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizer',
            name='default_service_fee_rate',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Default service fee rate for this organizer (e.g., 0.15 for 15%). If null, uses platform default.',
                max_digits=5,
                null=True,
                verbose_name='default service fee rate'
            ),
        ),
    ]
