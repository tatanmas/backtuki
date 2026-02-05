# Generated migration: media library refs + lat/lon + events

from django.db import migrations, models
from django.db.models.deletion import CASCADE


class Migration(migrations.Migration):

    dependencies = [
        ('landing_destinations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='landingdestination',
            name='hero_media_id',
            field=models.UUIDField(blank=True, null=True, verbose_name='hero image from media library'),
        ),
        migrations.AddField(
            model_name='landingdestination',
            name='gallery_media_ids',
            field=models.JSONField(
                default=list,
                help_text='List of MediaAsset UUIDs for the destination gallery',
                verbose_name='gallery image IDs from media library',
            ),
        ),
        migrations.AddField(
            model_name='landingdestination',
            name='latitude',
            field=models.FloatField(blank=True, null=True, verbose_name='latitude'),
        ),
        migrations.AddField(
            model_name='landingdestination',
            name='longitude',
            field=models.FloatField(blank=True, null=True, verbose_name='longitude'),
        ),
        migrations.AlterField(
            model_name='landingdestination',
            name='hero_image',
            field=models.URLField(blank=True, max_length=500, verbose_name='hero image URL fallback'),
        ),
        migrations.CreateModel(
            name='LandingDestinationEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id', models.UUIDField(db_index=True, verbose_name='event ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('destination', models.ForeignKey(on_delete=CASCADE, related_name='destination_events', to='landing_destinations.landingdestination')),
            ],
            options={
                'verbose_name': 'Landing destination event',
                'verbose_name_plural': 'Landing destination events',
                'ordering': ['order', 'event_id'],
                'unique_together': {('destination', 'event_id')},
            },
        ),
    ]
