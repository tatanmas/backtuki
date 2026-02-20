# Generated manually: community visibility preferences

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0017_community_fields_and_profile_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='erasmuslead',
            name='community_show_dates',
            field=models.BooleanField(default=True, help_text='Show arrival/departure dates on community profile', verbose_name='community show dates'),
        ),
        migrations.AddField(
            model_name='erasmuslead',
            name='community_show_age',
            field=models.BooleanField(default=True, help_text='Show age (from birth_date) on community profile', verbose_name='community show age'),
        ),
        migrations.AddField(
            model_name='erasmuslead',
            name='community_show_whatsapp',
            field=models.BooleanField(default=False, help_text='Show WhatsApp on community profile', verbose_name='community show whatsapp'),
        ),
    ]
