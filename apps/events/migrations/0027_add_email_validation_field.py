# Generated migration for email validation field in events

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0024_enterprise_coupon_holds'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='requires_email_validation',
            field=models.BooleanField(
                default=False,
                help_text='Si el evento requiere validación de email para publicarse',
                verbose_name='requires email validation'
            ),
        ),
    ]
