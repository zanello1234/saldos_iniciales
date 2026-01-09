=======================
Accounting AFIP Import
=======================

.. |badge1| image:: https://img.shields.io/badge/maturity-Beta-yellow.png
    :target: https://odoo-community.org/page/development-status
    :alt: Beta
.. |badge2| image:: https://img.shields.io/badge/licence-LGPL--3-blue.png
    :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3

|badge1| |badge2|

This module allows importing invoices (Purchases and Sales) directly from AFIP (Argentina Federal Tax Authority) "Mis Comprobantes" CSV files into Odoo. It is designed to handle both initial balances migration and regular monthly processing.

**Table of contents**

.. contents::
   :local:

Features
========

**Core Functionality**

* **Import Sources**: Supports "Mis Comprobantes" CSV format (Received and Issued).
* **Operation Types**: Purchase (Vendor Bills) and Sale (Customer Invoices).
* **Import Modes**:
    * *Initial Balances*: Imports total amount as a single line (useful for migration).
    * *New Documents*: Detailed import with VAT rates (21%, 10.5%, 27%, etc.) mapped to Odoo taxes.
* **Partner Creation**: Automatically creates Suppliers/Customers based on CUIT and Fiscal Position (RI, Monotributo, Consumidor Final).

**Advanced Capabilities**

* **Multi-Currency Support**:
    * Detects USD invoices automatically (supports 'DOL' and 'USD' codes).
    * Creates ``res.currency.rate`` records for the invoice date if missing.
    * Warning system for "Converted to Pesos" files to prevent currency mix-ups.
* **Robust Error Handling**:
    * "Errors" tab with line-by-line detail of failed rows (Invalid CUIT, Zero Amount, Duplicate, etc.).
    * Validates columns, CUIT format, and existing duplicates before creation.
* **Process Control**:
    * **Analyze**: Generates a detailed report without modifying accounting data.
    * **Analysis Report**: Shows breakdown of documents by Currency (ARS vs USD), totals, and validation stats.
    * **Process**: Creates the invoices in Odoo.
    * **Rollback**: One-click cleanup to delete generated invoices, rates, and partners if mistakes are found (only if draft/unused).
    * **Reset to Draft**: Allows re-uploading or changing parameters after analysis.

Installation
============

This module depends on:

* ``account``
* ``l10n_ar`` (Argentine Localization)
* ``mail``

Configuration
=============

No specific settings required. Ensure your Odoo instance has:
* Argentine taxes configured.
* Currencies (USD) active if importing foreign currency documents.

Usage
=====

1. Go to **Accounting > Importar comprobantes**.
2. Click **Create** and select the Journal (e.g., Vendor Bills).
3. Choose **Operation Type** (Purchase/Sale) and **Import Type** (New Documents).
4. Upload the CSV file downloaded from AFIP ("Mis Comprobantes").
   * *Tip*: For USD invoices, download the "Montos en moneda original" CSV.
5. Click **Analyze File**.
6. Review the **Analysis Report** tab for totals and the **Errors** tab for any skipped lines.
7. If satisfied, click **Process File**.
8. If you need to fix something, click **Rollback** (if processed) or **Reset to Draft**.

Known issues / Roadmap
======================

* Currently supports standard AFIP CSV columns. Custom formats may require code adaptation.

Bug Tracker
===========

Bugs are tracked on GitHub Issues.

Credits
=======

**Authors**

* Martin Zanello

**Maintainers**

This module is maintained by Previnca.

