# Migration: AccommodationExtraCharge model + pricing_snapshot on AccommodationReservation (cobros adicionales v1.5)

import uuid
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('accommodations', '0017_add_default_whatsapp_group_hotel_rental_hub'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccommodationExtraCharge',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(verbose_name='Updated at')),
                ('code', models.CharField(help_text='Unique per accommodation; used in selected_options. Immutable once created.', max_length=64, verbose_name='code')),
                ('name', models.CharField(max_length=255, verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('charge_type', models.CharField(choices=[('per_stay', 'Per stay'), ('per_night', 'Per night')], default='per_stay', max_length=20, verbose_name='charge type')),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(0)], verbose_name='amount')),
                ('currency', models.CharField(blank=True, help_text='Null = accommodation currency. If different from accommodation, rejected in v1.', max_length=3, null=True, verbose_name='currency')),
                ('is_optional', models.BooleanField(default=True, help_text='True = guest chooses; False = always applied (mandatory).', verbose_name='optional')),
                ('default_quantity', models.PositiveIntegerField(default=1, help_text='For optional extras: default quantity in selector. Not used for mandatory.', verbose_name='default quantity')),
                ('max_quantity', models.PositiveIntegerField(blank=True, help_text='Null = no cap. Only applies to optional extras.', null=True, verbose_name='max quantity')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('display_order', models.PositiveIntegerField(default=0, verbose_name='display order')),
                ('accommodation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='extra_charges', to='accommodations.accommodation', verbose_name='accommodation')),
            ],
            options={
                'verbose_name': 'Accommodation extra charge',
                'verbose_name_plural': 'Accommodation extra charges',
                'ordering': ['display_order', 'name'],
                'unique_together': {('accommodation', 'code')},
            },
        ),
        migrations.AddField(
            model_name='accommodationreservation',
            name='pricing_snapshot',
            field=models.JSONField(blank=True, help_text='Immutable snapshot at reservation creation: base, extras, total. Legacy reservations have null.', null=True, verbose_name='pricing snapshot'),
        ),
    ]
