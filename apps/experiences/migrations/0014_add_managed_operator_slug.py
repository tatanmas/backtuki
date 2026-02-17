# Generated manually for carga flow: experiences managed by Tuki store real operator slug

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('experiences', '0013_experience_review_and_reservation_review_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='experience',
            name='managed_operator_slug',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='When managed by Tuki (organizer = Tuki), the real operator identifier e.g. molantours for future transfer',
                max_length=100,
                verbose_name='managed operator slug'
            ),
        ),
    ]
