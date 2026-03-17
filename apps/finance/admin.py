from django.contrib import admin

from .models import (
    BankAccount,
    BankBalanceSnapshot,
    BankExportFile,
    BankReconciliation,
    BankStatementLine,
    CommercialPolicy,
    CostCenter,
    ExpenseCategory,
    ExpenseLine,
    ExternalRevenueImportBatch,
    ExternalRevenueRecord,
    FinancePlatformSettings,
    FinancialDocument,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    PayableLine,
    PayeeAccount,
    PayeeSchedule,
    Payout,
    PayoutAttachment,
    PayoutBatch,
    PayoutLineAllocation,
    ProcessorClearingEntry,
    ProcessorCostAllocation,
    ProcessorSettlement,
    RelatedParty,
    RelatedPartySettlement,
    RelatedPartyTransaction,
    SettlementLine,
    SettlementRun,
    TaxTreatment,
    Vendor,
    VendorBill,
    VendorPayment,
    VendorPaymentAllocation,
)


@admin.register(FinancePlatformSettings)
class FinancePlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'default_next_payment_date', 'default_schedule_frequency', 'updated_at')


@admin.register(PayeeAccount)
class PayeeAccountAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'actor_type', 'status', 'can_export', 'updated_at')
    list_filter = ('actor_type', 'status')
    search_fields = ('display_name', 'email', 'tax_id', 'account_key')


@admin.register(PayeeSchedule)
class PayeeScheduleAdmin(admin.ModelAdmin):
    list_display = ('payee', 'frequency', 'hold_days', 'next_payment_date')
    list_filter = ('frequency',)
    search_fields = ('payee__display_name',)


@admin.register(PayableLine)
class PayableLineAdmin(admin.ModelAdmin):
    list_display = ('source_reference', 'payee', 'source_type', 'status', 'maturity_status', 'payable_amount', 'due_date')
    list_filter = ('source_type', 'status', 'maturity_status')
    search_fields = ('source_reference', 'source_label', 'payee__display_name')


class PayoutAttachmentInline(admin.TabularInline):
    model = PayoutAttachment
    extra = 0


class PayoutLineAllocationInline(admin.TabularInline):
    model = PayoutLineAllocation
    extra = 0


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('payee', 'amount', 'status', 'paid_at', 'reference', 'partner_message')
    list_filter = ('status',)
    search_fields = ('payee__display_name', 'reference', 'bank_reference')
    inlines = [PayoutAttachmentInline, PayoutLineAllocationInline]


@admin.register(PayoutBatch)
class PayoutBatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'currency', 'created_at', 'paid_at')
    list_filter = ('status', 'currency')
    search_fields = ('name',)


@admin.register(BankExportFile)
class BankExportFileAdmin(admin.ModelAdmin):
    list_display = ('filename', 'adapter_code', 'row_count', 'status', 'created_at')
    list_filter = ('adapter_code', 'status')
    search_fields = ('filename', 'checksum')


# --- Commercial Policy ---

@admin.register(CommercialPolicy)
class CommercialPolicyAdmin(admin.ModelAdmin):
    list_display = ('scope_type', 'scope_id', 'commercial_mode', 'recognition_policy', 'priority', 'is_active')
    list_filter = ('scope_type', 'commercial_mode', 'is_active')
    search_fields = ('scope_id',)


# --- External Revenue ---

@admin.register(ExternalRevenueImportBatch)
class ExternalRevenueImportBatchAdmin(admin.ModelAdmin):
    list_display = ('source', 'status', 'records_received', 'records_created', 'records_failed', 'created_at')
    list_filter = ('status', 'source')


@admin.register(ExternalRevenueRecord)
class ExternalRevenueRecordAdmin(admin.ModelAdmin):
    list_display = ('external_reference', 'organizer', 'gross_amount', 'platform_fee_amount', 'status', 'effective_date')
    list_filter = ('status', 'source_type', 'commercial_mode')
    search_fields = ('external_reference', 'product_label', 'organizer__name')


# --- Settlements ---

class SettlementLineInline(admin.TabularInline):
    model = SettlementLine
    extra = 0


@admin.register(SettlementRun)
class SettlementRunAdmin(admin.ModelAdmin):
    list_display = ('scope_type', 'organizer', 'status', 'gross_collected', 'payable_amount', 'settlement_date')
    list_filter = ('status', 'scope_type')
    search_fields = ('organizer__name',)
    inlines = [SettlementLineInline]


@admin.register(FinancialDocument)
class FinancialDocumentAdmin(admin.ModelAdmin):
    list_display = ('doc_type', 'label', 'original_name', 'created_at')
    list_filter = ('doc_type',)


# --- Vendors & Expenses ---

@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('name', 'vendor_type', 'tax_id', 'country_code', 'status')
    list_filter = ('vendor_type', 'status')
    search_fields = ('name', 'legal_name', 'tax_id')


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')


@admin.register(TaxTreatment)
class TaxTreatmentAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'tax_type', 'rate', 'is_recoverable', 'is_active')
    list_filter = ('tax_type', 'is_recoverable')


class ExpenseLineInline(admin.TabularInline):
    model = ExpenseLine
    extra = 0


@admin.register(VendorBill)
class VendorBillAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'bill_number', 'total_amount', 'status', 'issue_date', 'due_date')
    list_filter = ('status',)
    search_fields = ('bill_number', 'vendor__name')
    inlines = [ExpenseLineInline]


class VendorPaymentAllocationInline(admin.TabularInline):
    model = VendorPaymentAllocation
    extra = 0


@admin.register(VendorPayment)
class VendorPaymentAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'amount', 'status', 'payment_date')
    list_filter = ('status',)
    search_fields = ('vendor__name', 'reference')
    inlines = [VendorPaymentAllocationInline]


@admin.register(ProcessorCostAllocation)
class ProcessorCostAllocationAdmin(admin.ModelAdmin):
    list_display = ('target_type', 'target_id', 'allocation_method', 'allocated_amount')
    list_filter = ('target_type', 'allocation_method')


# --- Related Parties ---

@admin.register(RelatedParty)
class RelatedPartyAdmin(admin.ModelAdmin):
    list_display = ('name', 'party_type', 'status')
    list_filter = ('party_type', 'status')
    search_fields = ('name', 'legal_name')


@admin.register(RelatedPartyTransaction)
class RelatedPartyTransactionAdmin(admin.ModelAdmin):
    list_display = ('related_party', 'transaction_type', 'amount', 'status', 'transaction_date')
    list_filter = ('transaction_type', 'status')


@admin.register(RelatedPartySettlement)
class RelatedPartySettlementAdmin(admin.ModelAdmin):
    list_display = ('related_party', 'amount', 'status', 'payment_date')
    list_filter = ('status',)


# --- Treasury ---

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'bank_name', 'currency', 'country_code', 'is_active')
    list_filter = ('is_active', 'currency')


@admin.register(BankStatementLine)
class BankStatementLineAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'statement_date', 'amount', 'status', 'description')
    list_filter = ('status', 'bank_account')


@admin.register(BankBalanceSnapshot)
class BankBalanceSnapshotAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'snapshot_date', 'balance', 'source')


@admin.register(ProcessorSettlement)
class ProcessorSettlementAdmin(admin.ModelAdmin):
    list_display = ('processor_name', 'settlement_reference', 'net_amount', 'status', 'payment_date')
    list_filter = ('processor_name', 'status')


@admin.register(ProcessorClearingEntry)
class ProcessorClearingEntryAdmin(admin.ModelAdmin):
    list_display = ('processor_settlement', 'entry_type', 'amount')
    list_filter = ('entry_type',)


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'period_start', 'period_end', 'status', 'unexplained_difference')
    list_filter = ('status',)


# --- Ledger ---

@admin.register(LedgerAccount)
class LedgerAccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'subtype', 'is_active')
    list_filter = ('account_type', 'is_active')
    search_fields = ('code', 'name')


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    readonly_fields = ('ledger_account', 'debit_amount', 'credit_amount', 'currency')


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('idempotency_key', 'posting_event', 'status', 'posting_date', 'is_balanced')
    list_filter = ('status', 'posting_event')
    search_fields = ('idempotency_key', 'reference', 'description')
    inlines = [JournalLineInline]
