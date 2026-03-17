"""Tests para services_commercial_policy."""

from datetime import date, timedelta

from django.test import TestCase

from apps.finance.services_commercial_policy import (
    get_effective_commercial_mode,
    resolve_commercial_policy,
    snapshot_policy,
)

from .test_fixtures import FinanceFixturesMixin


class CommercialPolicyServiceTests(FinanceFixturesMixin, TestCase):
    def setUp(self):
        self.create_organizer()
        self.create_commercial_policy(commercial_mode='collect_total')

    def test_resolve_organizer_default_policy(self):
        policy = resolve_commercial_policy(organizer=self.organizer)
        self.assertIsNotNone(policy)
        self.assertEqual(policy.commercial_mode, 'collect_total')
        self.assertEqual(policy.scope_type, 'organizer_default')

    def test_resolve_returns_none_when_no_policy(self):
        from apps.organizers.models import Organizer
        other = Organizer.objects.create(
            name='Other Org',
            slug='other-org',
            contact_email='other@test.com',
            status='active',
        )
        policy = resolve_commercial_policy(organizer=other)
        self.assertIsNone(policy)

    def test_snapshot_policy_serializes(self):
        policy = resolve_commercial_policy(organizer=self.organizer)
        snap = snapshot_policy(policy)
        self.assertIn('commercial_mode', snap)
        self.assertEqual(snap['commercial_mode'], 'collect_total')
        self.assertIn('id', snap)

    def test_snapshot_none_returns_defaults(self):
        snap = snapshot_policy(None)
        self.assertIn('commercial_mode', snap)
        self.assertEqual(snap['commercial_mode'], 'collect_total')

    def test_get_effective_commercial_mode(self):
        policy = resolve_commercial_policy(organizer=self.organizer)
        mode = get_effective_commercial_mode(policy)
        self.assertEqual(mode, 'collect_total')
        self.assertEqual(get_effective_commercial_mode(None), 'collect_total')
