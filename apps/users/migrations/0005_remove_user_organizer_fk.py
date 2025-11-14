from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_add_guest_user_fields"),
        ("organizers", "0012_add_service_fee_rate"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="organizer",
        ),
    ]

