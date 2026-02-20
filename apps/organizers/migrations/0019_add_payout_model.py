# Add Payout model for tracking transfers to organizers

from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('organizers', '0018_add_experience_service_fee_rate'),
        ('users', '0005_remove_user_organizer_fk'),
    ]

    operations = [
        migrations.CreateModel(
            name='Payout',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('amount', models.DecimalField(
                    decimal_places=2,
                    help_text='Amount transferred to organizer',
                    max_digits=12,
                    validators=[django.core.validators.MinValueValidator(0)],
                    verbose_name='amount'
                )),
                ('paid_at', models.DateTimeField(help_text='When the transfer was made', verbose_name='paid at')),
                ('reference', models.CharField(blank=True, max_length=255, verbose_name='reference')),
                ('organizer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='payouts',
                    to='organizers.organizer'
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='payouts_created',
                    to='users.user'
                )),
            ],
            options={
                'verbose_name': 'payout',
                'verbose_name_plural': 'payouts',
                'ordering': ['-paid_at'],
            },
        ),
    ]
