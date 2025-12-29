# Generated manually for adding flow FK to ExperienceReservation

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_add_platform_flow_monitoring'),
        ('experiences', '0002_experience_booking_horizon_days_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='experiencereservation',
            name='flow',
            field=models.ForeignKey(
                blank=True,
                help_text='Platform flow tracking this reservation (for traceability)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='experience_reservations',
                to='core.platformflow',
                verbose_name='platform flow'
            ),
        ),
    ]

