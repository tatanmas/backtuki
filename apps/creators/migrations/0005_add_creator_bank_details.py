# Generated manually for plan: TUKI Creators bank_details

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('creators', '0004_add_creator_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='creatorprofile',
            name='bank_details',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Optional: { bank_name, account_type, account_number, rut?, holder_name } for payouts',
                verbose_name='bank details',
            ),
        ),
    ]
