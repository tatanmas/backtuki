# Generated manually for ErasmusSlideConfig caption

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('erasmus', '0012_add_requested_whatsapp_approval'),
    ]

    operations = [
        migrations.AddField(
            model_name='erasmusslideconfig',
            name='caption',
            field=models.CharField(
                blank=True,
                help_text='Short legend shown on the slide (e.g. place name)',
                max_length=255,
                verbose_name='caption',
            ),
        ),
    ]
