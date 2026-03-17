"""
Generate thumbnails for MediaAssets that don't have one.
Run: python manage.py generate_media_thumbnails [--batch 100] [--dry-run]
"""

import logging
from django.core.management.base import BaseCommand
from apps.media.models import MediaAsset

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Generate thumbnails for MediaAssets without one"

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch',
            type=int,
            default=100,
            help='Process up to N assets per run (default 100)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only count, do not generate',
        )

    def handle(self, *args, **options):
        batch = options['batch']
        dry_run = options['dry_run']
        qs = MediaAsset.objects.filter(thumbnail__isnull=True, deleted_at__isnull=True).exclude(file='')[:batch]
        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('No assets need thumbnails.'))
            return
        if dry_run:
            self.stdout.write(f'Would generate {total} thumbnail(s). Run without --dry-run to apply.')
            return
        ok = 0
        fail = 0
        for asset in qs:
            try:
                asset.generate_thumbnail()
                ok += 1
                self.stdout.write(f'  OK: {asset.id} {asset.original_filename[:40]}')
            except Exception as e:
                fail += 1
                logger.warning('Thumbnail failed for %s: %s', asset.id, e)
                self.stdout.write(self.style.WARNING(f'  FAIL: {asset.id} {e}'))
        self.stdout.write(self.style.SUCCESS(f'Done: {ok} generated, {fail} failed.'))
