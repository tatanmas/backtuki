"""
Reset the PostgreSQL sequence for users_user.id so the next INSERT gets a valid id.
Use when you see: IntegrityError: duplicate key value violates unique constraint "users_user_pkey"
(e.g. after imports with explicit ids or sequence out of sync).
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Fix users_user id sequence so next insert does not duplicate id."

    def handle(self, *args, **options):
        table = "users_user"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE((SELECT MAX(id) FROM users_user), 1))",
                [table],
            )
            cursor.execute("SELECT last_value FROM users_user_id_seq")
            next_val = cursor.fetchone()[0]
        self.stdout.write(self.style.SUCCESS(f"Sequence users_user_id_seq set; next id will be {next_val + 1}"))
