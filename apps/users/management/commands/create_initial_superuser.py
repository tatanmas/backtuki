import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Create initial superuser from Django standard env vars if not exists."

    def handle(self, *args, **options):
        User = get_user_model()

        # Use Django's standard environment variables
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not username or not email or not password:
            raise CommandError("Missing DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL or DJANGO_SUPERUSER_PASSWORD")

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' already exists"))
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created successfully"))


