# Erasmus activity inscription flow: flow_type choice + erasmus_activity FK

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_alter_platformuptimeheartbeat_id_and_more'),
        ('erasmus', '0014_add_erasmus_activity_and_instance'),
    ]

    operations = [
        migrations.AddField(
            model_name='platformflow',
            name='erasmus_activity',
            field=models.ForeignKey(
                blank=True,
                help_text='Erasmus activity (paid inscription) associated with this flow (if applicable)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='flows',
                to='erasmus.erasmusactivity',
            ),
        ),
        migrations.AlterField(
            model_name='platformflow',
            name='flow_type',
            field=models.CharField(
                choices=[
                    ('ticket_checkout', 'Ticket Checkout (Events)'),
                    ('experience_booking', 'Experience Booking'),
                    ('accommodation_booking', 'Accommodation Booking'),
                    ('tour_booking', 'Tour Booking'),
                    ('erasmus_registration', 'Erasmus Registration'),
                    ('erasmus_activity_inscription', 'Erasmus Activity Inscription (paid)'),
                ],
                db_index=True,
                help_text='Type of business flow being tracked',
                max_length=50,
            ),
        ),
    ]
