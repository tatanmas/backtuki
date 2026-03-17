"""Finance domain models for payables, payouts, batches and exports."""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class FinancePlatformSettings(BaseModel):
    """Global finance defaults configured at platform level."""

    default_next_payment_date = models.DateField(_("default next payment date"), null=True, blank=True, db_index=True)
    default_schedule_frequency = models.CharField(_("default schedule frequency"), max_length=20, default='manual')
    payout_notes = models.TextField(_("payout notes"), blank=True)

    class Meta:
        verbose_name = _("finance platform settings")
        verbose_name_plural = _("finance platform settings")

    def __str__(self):
        return "Finance platform settings"


class PayeeAccount(BaseModel):
    ACTOR_TYPE_CHOICES = [
        ('organizer', _('Organizer')),
        ('creator', _('Creator')),
        ('transport_operator', _('Transport operator')),
        ('other', _('Other')),
    ]

    STATUS_CHOICES = [
        ('active', _('Active')),
        ('inactive', _('Inactive')),
        ('blocked', _('Blocked')),
    ]

    account_key = models.CharField(
        _("account key"),
        max_length=150,
        unique=True,
        db_index=True,
        help_text=_("Stable identity such as organizer:<uuid> or creator:<uuid>."),
    )
    actor_type = models.CharField(_("actor type"), max_length=40, choices=ACTOR_TYPE_CHOICES, db_index=True)
    actor_id = models.UUIDField(_("actor id"), null=True, blank=True, db_index=True)
    display_name = models.CharField(_("display name"), max_length=255)
    legal_name = models.CharField(_("legal name"), max_length=255, blank=True)
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(_("phone"), max_length=50, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)

    organizer = models.ForeignKey(
        'organizers.Organizer',
        on_delete=models.SET_NULL,
        related_name='finance_payee_accounts',
        null=True,
        blank=True,
    )
    creator = models.ForeignKey(
        'creators.CreatorProfile',
        on_delete=models.SET_NULL,
        related_name='finance_payee_accounts',
        null=True,
        blank=True,
    )

    country_code = models.CharField(_("country code"), max_length=2, default='CL')
    person_type = models.CharField(_("person type"), max_length=20, blank=True)
    tax_name = models.CharField(_("tax name"), max_length=255, blank=True)
    tax_id = models.CharField(_("tax id"), max_length=50, blank=True)
    billing_address = models.CharField(_("billing address"), max_length=255, blank=True)
    recipient_type = models.CharField(_("recipient type"), max_length=50, blank=True)
    document_type = models.CharField(_("document type"), max_length=50, default='RUT', blank=True)
    document_number = models.CharField(_("document number"), max_length=50, blank=True)

    bank_name = models.CharField(_("bank name"), max_length=100, blank=True)
    account_type = models.CharField(_("account type"), max_length=50, blank=True)
    account_number = models.CharField(_("account number"), max_length=100, blank=True)
    account_holder = models.CharField(_("account holder"), max_length=255, blank=True)

    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("payee account")
        verbose_name_plural = _("payee accounts")
        ordering = ['display_name']
        indexes = [
            models.Index(fields=['actor_type', 'status']),
            models.Index(fields=['display_name']),
        ]

    def __str__(self):
        return self.display_name

    @property
    def has_bank_details(self):
        return bool(self.bank_name and self.account_type and self.account_number and self.account_holder)

    @property
    def has_billing_details(self):
        return bool(self.tax_name and self.tax_id)

    @property
    def can_export(self):
        return self.has_bank_details and self.has_billing_details and self.status == 'active'


class PayeeSchedule(BaseModel):
    FREQUENCY_CHOICES = [
        ('manual', _('Manual')),
        ('weekly', _('Weekly')),
        ('biweekly', _('Biweekly')),
        ('monthly', _('Monthly')),
    ]

    payee = models.OneToOneField(
        PayeeAccount,
        on_delete=models.CASCADE,
        related_name='schedule',
    )
    frequency = models.CharField(_("frequency"), max_length=20, choices=FREQUENCY_CHOICES, default='manual')
    hold_days = models.PositiveIntegerField(_("hold days"), default=0)
    next_payment_date = models.DateField(_("next payment date"), null=True, blank=True, db_index=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        verbose_name = _("payee schedule")
        verbose_name_plural = _("payee schedules")


class PayableLine(BaseModel):
    STATUS_CHOICES = [
        ('open', _('Open')),
        ('batched', _('Batched')),
        ('paid', _('Paid')),
        ('reconciled', _('Reconciled')),
        ('voided', _('Voided')),
    ]
    MATURITY_CHOICES = [
        ('pending', _('Pending')),
        ('available', _('Available')),
        ('blocked', _('Blocked')),
    ]
    SOURCE_TYPE_CHOICES = [
        ('event_order', _('Event order')),
        ('experience_order', _('Experience order')),
        ('creator_commission', _('Creator commission')),
        ('accommodation_order', _('Accommodation order')),
        ('car_rental_order', _('Car rental order')),
        ('erasmus_activity_order', _('Erasmus activity order')),
        ('external_revenue', _('External revenue')),
        ('manual_adjustment', _('Manual adjustment')),
    ]

    RECOVERY_STATUS_CHOICES = [
        ('not_applicable', _('Not applicable')),
        ('pending', _('Pending')),
        ('partially_recovered', _('Partially recovered')),
        ('recovered', _('Recovered')),
        ('written_off', _('Written off')),
    ]

    payee = models.ForeignKey(
        PayeeAccount,
        on_delete=models.CASCADE,
        related_name='payable_lines',
    )
    source_type = models.CharField(_("source type"), max_length=40, choices=SOURCE_TYPE_CHOICES, db_index=True)
    source_reference = models.CharField(_("source reference"), max_length=150, unique=True)
    source_label = models.CharField(_("source label"), max_length=255, blank=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='open', db_index=True)
    maturity_status = models.CharField(_("maturity status"), max_length=20, choices=MATURITY_CHOICES, default='available', db_index=True)

    order = models.ForeignKey(
        'events.Order',
        on_delete=models.SET_NULL,
        related_name='finance_payable_lines',
        null=True,
        blank=True,
    )
    experience_reservation = models.ForeignKey(
        'experiences.ExperienceReservation',
        on_delete=models.SET_NULL,
        related_name='finance_payable_lines',
        null=True,
        blank=True,
    )

    gross_amount = models.DecimalField(_("gross amount"), max_digits=12, decimal_places=2, default=0)
    platform_fee_amount = models.DecimalField(_("platform fee amount"), max_digits=12, decimal_places=2, default=0)
    payable_amount = models.DecimalField(_("payable amount"), max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    effective_at = models.DateTimeField(_("effective at"), null=True, blank=True, db_index=True)
    due_date = models.DateField(_("due date"), null=True, blank=True, db_index=True)
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True, db_index=True)

    external_revenue_record = models.ForeignKey(
        'ExternalRevenueRecord', on_delete=models.SET_NULL,
        related_name='payable_lines', null=True, blank=True,
    )
    settlement_run = models.ForeignKey(
        'SettlementRun', on_delete=models.SET_NULL,
        related_name='payable_lines', null=True, blank=True,
    )
    commercial_mode = models.CharField(_("commercial mode"), max_length=40, blank=True)
    recovery_status = models.CharField(
        _("recovery status"), max_length=30,
        choices=RECOVERY_STATUS_CHOICES, default='not_applicable',
    )
    recovered_amount = models.DecimalField(_("recovered amount"), max_digits=12, decimal_places=2, default=0)
    invoice_reference = models.CharField(
        _("invoice reference"),
        max_length=100,
        blank=True,
        help_text=_("Boleta de honorarios number (required for creators before payment)"),
    )

    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("payable line")
        verbose_name_plural = _("payable lines")
        ordering = ['-effective_at', '-created_at']
        indexes = [
            models.Index(fields=['payee', 'status']),
            models.Index(fields=['payee', 'maturity_status']),
            models.Index(fields=['source_type', 'effective_at']),
        ]

    def __str__(self):
        return f"{self.payee.display_name} · {self.source_reference}"


class PayoutBatch(BaseModel):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('approved', _('Approved')),
        ('exported', _('Exported')),
        ('submitted', _('Submitted')),
        ('paid', _('Paid')),
        ('reconciled', _('Reconciled')),
        ('failed', _('Failed')),
    ]

    name = models.CharField(_("name"), max_length=255)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    description = models.TextField(_("description"), blank=True)
    approved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='finance_batches_approved',
        null=True,
        blank=True,
    )
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("payout batch")
        verbose_name_plural = _("payout batches")
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class BankExportFile(BaseModel):
    STATUS_CHOICES = [
        ('generated', _('Generated')),
        ('downloaded', _('Downloaded')),
        ('archived', _('Archived')),
    ]

    batch = models.ForeignKey(
        PayoutBatch,
        on_delete=models.CASCADE,
        related_name='export_files',
        null=True,
        blank=True,
    )
    adapter_code = models.CharField(_("adapter code"), max_length=50, db_index=True)
    filename = models.CharField(_("filename"), max_length=255)
    checksum = models.CharField(_("checksum"), max_length=128, blank=True)
    content = models.JSONField(_("content"), default=list, blank=True)
    row_count = models.PositiveIntegerField(_("row count"), default=0)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='generated')
    generated_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='finance_export_files',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("bank export file")
        verbose_name_plural = _("bank export files")
        ordering = ['-created_at']


class Payout(BaseModel):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('approved', _('Approved')),
        ('exported', _('Exported')),
        ('submitted', _('Submitted')),
        ('paid', _('Paid')),
        ('reconciled', _('Reconciled')),
        ('failed', _('Failed')),
    ]

    payee = models.ForeignKey(
        PayeeAccount,
        on_delete=models.CASCADE,
        related_name='payouts',
    )
    batch = models.ForeignKey(
        PayoutBatch,
        on_delete=models.SET_NULL,
        related_name='payouts',
        null=True,
        blank=True,
    )
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    reference = models.CharField(_("reference"), max_length=255, blank=True)
    partner_message = models.TextField(_("partner message"), blank=True)
    bank_reference = models.CharField(_("bank reference"), max_length=255, blank=True)
    approved_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='finance_payouts_approved',
        null=True,
        blank=True,
    )
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True, db_index=True)
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("payout")
        verbose_name_plural = _("payouts")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payee', 'status']),
            models.Index(fields=['status', 'paid_at']),
        ]

    def __str__(self):
        return f"{self.payee.display_name} · {self.amount}"


class PayoutLineAllocation(BaseModel):
    payout = models.ForeignKey(
        Payout,
        on_delete=models.CASCADE,
        related_name='allocations',
    )
    payable_line = models.OneToOneField(
        PayableLine,
        on_delete=models.CASCADE,
        related_name='allocation',
    )
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = _("payout line allocation")
        verbose_name_plural = _("payout line allocations")
        ordering = ['created_at']


class PayoutAttachment(BaseModel):
    payout = models.ForeignKey(
        Payout,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    file = models.FileField(_("file"), upload_to='finance/payout-attachments/')
    original_name = models.CharField(_("original name"), max_length=255, blank=True)
    label = models.CharField(_("label"), max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='finance_payout_attachments',
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("payout attachment")
        verbose_name_plural = _("payout attachments")
        ordering = ['-created_at']


# ---------------------------------------------------------------------------
# Capa 1: Operacion comercial – CommercialPolicy
# ---------------------------------------------------------------------------

class CommercialPolicy(BaseModel):
    SCOPE_TYPE_CHOICES = [
        ('organizer_default', _('Organizer default')),
        ('vertical_default', _('Vertical default')),
        ('product', _('Product')),
    ]
    COMMERCIAL_MODE_CHOICES = [
        ('collect_total', _('Collect total')),
        ('collect_commission_from_partner', _('Collect commission from partner')),
        ('collect_service_fee_only', _('Collect service fee only')),
    ]
    RECOGNITION_POLICY_CHOICES = [
        ('on_payment', _('On payment')),
        ('on_service_completion', _('On service completion')),
        ('on_settlement_close', _('On settlement close')),
    ]
    SETTLEMENT_POLICY_CHOICES = [
        ('per_product', _('Per product')),
        ('weekly', _('Weekly')),
        ('monthly', _('Monthly')),
        ('manual', _('Manual')),
    ]

    scope_type = models.CharField(_("scope type"), max_length=30, choices=SCOPE_TYPE_CHOICES, db_index=True)
    scope_id = models.UUIDField(_("scope id"), null=True, blank=True, db_index=True)
    organizer = models.ForeignKey(
        'organizers.Organizer', on_delete=models.CASCADE,
        related_name='commercial_policies', null=True, blank=True,
    )
    commercial_mode = models.CharField(_("commercial mode"), max_length=40, choices=COMMERCIAL_MODE_CHOICES)
    recognition_policy = models.CharField(
        _("recognition policy"), max_length=30,
        choices=RECOGNITION_POLICY_CHOICES, default='on_settlement_close',
    )
    settlement_policy = models.CharField(
        _("settlement policy"), max_length=20,
        choices=SETTLEMENT_POLICY_CHOICES, default='manual',
    )
    effective_from = models.DateField(_("effective from"))
    effective_to = models.DateField(_("effective to"), null=True, blank=True)
    priority = models.PositiveIntegerField(_("priority"), default=0)
    is_active = models.BooleanField(_("is active"), default=True, db_index=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("commercial policy")
        verbose_name_plural = _("commercial policies")
        ordering = ['-priority', '-effective_from']
        indexes = [
            models.Index(fields=['scope_type', 'scope_id', 'is_active']),
            models.Index(fields=['organizer', 'is_active']),
        ]

    def __str__(self):
        return f"{self.scope_type}:{self.scope_id} → {self.commercial_mode}"


# ---------------------------------------------------------------------------
# Capa 2: Fondos de terceros / settlements / revenue externo
# ---------------------------------------------------------------------------

class ExternalRevenueImportBatch(BaseModel):
    STATUS_CHOICES = [
        ('processing', _('Processing')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('dry_run', _('Dry run')),
    ]

    source = models.CharField(_("source"), max_length=100, db_index=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='processing')
    uploaded_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        related_name='external_revenue_batches', null=True, blank=True,
    )
    original_filename = models.CharField(_("original filename"), max_length=255, blank=True)
    payload_checksum = models.CharField(_("payload checksum"), max_length=128, blank=True, db_index=True)
    records_received = models.PositiveIntegerField(_("records received"), default=0)
    records_created = models.PositiveIntegerField(_("records created"), default=0)
    records_skipped = models.PositiveIntegerField(_("records skipped"), default=0)
    records_failed = models.PositiveIntegerField(_("records failed"), default=0)
    errors = models.JSONField(_("errors"), default=list, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("external revenue import batch")
        verbose_name_plural = _("external revenue import batches")
        ordering = ['-created_at']

    def __str__(self):
        return f"Batch {self.source} – {self.status} ({self.created_at:%Y-%m-%d})"


class ExternalRevenueRecord(BaseModel):
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('reversed', _('Reversed')),
        ('voided', _('Voided')),
    ]
    COMMERCIAL_MODE_CHOICES = CommercialPolicy.COMMERCIAL_MODE_CHOICES

    import_batch = models.ForeignKey(
        ExternalRevenueImportBatch, on_delete=models.SET_NULL,
        related_name='records', null=True, blank=True,
    )
    source_type = models.CharField(_("source type"), max_length=40, db_index=True)
    source_system = models.CharField(_("source system"), max_length=100, blank=True)
    external_reference = models.CharField(_("external reference"), max_length=255, db_index=True)
    organizer = models.ForeignKey(
        'organizers.Organizer', on_delete=models.PROTECT,
        related_name='external_revenue_records',
        null=True, blank=True,
        help_text=_("Optional for pre-platform revenue (orphan records)"),
    )
    already_paid = models.BooleanField(
        _("already paid"),
        default=False,
        db_index=True,
        help_text=_("Revenue already paid/transferred before platform (pre-platform events)"),
    )
    event = models.ForeignKey('events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='external_revenue_records')
    experience = models.ForeignKey('experiences.Experience', on_delete=models.SET_NULL, null=True, blank=True, related_name='external_revenue_records')
    accommodation = models.ForeignKey('accommodations.Accommodation', on_delete=models.SET_NULL, null=True, blank=True, related_name='external_revenue_records')
    car = models.ForeignKey('car_rental.Car', on_delete=models.SET_NULL, null=True, blank=True, related_name='external_revenue_records')
    product_label = models.CharField(_("product label"), max_length=255, blank=True)
    commercial_mode = models.CharField(_("commercial mode"), max_length=40, choices=COMMERCIAL_MODE_CHOICES, default='collect_total')
    gross_amount = models.DecimalField(_("gross amount"), max_digits=14, decimal_places=2)
    platform_fee_amount = models.DecimalField(_("platform fee amount"), max_digits=14, decimal_places=2, default=0)
    payable_amount = models.DecimalField(_("payable amount"), max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    effective_date = models.DateField(_("effective date"), db_index=True)
    service_date = models.DateField(_("service date"), null=True, blank=True)
    completion_date = models.DateField(_("completion date"), null=True, blank=True)
    settlement_date = models.DateField(_("settlement date"), null=True, blank=True)
    posting_date = models.DateField(_("posting date"), null=True, blank=True)
    due_date = models.DateField(_("due date"), null=True, blank=True)
    description = models.TextField(_("description"), blank=True)
    exclude_from_revenue = models.BooleanField(_("exclude from revenue"), default=False, db_index=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    reversal_of = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reversals',
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("external revenue record")
        verbose_name_plural = _("external revenue records")
        ordering = ['-effective_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['source_type', 'external_reference'],
                condition=models.Q(status='active'),
                name='uq_active_ext_rev_source_ref',
            ),
        ]
        indexes = [
            models.Index(fields=['organizer', 'status']),
            models.Index(fields=['effective_date', 'status']),
        ]

    def __str__(self):
        return f"{self.source_type}:{self.external_reference} – {self.gross_amount} {self.currency}"


class SettlementRun(BaseModel):
    SCOPE_TYPE_CHOICES = [
        ('event', _('Event')),
        ('experience', _('Experience')),
        ('accommodation', _('Accommodation')),
        ('organizer', _('Organizer')),
        ('batch', _('Batch')),
    ]
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('calculated', _('Calculated')),
        ('posted', _('Posted')),
        ('paid', _('Paid')),
        ('voided', _('Voided')),
    ]

    scope_type = models.CharField(_("scope type"), max_length=30, choices=SCOPE_TYPE_CHOICES, db_index=True)
    scope_id = models.UUIDField(_("scope id"), null=True, blank=True, db_index=True)
    organizer = models.ForeignKey(
        'organizers.Organizer', on_delete=models.PROTECT,
        related_name='settlement_runs',
    )
    commercial_mode = models.CharField(_("commercial mode"), max_length=40, choices=CommercialPolicy.COMMERCIAL_MODE_CHOICES)
    recognition_policy = models.CharField(_("recognition policy"), max_length=30, choices=CommercialPolicy.RECOGNITION_POLICY_CHOICES)
    settlement_policy = models.CharField(_("settlement policy"), max_length=20, choices=CommercialPolicy.SETTLEMENT_POLICY_CHOICES)
    period_start = models.DateField(_("period start"))
    period_end = models.DateField(_("period end"))
    service_cutoff_date = models.DateField(_("service cutoff date"), null=True, blank=True)
    settlement_date = models.DateField(_("settlement date"))
    posting_date = models.DateField(_("posting date"), null=True, blank=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    gross_collected = models.DecimalField(_("gross collected"), max_digits=14, decimal_places=2, default=0)
    platform_fee_recognized = models.DecimalField(_("platform fee recognized"), max_digits=14, decimal_places=2, default=0)
    payable_amount = models.DecimalField(_("payable amount"), max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    closed_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        related_name='closed_settlements', null=True, blank=True,
    )
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    recovery_status = models.CharField(
        _("recovery status"), max_length=30,
        choices=PayableLine.RECOVERY_STATUS_CHOICES, default='not_applicable',
    )
    recovered_amount = models.DecimalField(_("recovered amount"), max_digits=14, decimal_places=2, default=0)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("settlement run")
        verbose_name_plural = _("settlement runs")
        ordering = ['-settlement_date', '-created_at']
        indexes = [
            models.Index(fields=['scope_type', 'scope_id', 'status']),
            models.Index(fields=['organizer', 'status']),
        ]

    def __str__(self):
        return f"Settlement {self.scope_type}:{self.scope_id} – {self.status}"


class SettlementLine(BaseModel):
    settlement_run = models.ForeignKey(
        SettlementRun, on_delete=models.CASCADE, related_name='lines',
    )
    source_type = models.CharField(_("source type"), max_length=40, db_index=True)
    source_id = models.UUIDField(_("source id"), null=True, blank=True, db_index=True)
    order = models.ForeignKey(
        'events.Order', on_delete=models.SET_NULL,
        related_name='settlement_lines', null=True, blank=True,
    )
    external_revenue_record = models.ForeignKey(
        ExternalRevenueRecord, on_delete=models.SET_NULL,
        related_name='settlement_lines', null=True, blank=True,
    )
    gross_amount = models.DecimalField(_("gross amount"), max_digits=14, decimal_places=2, default=0)
    platform_fee_amount = models.DecimalField(_("platform fee amount"), max_digits=14, decimal_places=2, default=0)
    payable_amount = models.DecimalField(_("payable amount"), max_digits=14, decimal_places=2, default=0)
    effective_date = models.DateField(_("effective date"))
    completion_date = models.DateField(_("completion date"), null=True, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("settlement line")
        verbose_name_plural = _("settlement lines")
        ordering = ['-effective_date']

    def __str__(self):
        return f"Line {self.source_type}:{self.source_id} → {self.payable_amount}"


class FinancialDocument(BaseModel):
    DOC_TYPE_CHOICES = [
        ('invoice', _('Invoice')),
        ('settlement', _('Settlement')),
        ('support', _('Support')),
    ]

    doc_type = models.CharField(_("document type"), max_length=20, choices=DOC_TYPE_CHOICES, db_index=True)
    file = models.FileField(_("file"), upload_to='finance/documents/')
    original_name = models.CharField(_("original name"), max_length=255, blank=True)
    label = models.CharField(_("label"), max_length=255, blank=True)
    external_revenue_record = models.ForeignKey(
        ExternalRevenueRecord, on_delete=models.SET_NULL,
        related_name='documents', null=True, blank=True,
    )
    settlement_run = models.ForeignKey(
        SettlementRun, on_delete=models.SET_NULL,
        related_name='documents', null=True, blank=True,
    )
    event = models.ForeignKey('events.Event', on_delete=models.SET_NULL, null=True, blank=True, related_name='finance_documents')
    uploaded_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        related_name='finance_documents', null=True, blank=True,
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("financial document")
        verbose_name_plural = _("financial documents")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.doc_type}: {self.label or self.original_name}"


# ---------------------------------------------------------------------------
# Capa 3: Gastos / proveedores
# ---------------------------------------------------------------------------

class Vendor(BaseModel):
    VENDOR_TYPE_CHOICES = [
        ('local', _('Local')),
        ('foreign', _('Foreign')),
        ('related_party', _('Related party')),
    ]
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('inactive', _('Inactive')),
    ]

    vendor_type = models.CharField(_("vendor type"), max_length=20, choices=VENDOR_TYPE_CHOICES, default='local', db_index=True)
    name = models.CharField(_("name"), max_length=255)
    legal_name = models.CharField(_("legal name"), max_length=255, blank=True)
    tax_id = models.CharField(_("tax id"), max_length=50, blank=True, db_index=True)
    document_type = models.CharField(_("document type"), max_length=50, blank=True)
    country_code = models.CharField(_("country code"), max_length=2, default='CL')
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    email = models.EmailField(_("email"), blank=True)
    phone = models.CharField(_("phone"), max_length=50, blank=True)
    address = models.TextField(_("address"), blank=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    bank_name = models.CharField(_("bank name"), max_length=100, blank=True)
    account_type = models.CharField(_("account type"), max_length=50, blank=True)
    account_number = models.CharField(_("account number"), max_length=100, blank=True)
    account_holder = models.CharField(_("account holder"), max_length=255, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("vendor")
        verbose_name_plural = _("vendors")
        ordering = ['name']

    def __str__(self):
        return self.name


class ExpenseCategory(BaseModel):
    code = models.CharField(_("code"), max_length=30, unique=True)
    name = models.CharField(_("name"), max_length=255)
    cost_center_required = models.BooleanField(_("cost center required"), default=False)
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("expense category")
        verbose_name_plural = _("expense categories")
        ordering = ['code']

    def __str__(self):
        return f"{self.code} – {self.name}"


class CostCenter(BaseModel):
    code = models.CharField(_("code"), max_length=30, unique=True)
    name = models.CharField(_("name"), max_length=255)
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("cost center")
        verbose_name_plural = _("cost centers")
        ordering = ['code']

    def __str__(self):
        return f"{self.code} – {self.name}"


class TaxTreatment(BaseModel):
    TAX_TYPE_CHOICES = [
        ('vat_credit', _('VAT credit')),
        ('vat_exempt', _('VAT exempt')),
        ('no_vat', _('No VAT')),
        ('foreign_service', _('Foreign service')),
        ('non_creditable_vat', _('Non-creditable VAT')),
        ('withholding', _('Withholding')),
    ]

    code = models.CharField(_("code"), max_length=30, unique=True)
    name = models.CharField(_("name"), max_length=255)
    tax_type = models.CharField(_("tax type"), max_length=30, choices=TAX_TYPE_CHOICES, db_index=True)
    rate = models.DecimalField(_("rate"), max_digits=5, decimal_places=4, default=0)
    is_recoverable = models.BooleanField(_("is recoverable"), default=False)
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("tax treatment")
        verbose_name_plural = _("tax treatments")
        ordering = ['code']

    def __str__(self):
        return f"{self.code} – {self.name}"


class VendorBill(BaseModel):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('posted', _('Posted')),
        ('partially_paid', _('Partially paid')),
        ('paid', _('Paid')),
        ('voided', _('Voided')),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='bills')
    bill_number = models.CharField(_("bill number"), max_length=100, db_index=True)
    issue_date = models.DateField(_("issue date"))
    due_date = models.DateField(_("due date"))
    service_period_start = models.DateField(_("service period start"), null=True, blank=True)
    service_period_end = models.DateField(_("service period end"), null=True, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    subtotal_amount = models.DecimalField(_("subtotal amount"), max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(_("tax amount"), max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(_("total amount"), max_digits=14, decimal_places=2, default=0)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    external_reference = models.CharField(_("external reference"), max_length=255, blank=True)
    description = models.TextField(_("description"), blank=True)
    document_file = models.FileField(_("document file"), upload_to='finance/vendor-bills/', null=True, blank=True)
    posting_date = models.DateField(_("posting date"), null=True, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("vendor bill")
        verbose_name_plural = _("vendor bills")
        ordering = ['-issue_date']
        constraints = [
            models.UniqueConstraint(fields=['vendor', 'bill_number'], name='uq_vendor_bill_number'),
        ]
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]

    def __str__(self):
        return f"{self.vendor.name} – {self.bill_number}"

    @property
    def amount_paid(self):
        return self.payment_allocations.aggregate(total=models.Sum('amount'))['total'] or 0

    @property
    def amount_due(self):
        return self.total_amount - self.amount_paid


class ExpenseLine(BaseModel):
    vendor_bill = models.ForeignKey(VendorBill, on_delete=models.CASCADE, related_name='expense_lines')
    expense_category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expense_lines')
    cost_center = models.ForeignKey(CostCenter, on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_lines')
    tax_treatment = models.ForeignKey(TaxTreatment, on_delete=models.PROTECT, related_name='expense_lines')
    description = models.CharField(_("description"), max_length=500, blank=True)
    product_type = models.CharField(_("product type"), max_length=40, null=True, blank=True, db_index=True)
    product_id = models.UUIDField(_("product id"), null=True, blank=True)
    allocation_basis = models.CharField(_("allocation basis"), max_length=50, blank=True)
    net_amount = models.DecimalField(_("net amount"), max_digits=14, decimal_places=2, default=0)
    tax_amount = models.DecimalField(_("tax amount"), max_digits=14, decimal_places=2, default=0)
    gross_amount = models.DecimalField(_("gross amount"), max_digits=14, decimal_places=2, default=0)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("expense line")
        verbose_name_plural = _("expense lines")
        ordering = ['created_at']

    def __str__(self):
        return f"{self.expense_category.code}: {self.gross_amount}"


class VendorPayment(BaseModel):
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('voided', _('Voided')),
    ]

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name='payments')
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    payment_date = models.DateField(_("payment date"))
    posting_date = models.DateField(_("posting date"), null=True, blank=True)
    amount = models.DecimalField(_("amount"), max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    reference = models.CharField(_("reference"), max_length=255, blank=True)
    bank_reference = models.CharField(_("bank reference"), max_length=255, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("vendor payment")
        verbose_name_plural = _("vendor payments")
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['vendor', 'status']),
        ]

    def __str__(self):
        return f"{self.vendor.name} – {self.amount} ({self.status})"


class VendorPaymentAllocation(BaseModel):
    vendor_payment = models.ForeignKey(VendorPayment, on_delete=models.CASCADE, related_name='allocations')
    vendor_bill = models.ForeignKey(VendorBill, on_delete=models.CASCADE, related_name='payment_allocations')
    amount = models.DecimalField(_("amount"), max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = _("vendor payment allocation")
        verbose_name_plural = _("vendor payment allocations")
        ordering = ['created_at']

    def __str__(self):
        return f"Alloc {self.vendor_bill.bill_number} ← {self.amount}"


class ProcessorCostAllocation(BaseModel):
    TARGET_TYPE_CHOICES = [
        ('event', _('Event')),
        ('order', _('Order')),
        ('product_type', _('Product type')),
        ('period', _('Period')),
    ]
    ALLOCATION_METHOD_CHOICES = [
        ('manual', _('Manual')),
        ('proportional_gross', _('Proportional to gross')),
        ('proportional_orders', _('Proportional to order count')),
        ('proportional_units', _('Proportional to units')),
    ]

    vendor_bill = models.ForeignKey(VendorBill, on_delete=models.CASCADE, related_name='processor_allocations')
    expense_line = models.ForeignKey(ExpenseLine, on_delete=models.CASCADE, related_name='processor_allocations')
    target_type = models.CharField(_("target type"), max_length=20, choices=TARGET_TYPE_CHOICES, db_index=True)
    target_id = models.UUIDField(_("target id"), null=True, blank=True)
    allocation_method = models.CharField(_("allocation method"), max_length=30, choices=ALLOCATION_METHOD_CHOICES)
    allocated_amount = models.DecimalField(_("allocated amount"), max_digits=14, decimal_places=2, default=0)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("processor cost allocation")
        verbose_name_plural = _("processor cost allocations")
        ordering = ['-created_at']

    def __str__(self):
        return f"Alloc {self.target_type}:{self.target_id} → {self.allocated_amount}"


# ---------------------------------------------------------------------------
# Capa 4: Related parties / socios
# ---------------------------------------------------------------------------

class RelatedParty(BaseModel):
    PARTY_TYPE_CHOICES = [
        ('founder', _('Founder')),
        ('shareholder', _('Shareholder')),
        ('ex_shareholder', _('Ex-shareholder')),
        ('related_company', _('Related company')),
    ]
    STATUS_CHOICES = [
        ('active', _('Active')),
        ('inactive', _('Inactive')),
    ]

    party_type = models.CharField(_("party type"), max_length=20, choices=PARTY_TYPE_CHOICES, db_index=True)
    name = models.CharField(_("name"), max_length=255)
    legal_name = models.CharField(_("legal name"), max_length=255, blank=True)
    tax_id = models.CharField(_("tax id"), max_length=50, blank=True)
    country_code = models.CharField(_("country code"), max_length=2, default='CL')
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='active')
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("related party")
        verbose_name_plural = _("related parties")
        ordering = ['name']

    def __str__(self):
        return self.name


class RelatedPartyTransaction(BaseModel):
    TRANSACTION_TYPE_CHOICES = [
        ('capital_contribution', _('Capital contribution')),
        ('shareholder_loan_to_company', _('Shareholder loan to company')),
        ('company_debt_to_related_party', _('Company debt to related party')),
        ('expense_paid_personally', _('Expense paid personally')),
        ('reimbursement', _('Reimbursement')),
        ('loan_repayment', _('Loan repayment')),
    ]
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('posted', _('Posted')),
        ('reversed', _('Reversed')),
        ('settled', _('Settled')),
    ]

    related_party = models.ForeignKey(RelatedParty, on_delete=models.PROTECT, related_name='transactions')
    transaction_type = models.CharField(_("transaction type"), max_length=40, choices=TRANSACTION_TYPE_CHOICES, db_index=True)
    transaction_date = models.DateField(_("transaction date"))
    posting_date = models.DateField(_("posting date"), null=True, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    amount = models.DecimalField(_("amount"), max_digits=14, decimal_places=2)
    reference = models.CharField(_("reference"), max_length=255, blank=True)
    description = models.TextField(_("description"), blank=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("related party transaction")
        verbose_name_plural = _("related party transactions")
        ordering = ['-transaction_date']

    def __str__(self):
        return f"{self.related_party.name} – {self.transaction_type}: {self.amount}"


class RelatedPartySettlement(BaseModel):
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('completed', _('Completed')),
        ('failed', _('Failed')),
        ('voided', _('Voided')),
    ]

    related_party = models.ForeignKey(RelatedParty, on_delete=models.PROTECT, related_name='settlements')
    transaction = models.ForeignKey(
        RelatedPartyTransaction, on_delete=models.SET_NULL,
        related_name='settlements', null=True, blank=True,
    )
    payment_date = models.DateField(_("payment date"))
    posting_date = models.DateField(_("posting date"), null=True, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    amount = models.DecimalField(_("amount"), max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    reference = models.CharField(_("reference"), max_length=255, blank=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("related party settlement")
        verbose_name_plural = _("related party settlements")
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.related_party.name} settlement: {self.amount}"


# ---------------------------------------------------------------------------
# Capa transversal: Treasury / bancos / conciliacion
# ---------------------------------------------------------------------------

class BankAccount(BaseModel):
    name = models.CharField(_("name"), max_length=255)
    bank_name = models.CharField(_("bank name"), max_length=100)
    account_number_masked = models.CharField(_("account number (masked)"), max_length=30, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    country_code = models.CharField(_("country code"), max_length=2, default='CL')
    is_active = models.BooleanField(_("is active"), default=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("bank account")
        verbose_name_plural = _("bank accounts")
        ordering = ['name']

    def __str__(self):
        return f"{self.bank_name} – {self.name}"


class BankStatementLine(BaseModel):
    STATUS_CHOICES = [
        ('imported', _('Imported')),
        ('matched', _('Matched')),
        ('partially_matched', _('Partially matched')),
        ('ignored', _('Ignored')),
    ]
    MOVEMENT_TYPE_CHOICES = [
        ('collection_income', _('Collection income')),
        ('collection_refund', _('Collection refund')),
        ('payout', _('Partner payout')),
        ('vendor_payment', _('Vendor payment')),
        ('transfer', _('Transfer')),
        ('expense', _('Expense')),
        ('vat', _('VAT / tax')),
        ('other', _('Other')),
    ]

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='statement_lines')
    statement_date = models.DateField(_("statement date"), db_index=True)
    value_date = models.DateField(_("value date"), null=True, blank=True)
    external_reference = models.CharField(_("external reference"), max_length=255, blank=True)
    description = models.CharField(_("description"), max_length=500, blank=True)
    amount = models.DecimalField(_("amount"), max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(_("balance after"), max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='imported', db_index=True)
    movement_type = models.CharField(
        _("movement type"),
        max_length=30,
        choices=MOVEMENT_TYPE_CHOICES,
        blank=True,
        db_index=True,
    )
    classification_note = models.TextField(_("classification note"), blank=True)
    matched_payout = models.ForeignKey(
        'Payout',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bank_statement_lines',
        verbose_name=_("matched payout"),
    )
    matched_vendor_payment = models.ForeignKey(
        'VendorPayment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bank_statement_lines',
        verbose_name=_("matched vendor payment"),
    )
    matched_processor_settlement = models.ForeignKey(
        'ProcessorSettlement',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bank_statement_lines',
        verbose_name=_("matched processor settlement"),
    )
    matched_journal_entry = models.ForeignKey(
        'JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bank_statement_lines',
        verbose_name=_("matched journal entry"),
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("bank statement line")
        verbose_name_plural = _("bank statement lines")
        ordering = ['-statement_date', '-created_at']
        indexes = [
            models.Index(fields=['bank_account', 'statement_date']),
        ]

    def __str__(self):
        return f"{self.bank_account.name} {self.statement_date}: {self.amount}"


class BankBalanceSnapshot(BaseModel):
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='balance_snapshots')
    snapshot_date = models.DateField(_("snapshot date"), db_index=True)
    balance = models.DecimalField(_("balance"), max_digits=14, decimal_places=2)
    source = models.CharField(_("source"), max_length=50, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("bank balance snapshot")
        verbose_name_plural = _("bank balance snapshots")
        ordering = ['-snapshot_date']
        constraints = [
            models.UniqueConstraint(fields=['bank_account', 'snapshot_date'], name='uq_bank_balance_date'),
        ]

    def __str__(self):
        return f"{self.bank_account.name} @ {self.snapshot_date}: {self.balance}"


class ProcessorSettlement(BaseModel):
    STATUS_CHOICES = [
        ('reported', _('Reported')),
        ('matched', _('Matched')),
        ('deposited', _('Deposited')),
        ('reconciled', _('Reconciled')),
    ]

    processor_name = models.CharField(_("processor name"), max_length=100, db_index=True)
    settlement_reference = models.CharField(_("settlement reference"), max_length=255, db_index=True)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    gross_amount = models.DecimalField(_("gross amount"), max_digits=14, decimal_places=2, default=0)
    fees_amount = models.DecimalField(_("fees amount"), max_digits=14, decimal_places=2, default=0)
    net_amount = models.DecimalField(_("net amount"), max_digits=14, decimal_places=2, default=0)
    payment_date = models.DateField(_("payment date"))
    deposit_date = models.DateField(_("deposit date"), null=True, blank=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='reported', db_index=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("processor settlement")
        verbose_name_plural = _("processor settlements")
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['processor_name', 'status']),
        ]

    def __str__(self):
        return f"{self.processor_name} – {self.settlement_reference}: {self.net_amount}"


class ProcessorClearingEntry(BaseModel):
    ENTRY_TYPE_CHOICES = [
        ('gross_collection', _('Gross collection')),
        ('processor_fee', _('Processor fee')),
        ('net_transfer', _('Net transfer')),
    ]

    processor_settlement = models.ForeignKey(
        ProcessorSettlement, on_delete=models.CASCADE, related_name='clearing_entries',
    )
    order = models.ForeignKey('events.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='processor_clearing_entries')
    payment = models.ForeignKey('payment_processor.Payment', on_delete=models.SET_NULL, null=True, blank=True, related_name='processor_clearing_entries')
    amount = models.DecimalField(_("amount"), max_digits=14, decimal_places=2, default=0)
    entry_type = models.CharField(_("entry type"), max_length=20, choices=ENTRY_TYPE_CHOICES, db_index=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("processor clearing entry")
        verbose_name_plural = _("processor clearing entries")
        ordering = ['created_at']

    def __str__(self):
        return f"{self.entry_type}: {self.amount}"


class BankReconciliation(BaseModel):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('balanced', _('Balanced')),
        ('reviewed', _('Reviewed')),
        ('closed', _('Closed')),
    ]

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='reconciliations')
    period_start = models.DateField(_("period start"))
    period_end = models.DateField(_("period end"))
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    book_balance = models.DecimalField(_("book balance"), max_digits=14, decimal_places=2, default=0)
    bank_balance = models.DecimalField(_("bank balance"), max_digits=14, decimal_places=2, default=0)
    unexplained_difference = models.DecimalField(_("unexplained difference"), max_digits=14, decimal_places=2, default=0)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("bank reconciliation")
        verbose_name_plural = _("bank reconciliations")
        ordering = ['-period_end']

    def __str__(self):
        return f"{self.bank_account.name} reconciliation {self.period_start}–{self.period_end}"


# ---------------------------------------------------------------------------
# Capa 4: Contabilidad / Ledger
# ---------------------------------------------------------------------------

class LedgerAccount(BaseModel):
    ACCOUNT_TYPE_CHOICES = [
        ('asset', _('Asset')),
        ('liability', _('Liability')),
        ('equity', _('Equity')),
        ('revenue', _('Revenue')),
        ('expense', _('Expense')),
    ]

    code = models.CharField(_("code"), max_length=20, unique=True, db_index=True)
    name = models.CharField(_("name"), max_length=255)
    account_type = models.CharField(_("account type"), max_length=20, choices=ACCOUNT_TYPE_CHOICES, db_index=True)
    subtype = models.CharField(_("subtype"), max_length=50, blank=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    currency_mode = models.CharField(_("currency mode"), max_length=20, default='functional', blank=True)
    is_active = models.BooleanField(_("is active"), default=True)

    class Meta:
        verbose_name = _("ledger account")
        verbose_name_plural = _("ledger accounts")
        ordering = ['code']

    def __str__(self):
        return f"{self.code} – {self.name}"


class JournalEntry(BaseModel):
    STATUS_CHOICES = [
        ('draft', _('Draft')),
        ('posted', _('Posted')),
        ('reversed', _('Reversed')),
    ]

    entry_date = models.DateField(_("entry date"), db_index=True)
    posting_date = models.DateField(_("posting date"), db_index=True)
    reference = models.CharField(_("reference"), max_length=255, blank=True)
    source_type = models.CharField(_("source type"), max_length=60, db_index=True)
    source_id = models.UUIDField(_("source id"), null=True, blank=True, db_index=True)
    posting_event = models.CharField(_("posting event"), max_length=60, db_index=True)
    idempotency_key = models.CharField(_("idempotency key"), max_length=255, unique=True, db_index=True)
    description = models.TextField(_("description"), blank=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default='draft', db_index=True)
    reversal_of = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reversals',
    )
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL,
        related_name='journal_entries', null=True, blank=True,
    )
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("journal entry")
        verbose_name_plural = _("journal entries")
        ordering = ['-posting_date', '-created_at']
        indexes = [
            models.Index(fields=['source_type', 'source_id']),
            models.Index(fields=['posting_event', 'status']),
        ]

    def __str__(self):
        return f"JE {self.reference or self.idempotency_key} – {self.status}"

    @property
    def is_balanced(self):
        agg = self.lines.aggregate(
            total_debit=models.Sum('debit_amount'),
            total_credit=models.Sum('credit_amount'),
        )
        return (agg['total_debit'] or 0) == (agg['total_credit'] or 0)


class JournalLine(BaseModel):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    ledger_account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name='journal_lines')
    debit_amount = models.DecimalField(_("debit amount"), max_digits=14, decimal_places=2, default=0)
    credit_amount = models.DecimalField(_("credit amount"), max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(_("currency"), max_length=3, default='CLP')
    functional_amount = models.DecimalField(_("functional amount"), max_digits=14, decimal_places=2, default=0)
    organizer = models.ForeignKey('organizers.Organizer', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    related_party = models.ForeignKey(RelatedParty, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    order = models.ForeignKey('events.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    payment = models.ForeignKey('payment_processor.Payment', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    external_revenue_record = models.ForeignKey(ExternalRevenueRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    settlement_run = models.ForeignKey(SettlementRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    payable_line = models.ForeignKey(PayableLine, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    payout = models.ForeignKey(Payout, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    vendor_bill = models.ForeignKey(VendorBill, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    vendor_payment = models.ForeignKey(VendorPayment, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    processor_settlement = models.ForeignKey(ProcessorSettlement, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    bank_statement_line = models.ForeignKey(BankStatementLine, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    description = models.CharField(_("description"), max_length=500, blank=True)
    metadata = models.JSONField(_("metadata"), default=dict, blank=True)

    class Meta:
        verbose_name = _("journal line")
        verbose_name_plural = _("journal lines")
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ledger_account', 'journal_entry']),
        ]

    def __str__(self):
        return f"{self.ledger_account.code} Dr:{self.debit_amount} Cr:{self.credit_amount}"
