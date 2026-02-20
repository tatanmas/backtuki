# Generated migration for ErasmusSlideConfig

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0009_add_lead_completion_status_and_nullable_dates'),
        ('media', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ErasmusSlideConfig',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('slide_id', models.CharField(help_text='e.g. sunset-manquehue, valpo-concon, san-cristobal-bike', max_length=100, unique=True, verbose_name='slide id')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('asset', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='erasmus_slide_configs', to='media.mediaasset', verbose_name='asset')),
            ],
            options={
                'verbose_name': 'Erasmus slide config',
                'verbose_name_plural': 'Erasmus slide configs',
                'ordering': ['order', 'slide_id'],
            },
        ),
    ]
