# Generated manually for storage_backend field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('migration_system', '0003_backupjob'),
    ]

    operations = [
        migrations.AddField(
            model_name='migrationjob',
            name='storage_backend',
            field=models.CharField(
                choices=[('local', 'Local Filesystem'), ('gcs', 'Google Cloud Storage')],
                default='local',
                help_text='Backend donde se guardó el archivo de export',
                max_length=20,
                verbose_name='storage backend'
            ),
        ),
    ]
