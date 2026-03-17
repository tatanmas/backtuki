"""Finance domain – Tuki's enterprise financial system.

Layers:
  1. Operational – CommercialPolicy, ExternalRevenueRecord, Order dates
  2. Custodial  – SettlementRun, SettlementLine, PayableLine, Payout
  3. Expenses   – Vendor, VendorBill, ExpenseLine, TaxTreatment
  4. Ledger     – LedgerAccount, JournalEntry, JournalLine (double-entry, idempotent)
  5. Treasury   – BankAccount, ProcessorSettlement, BankReconciliation
  6. Related    – RelatedParty, RelatedPartyTransaction
  7. Reporting  – balance_sheet, income_statement, cash_flow_basic, trial_balance
"""
