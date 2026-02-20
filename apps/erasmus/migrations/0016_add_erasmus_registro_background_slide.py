# Generated manually for ErasmusRegistroBackgroundSlide

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0015_rename_erasmus_act_slug_idx_erasmus_era_slug_8c9813_idx_and_more'),
        ('media', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ErasmusRegistroBackgroundSlide',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('asset', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='erasmus_registro_background_slides', to='media.mediaasset', verbose_name='asset')),
            ],
            options={
                'verbose_name': 'Erasmus registro background slide',
                'verbose_name_plural': 'Erasmus registro background slides',
                'ordering': ['order', 'id'],
            },
        ),
    ]
