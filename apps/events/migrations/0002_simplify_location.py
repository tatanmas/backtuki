# Generated migration for location simplification

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0001_initial'),
    ]

    operations = [
        # Remove old fields from Location
        migrations.RemoveField(
            model_name='location',
            name='city',
        ),
        migrations.RemoveField(
            model_name='location',
            name='country',
        ),
        migrations.RemoveField(
            model_name='location',
            name='latitude',
        ),
        migrations.RemoveField(
            model_name='location',
            name='longitude',
        ),
        migrations.RemoveField(
            model_name='location',
            name='venue_details',
        ),
        migrations.RemoveField(
            model_name='location',
            name='capacity',
        ),
        # Modify existing fields
        migrations.AlterField(
            model_name='location',
            name='name',
            field=models.CharField(help_text='Name of the venue or platform', max_length=255, verbose_name='name'),
        ),
        migrations.AlterField(
            model_name='location',
            name='address',
            field=models.TextField(help_text='Physical address or virtual meeting URL', verbose_name='address'),
        ),
    ]
