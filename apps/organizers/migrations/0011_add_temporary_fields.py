# Generated migration for temporary organizer fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizers', '0009_alter_organizer_organizer_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizer',
            name='is_temporary',
            field=models.BooleanField(
                default=False,
                help_text='Si el organizador es temporal (antes de validar email)',
                verbose_name='is temporary'
            ),
        ),
        migrations.AddField(
            model_name='organizer',
            name='email_validated',
            field=models.BooleanField(
                default=False,
                help_text='Si el email del organizador ha sido validado',
                verbose_name='email validated'
            ),
        ),
        migrations.AlterField(
            model_name='organizer',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('pending_validation', 'Pending Email Validation'),
                    ('onboarding', 'Onboarding'),
                    ('active', 'Active'),
                    ('suspended', 'Suspended'),
                ],
                default='pending',
                max_length=20,
                verbose_name='status'
            ),
        ),
    ]
