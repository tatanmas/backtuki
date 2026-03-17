"""Fixtures y mixins para tests de finance – datos realistas."""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.events.models import Event, Order
from apps.finance.models import (
    CommercialPolicy,
    ExpenseCategory,
    ExternalRevenueRecord,
    LedgerAccount,
    PayableLine,
    PayeeAccount,
    PayeeSchedule,
    SettlementRun,
    TaxTreatment,
    Vendor,
    VendorBill,
)
from apps.organizers.models import Organizer

User = get_user_model()


class FinanceFixturesMixin:
    """Mixin que crea datos base para tests de finance."""

    def create_superuser(self):
        self.superuser = User.objects.create_superuser(
            username='finance-admin',
            email='finance-admin@test.com',
            password='testpass123',
        )
        return self.superuser

    def create_organizer(self, name='Test Organizer', slug='test-org'):
        self.organizer = Organizer.objects.create(
            name=name,
            slug=slug,
            contact_email=f'{slug}@test.com',
            status='active',
        )
        return self.organizer

    def create_payee(self, organizer=None, actor_type='organizer'):
        organizer = organizer or getattr(self, 'organizer', None)
        if not organizer:
            self.create_organizer()
            organizer = self.organizer

        account_key = f'organizer:{organizer.id}' if actor_type == 'organizer' else f'creator:test-{organizer.id}'
        self.payee = PayeeAccount.objects.create(
            account_key=account_key,
            actor_type=actor_type,
            actor_id=organizer.id,
            display_name=organizer.name,
            legal_name=organizer.name,
            email=organizer.contact_email or '',
            organizer=organizer,
            tax_id='11111111-1',
            bank_name='Banco Test',
            account_type='Cuenta Corriente',
            account_number='123456',
            account_holder=organizer.name,
        )
        PayeeSchedule.objects.create(payee=self.payee)
        return self.payee

    def create_payable_lines(self, payee=None, count=2):
        payee = payee or getattr(self, 'payee', None)
        if not payee:
            self.create_payee()
            payee = self.payee

        amounts = [(10000, 2500), (12000, 3000)][:count]
        lines = []
        for i, (gross, payable) in enumerate(amounts):
            line = PayableLine.objects.create(
                payee=payee,
                source_type='creator_commission',
                source_reference=f'reservation:test-{i+1}:creator',
                source_label=f'Reserva {i+1}',
                gross_amount=gross,
                platform_fee_amount=0,
                payable_amount=payable,
                currency='CLP',
            )
            lines.append(line)
        return lines

    def create_event_and_order(self, organizer=None):
        organizer = organizer or getattr(self, 'organizer', None)
        if not organizer:
            self.create_organizer()
            organizer = self.organizer

        start = timezone.now() + timedelta(days=7)
        end = start + timedelta(hours=2)
        slug = f'event-finance-{uuid.uuid4().hex[:8]}'
        self.event = Event.objects.create(
            title='Concierto Test',
            slug=slug,
            organizer=organizer,
            status='published',
            start_date=start,
            end_date=end,
            visibility='public',
        )

        self.order = Order.objects.create(
            order_kind='event',
            event=self.event,
            status='paid',
            email='buyer@test.com',
            first_name='Juan',
            last_name='Pérez',
            subtotal=Decimal('85000'),
            service_fee=Decimal('5000'),
            subtotal_effective=Decimal('85000'),
            service_fee_effective=Decimal('5000'),
            total=Decimal('90000'),
            is_sandbox=False,
        )
        return self.event, self.order

    def create_commercial_policy(self, organizer=None, commercial_mode='collect_total'):
        organizer = organizer or getattr(self, 'organizer', None)
        if not organizer:
            self.create_organizer()
            organizer = self.organizer

        today = timezone.localdate()
        return CommercialPolicy.objects.create(
            scope_type='organizer_default',
            organizer=organizer,
            commercial_mode=commercial_mode,
            recognition_policy='on_settlement_close',
            settlement_policy='manual',
            effective_from=today,
            effective_to=today + timedelta(days=365),
            priority=0,
            is_active=True,
        )

    def create_ledger_accounts(self):
        """Crea cuentas mínimas para tests de ledger."""
        accounts = [
            ('1.1.02', 'Bancos', 'asset', 'bank'),
            ('2.1.10', 'Fondos terceros', 'liability', 'third_party_funds'),
            ('4.1.01', 'Comisión', 'revenue', 'commission'),
            ('5.1.01', 'Gastos generales', 'expense', 'general'),
        ]
        created = []
        for code, name, acc_type, subtype in accounts:
            acc, _ = LedgerAccount.objects.get_or_create(
                code=code,
                defaults={'name': name, 'account_type': acc_type, 'subtype': subtype},
            )
            created.append(acc)
        return created

    def create_vendor_and_bill(self):
        self.vendor = Vendor.objects.create(
            name='Proveedor Test',
            legal_name='Proveedor Test SpA',
            tax_id='22222222-2',
            country_code='CL',
            currency='CLP',
        )
        today = timezone.localdate()
        self.bill = VendorBill.objects.create(
            vendor=self.vendor,
            bill_number='FAC-001',
            issue_date=today,
            due_date=today + timedelta(days=30),
            subtotal_amount=Decimal('100000'),
            tax_amount=Decimal('19000'),
            total_amount=Decimal('119000'),
            status='draft',
        )
        return self.vendor, self.bill
