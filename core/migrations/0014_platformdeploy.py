# PlatformDeploy: registro de cada deploy para historial en Super Admin

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_authbackgroundslide'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlatformDeploy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('deployed_at', models.DateTimeField(db_index=True, help_text='Momento del deploy (coincide con DEPLOYED_AT o registro manual)', verbose_name='Deployed at')),
                ('version', models.CharField(blank=True, default='', help_text='APP_VERSION o commit/tag del deploy', max_length=80, verbose_name='Version')),
                ('source', models.CharField(blank=True, default='startup', help_text='Origen: startup, cloud_build, manual', max_length=50, verbose_name='Source')),
            ],
            options={
                'verbose_name': 'Platform Deploy',
                'verbose_name_plural': 'Platform Deploys',
                'ordering': ['-deployed_at'],
            },
        ),
        migrations.AddIndex(
            model_name='platformdeploy',
            index=models.Index(fields=['-deployed_at'], name='core_platfo_deploye_idx'),
        ),
    ]
