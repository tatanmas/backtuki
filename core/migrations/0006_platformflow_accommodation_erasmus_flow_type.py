# Add accommodation FK to PlatformFlow; erasmus_registration flow type (choice in code only)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accommodations', '0001_initial'),
        ('core', '0005_add_flow_creator'),
    ]

    operations = [
        migrations.AddField(
            model_name='platformflow',
            name='accommodation',
            field=models.ForeignKey(
                blank=True,
                help_text='Accommodation associated with this flow (if applicable)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='flows',
                to='accommodations.accommodation',
            ),
        ),
    ]
