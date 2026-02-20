# Generated migration for ErasmusTimelineItem

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0010_erasmusslideconfig'),
        ('experiences', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ErasmusTimelineItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('title_es', models.CharField(max_length=255, verbose_name='title Spanish')),
                ('title_en', models.CharField(blank=True, max_length=255, verbose_name='title English')),
                ('location', models.CharField(blank=True, max_length=255, verbose_name='location')),
                ('image', models.URLField(blank=True, max_length=500, verbose_name='image URL')),
                ('scheduled_date', models.DateField(blank=True, null=True, verbose_name='scheduled date')),
                ('display_order', models.PositiveIntegerField(default=0, verbose_name='display order')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('experience', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='erasmus_timeline_items', to='experiences.experience', verbose_name='experience')),
            ],
            options={
                'verbose_name': 'Erasmus timeline item',
                'verbose_name_plural': 'Erasmus timeline items',
                'ordering': ['display_order', 'scheduled_date', 'created_at'],
            },
        ),
    ]
