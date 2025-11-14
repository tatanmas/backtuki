from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count

from apps.organizers.models import OrganizerUser


class Command(BaseCommand):
    help = (
        "Validate organizer memberships and optionally backfill missing "
        "OrganizerUser links for users marked as organizers."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Create missing OrganizerUser records and sync organizer flags.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit the number of users processed in each category.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        limit = options["limit"]
        User = get_user_model()

        self.stdout.write(self.style.MIGRATE_HEADING("Organizer membership audit"))
        self.stdout.write(f"Dry-run mode: {not apply_changes}")

        users_with_roles = (
            User.objects.annotate(role_count=Count("organizer_roles"))
            .filter(role_count__gt=0)
        )
        users_with_roles_missing_flag = users_with_roles.filter(is_organizer=False)

        users_flagged_without_roles = (
            User.objects.filter(is_organizer=True)
            .annotate(role_count=Count("organizer_roles"))
            .filter(role_count=0)
        )

        self._display_users(
            "Users with organizer roles but flag disabled",
            users_with_roles_missing_flag,
            limit,
        )
        self._display_users(
            "Users flagged as organizer but lacking OrganizerUser membership",
            users_flagged_without_roles,
            limit,
        )

        if apply_changes:
            with transaction.atomic():
                updated = users_with_roles_missing_flag.update(is_organizer=True)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated organizer flag for {updated} users with existing roles."
                    )
                )

                created_links = 0
                manual_follow_up = []
                for user in users_flagged_without_roles:
                    if limit is not None and created_links >= limit:
                        break
                    organizer = getattr(user, "organizer", None)
                    if not organizer:
                        manual_follow_up.append(user)
                        continue

                    organizer_user, created = OrganizerUser.objects.get_or_create(
                        organizer=organizer,
                        user=user,
                        defaults={
                            "is_admin": True,
                            "can_manage_events": True,
                            "can_manage_accommodations": True,
                            "can_manage_experiences": True,
                            "can_view_reports": True,
                            "can_manage_settings": True,
                        },
                    )
                    if created:
                        created_links += 1

                if created_links:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Created {created_links} missing OrganizerUser memberships."
                        )
                    )

                if manual_follow_up:
                    self.stdout.write(self.style.WARNING("Users requiring manual review:"))
                    for user in manual_follow_up:
                        self.stdout.write(f" - {user.id} | {user.email} (no organizer FK)")

        self.stdout.write(self.style.SUCCESS("Audit completed."))

    def _display_users(self, title, queryset, limit):
        total = queryset.count()
        self.stdout.write(self.style.NOTICE(f"{title}: {total}"))
        if total == 0:
            return

        sample = queryset.order_by("id")
        if limit:
            sample = sample[:limit]

        for user in sample:
            organizer = getattr(user, "organizer", None)
            organizer_id = getattr(organizer, "id", None)
            self.stdout.write(
                f" - {user.id} | {user.email} | organizer_fk={organizer_id} "
                f"| roles={user.organizer_roles.count()}"
            )

