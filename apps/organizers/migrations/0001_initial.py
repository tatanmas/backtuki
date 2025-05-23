# Generated by Django 4.2.8 on 2025-04-30 20:07

from django.db import migrations, models
import django.db.models.deletion
import django_tenants.postgresql_backend.base
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Domain',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('domain', models.CharField(db_index=True, max_length=253, unique=True)),
                ('is_primary', models.BooleanField(db_index=True, default=True)),
            ],
            options={
                'verbose_name': 'domain',
                'verbose_name_plural': 'domains',
            },
        ),
        migrations.CreateModel(
            name='Organizer',
            fields=[
                ('schema_name', models.CharField(db_index=True, max_length=63, unique=True, validators=[django_tenants.postgresql_backend.base._check_schema_name])),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255, verbose_name='name')),
                ('slug', models.SlugField(unique=True, verbose_name='slug')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('logo', models.ImageField(blank=True, null=True, upload_to='organizers/logos', verbose_name='logo')),
                ('website', models.URLField(blank=True, verbose_name='website')),
                ('contact_email', models.EmailField(max_length=254, verbose_name='contact email')),
                ('contact_phone', models.CharField(blank=True, max_length=30, verbose_name='contact phone')),
                ('address', models.CharField(blank=True, max_length=255, verbose_name='address')),
                ('city', models.CharField(blank=True, max_length=100, verbose_name='city')),
                ('country', models.CharField(blank=True, max_length=100, verbose_name='country')),
                ('has_events_module', models.BooleanField(default=True, verbose_name='has events module')),
                ('has_accommodation_module', models.BooleanField(default=False, verbose_name='has accommodation module')),
                ('has_experience_module', models.BooleanField(default=False, verbose_name='has experience module')),
            ],
            options={
                'verbose_name': 'organizer',
                'verbose_name_plural': 'organizers',
            },
        ),
        migrations.CreateModel(
            name='OrganizerSubscription',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('plan', models.CharField(choices=[('free', 'Free'), ('basic', 'Basic'), ('premium', 'Premium'), ('enterprise', 'Enterprise')], max_length=20, verbose_name='plan')),
                ('status', models.CharField(choices=[('active', 'Active'), ('trial', 'Trial'), ('canceled', 'Canceled'), ('expired', 'Expired')], max_length=20, verbose_name='status')),
                ('start_date', models.DateField(verbose_name='start date')),
                ('end_date', models.DateField(blank=True, null=True, verbose_name='end date')),
                ('max_events', models.PositiveIntegerField(default=0, verbose_name='max events')),
                ('max_accommodations', models.PositiveIntegerField(default=0, verbose_name='max accommodations')),
                ('max_experiences', models.PositiveIntegerField(default=0, verbose_name='max experiences')),
                ('max_storage_gb', models.PositiveIntegerField(default=0, verbose_name='max storage (GB)')),
                ('max_users', models.PositiveIntegerField(default=1, verbose_name='max users')),
            ],
            options={
                'verbose_name': 'organizer subscription',
                'verbose_name_plural': 'organizer subscriptions',
                'ordering': ['-start_date'],
            },
        ),
        migrations.CreateModel(
            name='OrganizerUser',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('is_admin', models.BooleanField(default=False, verbose_name='is admin')),
                ('can_manage_events', models.BooleanField(default=False, verbose_name='can manage events')),
                ('can_manage_accommodations', models.BooleanField(default=False, verbose_name='can manage accommodations')),
                ('can_manage_experiences', models.BooleanField(default=False, verbose_name='can manage experiences')),
                ('can_view_reports', models.BooleanField(default=False, verbose_name='can view reports')),
                ('can_manage_settings', models.BooleanField(default=False, verbose_name='can manage settings')),
                ('organizer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='organizer_users', to='organizers.organizer')),
            ],
            options={
                'verbose_name': 'organizer user',
                'verbose_name_plural': 'organizer users',
            },
        ),
    ]
