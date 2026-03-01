# Allow enabling/disabling the review link independently

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0040_erasmusactivityreview_and_review_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmusactivitypubliclink",
            name="review_link_enabled",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="When False, the review link returns disabled/404 (stops new reviews).",
                verbose_name="review link enabled",
            ),
        ),
    ]
