"""
Crea un superuser dedicado para el Cloudbot (ej. Eva) que interactúa con el API.
Uso: python manage.py create_cloudbot_user --email eva-cloudbot@tuki.cl --password "contraseña_segura"
O con env: CLOUDBOT_EMAIL, CLOUDBOT_PASSWORD (opcional, para scripts/CI).
Si el usuario ya existe: por defecto solo avisa; usa --update-password para actualizar la contraseña.
"""

import os
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Crea un superuser para el Cloudbot (Eva) que pueda autenticarse vía JWT contra el API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default=os.environ.get("CLOUDBOT_EMAIL"),
            help="Email del usuario (o variable CLOUDBOT_EMAIL).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default=os.environ.get("CLOUDBOT_PASSWORD"),
            help="Contraseña (o variable CLOUDBOT_PASSWORD). No dejar en historial en producción.",
        )
        parser.add_argument(
            "--update-password",
            action="store_true",
            help="Si el usuario ya existe, actualizar su contraseña (y asegurar que sea superuser/staff).",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = (options.get("email") or "").strip()
        password = options.get("password") or ""
        update_password = options.get("update_password", False)

        if not email:
            raise CommandError("Falta --email o variable CLOUDBOT_EMAIL.")
        if not password:
            raise CommandError("Falta --password o variable CLOUDBOT_PASSWORD.")

        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            if not update_password:
                self.stdout.write(
                    self.style.WARNING(
                        f"Ya existe un usuario con email: {email}. "
                        "Usa --update-password para cambiar la contraseña y asegurar que sea superuser."
                    )
                )
                return
            existing.set_password(password)
            existing.is_superuser = True
            existing.is_staff = True
            existing.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Usuario actualizado: {existing.email} (superuser, staff, contraseña actualizada)."
                )
            )
            return

        username = email.split("@")[0]
        if User.objects.filter(username=username).exists():
            username = f"{username}-cloudbot"

        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        user.is_staff = True
        user.save()

        self.stdout.write(self.style.SUCCESS(f"Usuario Cloudbot creado: {user.email} (superuser, staff)."))
        self.stdout.write("Configura en el Cloudbot: TUKI_API_BASE_URL, TUKI_EVA_EMAIL (este email), TUKI_EVA_PASSWORD (esta contraseña).")
