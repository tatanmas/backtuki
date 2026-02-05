# Add creator FK to PlatformFlow for TUKI Creators attribution

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('creators', '0001_creators_initial'),
        ('core', '0004_add_country_model'),
    ]

    operations = [
        migrations.AddField(
            model_name='platformflow',
            name='creator',
            field=models.ForeignKey(
                blank=True,
                help_text='Creator (influencer) who referred this flow (for commission)',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='flows',
                to='creators.creatorprofile',
            ),
        ),
    ]
