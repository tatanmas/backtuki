# Erasmus activities: same structure as Experience (itinerary, meeting point, included/not_included, duration)
# Instances: optional start_time / end_time

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("erasmus", "0027_add_deportes_extra_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="erasmusactivity",
            name="location_name",
            field=models.CharField(
                blank=True,
                help_text="Meeting point / place name",
                max_length=255,
                verbose_name="meeting point name",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivity",
            name="location_address",
            field=models.TextField(
                blank=True,
                help_text="Full address for meeting point",
                verbose_name="meeting point address",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivity",
            name="duration_minutes",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Optional duration (e.g. 120 for 2h)",
                null=True,
                verbose_name="duration in minutes",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivity",
            name="included",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of what's included (same as Experience)",
                verbose_name="included",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivity",
            name="not_included",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of what's not included (same as Experience)",
                verbose_name="not included",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivity",
            name="itinerary",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="List of items: time (or start_time/end_time), title, description (same as Experience)",
                verbose_name="itinerary",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="start_time",
            field=models.TimeField(
                blank=True,
                help_text="Optional start time for this instance (HH:MM)",
                null=True,
                verbose_name="start time",
            ),
        ),
        migrations.AddField(
            model_name="erasmusactivityinstance",
            name="end_time",
            field=models.TimeField(
                blank=True,
                help_text="Optional end time for this instance (HH:MM)",
                null=True,
                verbose_name="end time",
            ),
        ),
    ]
