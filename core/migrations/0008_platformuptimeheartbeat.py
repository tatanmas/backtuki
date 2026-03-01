# Generated migration for PlatformUptimeHeartbeat

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_alter_platformflow_flow_type_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlatformUptimeHeartbeat',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('recorded_at', models.DateTimeField(db_index=True, help_text='Momento en que se registró el heartbeat (plataforma arriba)', verbose_name='Recorded at')),
                ('source', models.CharField(blank=True, default='celery', help_text='Origen del heartbeat (celery, management_command, etc.)', max_length=50)),
            ],
            options={
                'verbose_name': 'Platform Uptime Heartbeat',
                'verbose_name_plural': 'Platform Uptime Heartbeats',
                'ordering': ['recorded_at'],
            },
        ),
    ]
