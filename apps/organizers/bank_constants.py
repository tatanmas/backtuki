"""
Bank constants for Chile - used for transfer templates and banking details forms.
Values must match the bank's Plantilla Beneficiarios format.
"""

# Chile account types (TIPO_CUENTA_CL_Chile)
ACCOUNT_TYPE_CC = "CC - Cuenta Corriente"
ACCOUNT_TYPE_CA = "CA - Cuenta de Ahorros"
ACCOUNT_TYPE_CV = "CV - Cuenta a la Vista"

CHILE_ACCOUNT_TYPES = [
    (ACCOUNT_TYPE_CC, "Cuenta Corriente"),
    (ACCOUNT_TYPE_CA, "Cuenta de Ahorros"),
    (ACCOUNT_TYPE_CV, "Cuenta a la Vista"),
]

# Document types for Chile
CHILE_DOCUMENT_TYPES = [
    ("RUT", "RUT"),
]

# Recipient types (TIPO DESTINATARIO)
RECIPIENT_TYPE_PERSONA = "Persona"
RECIPIENT_TYPE_EMPRESA = "Empresa"

RECIPIENT_TYPES = [
    (RECIPIENT_TYPE_PERSONA, "Persona"),
    (RECIPIENT_TYPE_EMPRESA, "Empresa"),
]

# Map BillingDetails.person_type to recipient type
PERSON_TYPE_TO_RECIPIENT = {
    "natural": RECIPIENT_TYPE_PERSONA,
    "juridica": RECIPIENT_TYPE_EMPRESA,
}

# Chile banks - format "CODE - Bank Name" (BANCOS CHILE from Plantilla Beneficiarios)
CHILE_BANKS = [
    ("17 - Banco BCI / MACHBANK", "Banco BCI / MACHBANK"),
    ("14 - Banco Bice", "Banco Bice"),
    ("2227 - Banco Consorcio", "Banco Consorcio"),
    ("16 - Banco de Chile", "Banco de Chile"),
    ("18 - Banco del Desarrollo", "Banco del Desarrollo"),
    ("24 - Banco Estado", "Banco Estado"),
    ("20 - Banco Falabella", "Banco Falabella"),
    ("21 - Banco Internacional", "Banco Internacional"),
    ("992 - Banco Ripley", "Banco Ripley"),
    ("22 - Banco Santander", "Banco Santander"),
    ("23 - Banco Security", "Banco Security"),
    ("31 - Banco Scotiabank", "Banco Scotiabank"),
    ("1364 - Coopeuch/Dale", "Coopeuch/Dale"),
    ("2954 - Copec Pay", "Copec Pay"),
    ("3369 - Fintual", "Fintual"),
    ("3011 - HSBC", "HSBC"),
    ("3008 - ISWITCH", "ISWITCH"),
    ("27 - Itaú/CorpBanca", "Itaú/CorpBanca"),
    ("3010 - JP Morgan", "JP Morgan"),
    ("2953 - Mercadopago", "Mercadopago"),
    ("2957 - Prepago Los Heroes", "Prepago Los Heroes"),
    ("1362 - Prepago Tenpo", "Prepago Tenpo"),
    ("3314 - Prex", "Prex"),
    ("3375 - Tanner", "Tanner"),
    ("2958 - TAPP Caja los Andes", "TAPP Caja los Andes"),
    ("3009 - Transbank", "Transbank"),
]

# Full display value for each bank (what gets stored in bank_name)
CHILE_BANK_CHOICES = [(code_name, code_name) for code_name, _ in CHILE_BANKS]

# Default country for Chile-based organizers
DEFAULT_COUNTRY_CODE = "CL"
