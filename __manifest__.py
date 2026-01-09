{
    "name": "Initial Balances Import",
    "summary": "Import receivable and payable balances from AFIP CSV files",
    "description": """
Initial Balances Import
=======================

This module allows importing receivable and payable balances, or new invoices, 
from AFIP (Argentina Federal Tax Authority) CSV format files.

Features
--------
* Import initial balances (total amount without VAT details)
* Import new invoices with VAT details (rate and tax amount)
* Duplicate verification for new invoices
* Works with AFIP CSV format files
* Multi-currency support (DOL -> USD, PES -> ARS)
* Automatic exchange rate updates
* Automatic partner creation (suppliers/customers)

Import Types
------------
* **Initial Balances**: Import existing balances without duplicate verification
* **New Documents**: Import new invoices with duplicate verification and VAT details

This module is designed specifically for the Argentine localization and requires 
the l10n_ar module to be installed.
    """,
    "author": "Your Company Name",
    "website": "https://www.yourcompany.com",
    "category": "Accounting/Localizations",
    "version": "19.0.1.0.0",
    "license": "LGPL-3",
    "depends": [
        "base",
        "account",
        "l10n_ar",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "views/account_iva_file_views.xml",
        "views/account_move_views.xml",
        "views/menus.xml",
    ],
    "assets": {},
    "images": [
        "static/description/banner.png",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
