# Add experience_service_fee_rate to Organizer for TUKI Creators

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizers', '0017_studentcenterconfig_selected_experiences'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizer',
            name='experience_service_fee_rate',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Platform fee rate for experiences (e.g., 0.15 for 15%). If null, uses platform default.',
                max_digits=5,
                null=True,
                verbose_name='experience service fee rate',
            ),
        ),
    ]
