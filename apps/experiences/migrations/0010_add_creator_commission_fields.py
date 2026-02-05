# Add platform fee, creator commission to Experience and creator fields to ExperienceReservation

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('creators', '0001_creators_initial'),
        ('experiences', '0009_studentcentertimelineitem_studentinterest_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='experience',
            name='platform_service_fee_rate',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Platform fee rate (e.g., 0.15 = 15%). If null, uses organizer or platform default.',
                max_digits=5,
                null=True,
                verbose_name='platform service fee rate',
            ),
        ),
        migrations.AddField(
            model_name='experience',
            name='creator_commission_rate',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Creator share of platform fee (e.g., 0.5 = 50%). If null, uses platform default.',
                max_digits=5,
                null=True,
                verbose_name='creator commission rate',
            ),
        ),
        migrations.AddField(
            model_name='experiencereservation',
            name='creator',
            field=models.ForeignKey(
                blank=True,
                help_text='Creator who referred this booking (for commission)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='experience_reservations',
                to='creators.creatorprofile',
                verbose_name='creator',
            ),
        ),
        migrations.AddField(
            model_name='experiencereservation',
            name='creator_commission_amount',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Amount to pay creator (snapshot at book time)',
                max_digits=10,
                verbose_name='creator commission amount',
            ),
        ),
        migrations.AddField(
            model_name='experiencereservation',
            name='creator_commission_status',
            field=models.CharField(
                blank=True,
                choices=[('pending', 'Pending'), ('earned', 'Earned'), ('paid', 'Paid'), ('reversed', 'Reversed')],
                max_length=20,
                null=True,
                verbose_name='creator commission status',
            ),
        ),
    ]
