# Auth background slides for login/register flow (managed from SuperAdmin)

from django.db import migrations, models
from django.db.models.deletion import SET_NULL
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_otp_and_creator_flow_types'),
        ('media', '0003_alter_mediaasset_file'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthBackgroundSlide',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated at')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('asset', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=SET_NULL,
                    related_name='auth_background_slides',
                    to='media.mediaasset',
                    verbose_name='asset',
                )),
            ],
            options={
                'verbose_name': 'Auth background slide',
                'verbose_name_plural': 'Auth background slides',
                'ordering': ['order', 'id'],
            },
        ),
    ]
