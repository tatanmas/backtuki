# Generated migration for LandingDestination and LandingDestinationExperience

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='LandingDestination',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('name', models.CharField(db_index=True, max_length=255, verbose_name='name')),
                ('slug', models.SlugField(db_index=True, max_length=255, unique=True, verbose_name='slug')),
                ('country', models.CharField(default='Chile', max_length=255, verbose_name='country')),
                ('region', models.CharField(blank=True, max_length=255, verbose_name='region')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('hero_image', models.URLField(blank=True, max_length=500, verbose_name='hero image')),
                ('temperature', models.IntegerField(blank=True, null=True, verbose_name='temperature')),
                ('local_time', models.CharField(blank=True, max_length=50, verbose_name='local time')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('images', models.JSONField(default=list, help_text='List of image URLs for the destination gallery', verbose_name='gallery images')),
                ('travel_guides', models.JSONField(default=list, help_text='List of {id, title, image, description?, author?}', verbose_name='travel guides')),
                ('transportation', models.JSONField(default=list, help_text='List of {id, type, icon, title, description, price?}', verbose_name='transportation options')),
                ('accommodation_ids', models.JSONField(default=list, help_text='List of accommodation UUIDs (for when accommodations app is populated)', verbose_name='accommodation IDs')),
                ('featured_type', models.CharField(blank=True, choices=[('experience', 'Experience'), ('event', 'Event'), ('accommodation', 'Accommodation')], max_length=20, null=True, verbose_name='featured type')),
                ('featured_id', models.UUIDField(blank=True, null=True, verbose_name='featured entity ID')),
            ],
            options={
                'verbose_name': 'Landing Destination',
                'verbose_name_plural': 'Landing Destinations',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='LandingDestinationExperience',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('experience_id', models.UUIDField(db_index=True, verbose_name='experience ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('destination', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='destination_experiences', to='landing_destinations.landingdestination')),
            ],
            options={
                'verbose_name': 'Landing destination experience',
                'verbose_name_plural': 'Landing destination experiences',
                'ordering': ['order', 'experience_id'],
                'unique_together': {('destination', 'experience_id')},
            },
        ),
    ]
