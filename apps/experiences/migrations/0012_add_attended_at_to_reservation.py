# Add attended_at to ExperienceReservation (experience completed → creator commission earned)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('experiences', '0011_add_payment_model_and_operator_net_price'),
    ]

    operations = [
        migrations.AddField(
            model_name='experiencereservation',
            name='attended_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When the experience was completed by the customer; used to move creator commission to earned',
                null=True,
                verbose_name='attended at',
            ),
        ),
    ]
