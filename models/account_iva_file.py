# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Module for importing initial balances from AFIP CSV files.

CSV Structure for AFIP Invoices (separated by ;):

RECEIVED INVOICES FORMAT - PURCHASES (30 columns):
Column 1 (index 0): Issue Date
Column 2 (index 1): Document Type
Column 3 (index 2): Point of Sale
Column 4 (index 3): Number From
Column 5 (index 4): Number To
Column 6 (index 5): Authorization Code
Column 7 (index 6): Issuer Document Type
Column 8 (index 7): Issuer Document Number (Supplier CUIT)
Column 9 (index 8): Issuer Name (Supplier Name)
Column 10 (index 9): Receiver Document Type
Column 11 (index 10): Receiver Document Number
Column 12 (index 11): Exchange Rate
Column 13 (index 12): Currency
Column 14 (index 13): Net Amount VAT 0%
Column 15 (index 14): VAT 2.5%
Column 16 (index 15): Net Amount VAT 2.5%
Column 17 (index 16): VAT 5%
Column 18 (index 17): Net Amount VAT 5%
Column 19 (index 18): VAT 10.5%
Column 20 (index 19): Net Amount VAT 10.5%
Column 21 (index 20): VAT 21%
Column 22 (index 21): Net Amount VAT 21%
Column 23 (index 22): VAT 27%
Column 24 (index 23): Net Amount VAT 27%
Column 25 (index 24): Total Net Amount *** TOTAL NET AMOUNT ***
Column 26 (index 25): Non-Taxable Net Amount
Column 27 (index 26): Exempt Operations Amount
Column 28 (index 27): Other Taxes
Column 29 (index 28): Total VAT
Column 30 (index 29): Total Amount *** TOTAL AMOUNT WITH VAT ***

ISSUED INVOICES FORMAT - SALES (28 columns):
Column 1 (index 0): Issue Date
Column 2 (index 1): Document Type
Column 3 (index 2): Point of Sale
Column 4 (index 3): Number From
Column 5 (index 4): Number To
Column 6 (index 5): Authorization Code
Column 7 (index 6): Receiver Document Type
Column 8 (index 7): Receiver Document Number (Customer CUIT)
Column 9 (index 8): Receiver Name (Customer Name)
Column 10 (index 9): Exchange Rate
Column 11 (index 10): Currency
Column 12 (index 11): Net Amount VAT 0%
Column 13 (index 12): VAT 2.5%
Column 14 (index 13): Net Amount VAT 2.5%
Column 15 (index 14): VAT 5%
Column 16 (index 15): Net Amount VAT 5%
Column 17 (index 16): VAT 10.5%
Column 18 (index 17): Net Amount VAT 10.5%
Column 19 (index 18): VAT 21%
Column 20 (index 19): Net Amount VAT 21%
Column 21 (index 20): VAT 27%
Column 22 (index 21): Net Amount VAT 27%
Column 23 (index 22): Total Net Amount *** TOTAL NET AMOUNT ***
Column 24 (index 23): Non-Taxable Net Amount
Column 25 (index 24): Exempt Operations Amount
Column 26 (index 25): Other Taxes
Column 27 (index 26): Total VAT
Column 28 (index 27): Total Amount *** TOTAL AMOUNT WITH VAT ***
"""

import base64
import csv
import re
from datetime import datetime
from io import StringIO

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountIvaFileLineError(models.Model):
    """Model to store detailed line errors during import."""
    _name = "account.iva.file.line.error"
    _description = "Import Line Error"
    _order = "row_number asc"

    account_iva_file_id = fields.Many2one(
        'account.iva.file',
        string='Import File',
        required=True,
        ondelete='cascade',
    )
    row_number = fields.Integer(
        string='Row',
        required=True,
    )
    cuit = fields.Char(
        string='CUIT',
    )
    error_message = fields.Char(
        string='Error Message',
        required=True,
    )
    row_content = fields.Text(
        string='Row Content',
    )


class AccountIvaFile(models.Model):
    """Model for importing initial balances and invoices from AFIP CSV files."""

    _name = "account.iva.file"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Balance Import"
    _order = "date desc, id desc"

    # Basic Fields
    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        tracking=True,
        help="Company to which this import file belongs.",
    )
    operation_type = fields.Selection(
        selection=[
            ('purchase', 'Purchases'),
            ('sale', 'Sales'),
        ],
        string='Operation Type',
        required=True,
        default='purchase',
        tracking=True,
    )
    import_type = fields.Selection(
        selection=[
            ('initial_balances', 'Initial Balances'),
            ('new_documents', 'New Documents'),
        ],
        string='Import Type',
        required=True,
        default='initial_balances',
        tracking=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=False,
        help="Product used for new document import lines.",
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
    )
    date = fields.Date(
        string='Date',
        default=fields.Date.today,
        readonly=True,
    )
    iva_file = fields.Binary(
        string='CSV File',
    )
    filename = fields.Char(
        string='Filename',
    )
    separator = fields.Char(
        string='CSV Separator',
        default=';',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('analyzed', 'Analyzed'),
            ('done', 'Processed'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )

    # Exchange Rate Fields
    usd_exchange_rate = fields.Float(
        string='USD Exchange Rate',
        digits=(12, 4),
        help="Dollar exchange rate for this date (1 USD = X ARS).",
    )
    update_exchange_rates = fields.Boolean(
        string='Update Exchange Rates',
        default=True,
        help="Automatically create/update exchange rates when USD invoices are found.",
    )

    # Related Records
    partner_ids = fields.One2many(
        'res.partner',
        'account_iva_file_id',
        string='Created Partners',
    )
    move_ids = fields.One2many(
        'account.move',
        'account_iva_file_id',
        string='Created Invoices',
    )
    currency_rate_ids = fields.One2many(
        'res.currency.rate',
        'account_iva_file_id',
        string='Updated Exchange Rates',
    )
    error_ids = fields.One2many(
        'account.iva.file.line.error',
        'account_iva_file_id',
        string='Line Errors',
    )

    # Analysis Fields
    analysis_total_rows = fields.Integer(
        string='Total Rows Read',
        readonly=True,
    )
    analysis_valid_rows = fields.Integer(
        string='Valid Rows',
        readonly=True,
    )
    analysis_omitted_rows = fields.Integer(
        string='Omitted Rows',
        readonly=True,
    )
    analysis_success_percentage = fields.Float(
        string='Success Percentage',
        readonly=True,
        digits=(5, 2),
    )
    analysis_total_net = fields.Float(
        string='Total Net',
        readonly=True,
        digits=(12, 2),
    )
    analysis_total_tax = fields.Float(
        string='Total VAT',
        readonly=True,
        digits=(12, 2),
    )
    analysis_total_amount = fields.Float(
        string='Total Amount',
        readonly=True,
        digits=(12, 2),
    )
    analysis_existing_documents = fields.Integer(
        string='Existing Documents',
        readonly=True,
    )
    analysis_new_documents = fields.Integer(
        string='New Documents',
        readonly=True,
    )
    analysis_duplicate_percentage = fields.Float(
        string='Duplicate Percentage',
        readonly=True,
        digits=(5, 2),
    )
    analysis_report = fields.Html(
        string='Analysis Report',
        readonly=True,
    )

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _log_error(self, row_number, message, cuit=False, row_data=False):
        """Log a structured error for a specific row."""
        self.env['account.iva.file.line.error'].create({
            'account_iva_file_id': self.id,
            'row_number': row_number,
            'error_message': message,
            'cuit': cuit,
            'row_content': str(row_data) if row_data else False,
        })

    def btn_rollback(self):
        """Rollback the import process."""
        if self.state != 'done':
            return
        
        # Check if invoices are posted
        posted_moves = self.move_ids.filtered(lambda m: m.state == 'posted')
        if posted_moves:
            raise ValidationError(_("Cannot rollback because some invoices are already posted. Please reset them to draft first."))

        # Delete invoices
        self.move_ids.unlink()

        # Delete currency rates
        self.currency_rate_ids.unlink()

        # Delete ONLY partners created by this file that have no other invoices
        # Safe check: only delete if they have no other accounting moves
        partners_to_delete = self.partner_ids.filtered(lambda p: not self.env['account.move'].search_count([('partner_id', '=', p.id), ('id', 'not in', self.move_ids.ids)]))
        partners_to_delete.unlink()
        
        # Clear errors
        self.error_ids.unlink()
        
        self.state = 'analyzed'

    def btn_reset_to_draft(self):
        """Reset the record to draft state to allow editing and re-analysis."""
        if self.state == 'done':
            raise ValidationError(_("You cannot reset to draft a processed file. Please rollback first."))
            
        self.write({
            'state': 'draft',
            'analysis_report': False,
            'analysis_total_rows': 0,
            'analysis_valid_rows': 0,
            'analysis_omitted_rows': 0,
            'analysis_success_percentage': 0,
            'analysis_total_net': 0,
            'analysis_total_tax': 0,
            'analysis_total_amount': 0,
            'analysis_existing_documents': 0,
            'analysis_new_documents': 0,
            'analysis_duplicate_percentage': 0,
        })
        self.error_ids.unlink()

    # -------------------------------------------------------------------------
    # ONCHANGE METHODS
    # -------------------------------------------------------------------------

    @api.onchange('operation_type')
    def _onchange_operation_type(self):
        """Filter journals by operation type."""
        self.journal_id = False
        return {
            'domain': {
                'journal_id': [('type', '=', self.operation_type)]
            }
        }

    @api.onchange('import_type')
    def _onchange_import_type(self):
        """Clear product when selecting initial balances."""
        if self.import_type == 'initial_balances':
            self.product_id = False

    # -------------------------------------------------------------------------
    # CONSTRAINT METHODS
    # -------------------------------------------------------------------------

    @api.constrains('product_id', 'import_type')
    def _check_product_required(self):
        """Validate that product is required only for new documents."""
        for record in self:
            if record.import_type == 'new_documents' and not record.product_id:
                raise ValidationError(_('Product is required for importing new documents.'))

    # -------------------------------------------------------------------------
    # DOCUMENT NAME GENERATION
    # -------------------------------------------------------------------------

    def _get_document_name_by_type(self, doc_type_code, point_of_sale, doc_number):
        """Generate document name according to AFIP type."""
        try:
            document_types = {
                # Invoices
                '1': 'FA-A',
                '6': 'FA-B',
                '11': 'FA-C',
                # Debit Notes
                '2': 'ND-A',
                '7': 'ND-B',
                '12': 'ND-C',
                # Credit Notes
                '3': 'NC-A',
                '8': 'NC-B',
                '13': 'NC-C',
                # MiPyme
                '201': 'FA-A',
                '202': 'FA-B',
                '203': 'NC-A',
                # Invoice M
                '51': 'FA-M',
                '52': 'ND-M',
                '53': 'NC-M',
            }

            prefix = document_types.get(doc_type_code, 'FA-A')
            formatted_number = f"{prefix} {point_of_sale}-{doc_number}"

            return formatted_number

        except Exception:
            return f"FA-A {point_of_sale}-{doc_number}"

    # -------------------------------------------------------------------------
    # AMOUNT PARSING
    # -------------------------------------------------------------------------

    def _parse_amount(self, amount_str):
        """Parse amount string handling different formats."""
        try:
            amount_clean = amount_str.replace(',', '.').replace(' ', '').replace('$', '')
            parts = amount_clean.split('.')
            if len(parts) > 2:
                amount_clean = ''.join(parts[:-1]) + '.' + parts[-1]
            elif len(parts) == 2 and len(parts[1]) > 2:
                amount_clean = ''.join(parts)

            return float(amount_clean)
        except Exception:
            return 0.0

    # -------------------------------------------------------------------------
    # ANALYZE FILE
    # -------------------------------------------------------------------------

    def btn_analyze_file(self):
        """Analyze the file without processing it."""
        if not self.iva_file:
            raise ValidationError(_('You must upload a CSV file.'))
        
        try:
            csv_data = base64.b64decode(self.iva_file)
            data_file = StringIO(csv_data.decode("utf-8"))
            csv_reader = csv.reader(data_file, delimiter=self.separator)

            total_rows = 0
            valid_rows = 0
            duplicados_existentes = 0
            comprobantes_nuevos = 0
            total_neto = 0.0
            total_iva = 0.0
            total_general = 0.0

            # Totals by currency
            total_ars = {
                'count': 0,
                'neto': 0.0,
                'iva': 0.0,
                'total': 0.0
            }
            total_usd = {
                'count': 0,
                'neto': 0.0,
                'iva': 0.0,
                'total': 0.0
            }

            filas_cortas = 0
            cuits_invalidos = 0
            montos_cero = 0

            for i, row in enumerate(csv_reader):
                if i == 0:
                    continue

                total_rows += 1

                expected_cols = 30 if self.operation_type == 'purchase' else 28
                if len(row) < expected_cols:
                    filas_cortas += 1
                    continue

                try:
                    cuit = row[7].strip().replace('-', '').replace(' ', '') if row[7] else ''
                    doc_type_code = row[1].strip() if len(row) > 1 else ''

                    if self.operation_type == 'purchase':
                        currency_code = row[12].strip().upper() if len(row) > 12 else ''
                        if doc_type_code == '11':
                            amount_str = row[29].strip().replace(' ', '') if len(row) > 29 and row[29] else '0'
                        else:
                            amount_str = row[24].strip().replace(' ', '') if len(row) > 24 and row[24] else '0'
                    else:
                        currency_code = row[10].strip().upper() if len(row) > 10 else ''
                        if doc_type_code == '11':
                            amount_str = row[27].strip().replace(' ', '') if len(row) > 27 and row[27] else '0'
                        else:
                            amount_str = row[22].strip().replace(' ', '') if len(row) > 22 and row[22] else '0'

                    if not cuit or len(cuit) < 7:
                        cuits_invalidos += 1
                        continue

                    amount = self._parse_amount(amount_str)

                    if amount == 0:
                        montos_cero += 1
                        continue

                    valid_rows += 1

                    # Accumulate by currency
                    neto = 0.0
                    iva = 0.0

                    if amount > 0:
                        if doc_type_code in ['1', '2', '3', '51', '52', '53', '201']:
                            neto = amount / 1.21
                            iva = amount - neto
                        elif doc_type_code in ['202', '203']:
                            neto = amount / 1.105
                            iva = amount - neto
                        else:
                            neto = amount
                            iva = 0.0

                    if currency_code in ['DOL', 'USD']:
                        total_usd['count'] += 1
                        total_usd['neto'] += neto
                        total_usd['iva'] += iva
                        total_usd['total'] += amount
                        
                        # Add to general total (estimated ARS just for single field storage? 
                        # Or better just store ARS part in fields. For now we sum raw just for non-breaking behavior, 
                        # but the report will show the truth)
                        # Let's NOT mix currencies in the simple totals fields if possible, but they are Floats.
                        # We'll just sum them raw as legacy behavior, but the HTML report is what matters.
                        total_neto += neto
                        total_iva += iva
                        total_general += amount
                    else:
                        total_ars['count'] += 1
                        total_ars['neto'] += neto
                        total_ars['iva'] += iva
                        total_ars['total'] += amount

                        total_neto += neto
                        total_iva += iva
                        total_general += amount


                    if self.import_type == 'new_documents':
                        point_of_sale = row[2].zfill(5) if len(row) > 2 and row[2] else '00001'
                        doc_number = row[3].zfill(8) if len(row) > 3 and row[3] else '00000001'
                        document_number = f"{point_of_sale}-{doc_number}"

                        partner = self.env['res.partner'].search([('vat', '=', cuit)], limit=1)
                        if partner:
                            is_duplicate = self._check_duplicate_document(partner, document_number, doc_type_code)
                            if is_duplicate:
                                duplicados_existentes += 1
                            else:
                                comprobantes_nuevos += 1
                        else:
                            comprobantes_nuevos += 1
                    else:
                        comprobantes_nuevos += 1

                except Exception:
                    continue

            success_percentage = (valid_rows / total_rows * 100) if total_rows > 0 else 0
            duplicate_percentage = (duplicados_existentes / valid_rows * 100) if valid_rows > 0 else 0

            analysis_message = f"""📊 DETAILED FILE ANALYSIS:

📋 GENERAL SUMMARY:
• Total rows read: {total_rows}
• Valid processable rows: {valid_rows}
• Omitted rows: {total_rows - valid_rows}
• Success percentage: {success_percentage:.1f}%

💰 CURRENCY BREAKDOWN:

🇦🇷 PESOS (ARS):
• Count: {total_ars['count']}
• Total Net: ${total_ars['neto']:,.2f}
• Total VAT: ${total_ars['iva']:,.2f}
• Total: ${total_ars['total']:,.2f}

🇺🇸 DOLLARS (USD):
• Count: {total_usd['count']}
• Total Net: U$S {total_usd['neto']:,.2f}
• Total VAT: U$S {total_usd['iva']:,.2f}
• Total: U$S {total_usd['total']:,.2f}

🔍 OMITTED ROWS DETAILS:
• Rows with less than {expected_cols} columns: {filas_cortas}
• Invalid CUITs (less than 7 digits): {cuits_invalidos}
• Zero amounts: {montos_cero}

🔍 DOCUMENT STATUS:"""

            if self.import_type == 'new_documents':
                analysis_message += f"""
• Existing documents: {duplicados_existentes}
• New documents detected: {comprobantes_nuevos}
• Duplicate ratio: {duplicate_percentage:.1f}%"""
            else:
                analysis_message += f"""
• Initial balances to process: {comprobantes_nuevos}"""

            analysis_message += """

✅ FILE READY TO PROCESS"""

            self.write({
                'analysis_total_rows': total_rows,
                'analysis_valid_rows': valid_rows,
                'analysis_omitted_rows': total_rows - valid_rows,
                'analysis_success_percentage': success_percentage,
                'analysis_total_net': total_neto,
                'analysis_total_tax': total_iva,
                'analysis_total_amount': total_general,
                'analysis_existing_documents': duplicados_existentes,
                'analysis_new_documents': comprobantes_nuevos,
                'analysis_duplicate_percentage': duplicate_percentage,
                'analysis_report': f'<pre>{analysis_message}</pre>',
                'state': 'analyzed'
            })

        except Exception as e:
            raise ValidationError(_('Error analyzing file: %s') % str(e))

    # -------------------------------------------------------------------------
    # PROCESS FILE
    # -------------------------------------------------------------------------

    def btn_process_file(self):
        """Process the analyzed file and create invoices."""
        if not self.iva_file:
            raise ValidationError(_('You must upload a CSV file.'))

        if self.state != 'analyzed':
            raise ValidationError(_('You must analyze the file before processing.'))

        try:
            csv_data = base64.b64decode(self.iva_file)
            data_file = StringIO(csv_data.decode("utf-8"))
            csv_reader = csv.reader(data_file, delimiter=self.separator)

            total_rows = 0
            facturas_creadas = 0
            facturas_omitidas = 0
            partners_creados = 0
            duplicados_omitidos = 0

            errores_detallados = {
                'filas_cortas': 0,
                'cuits_invalidos': 0,
                'montos_cero': 0,
                'partners_invalidos': 0,
                'duplicados': 0,
                'errores_creacion': 0
            }

            partner_cache = {}
            duplicate_cache = {}

            # Pre-load CUITs from CSV
            csv_cuits = set()
            csv_data_temp = base64.b64decode(self.iva_file)
            data_file_temp = StringIO(csv_data_temp.decode("utf-8"))
            csv_reader_temp = csv.reader(data_file_temp, delimiter=self.separator)

            for i, row in enumerate(csv_reader_temp):
                if i == 0:
                    continue
                if len(row) > 7 and row[7]:
                    cuit = row[7].strip().replace('-', '').replace(' ', '')
                    if cuit and len(cuit) >= 7:
                        csv_cuits.add(cuit)

            # Pre-load existing partners
            if csv_cuits:
                existing_partners = self.env['res.partner'].search([('vat', 'in', list(csv_cuits))])
                for partner in existing_partners:
                    if partner.vat:
                        partner_cache[partner.vat] = partner
            
            # Pre-load existing invoices for duplicate detection
            if self.import_type == 'new_documents':
                partner_ids_to_check = [p.id for p in partner_cache.values()]

                if partner_ids_to_check:
                    existing_invoices = self.env['account.move'].search([
                        ('state', '!=', 'cancel'),
                        ('name', '!=', False),
                        ('partner_id', 'in', partner_ids_to_check)
                    ])

                    for invoice in existing_invoices:
                        if invoice.name and invoice.partner_id:
                            cache_keys = [(invoice.partner_id.id, invoice.name)]
                            if invoice.ref:
                                cache_keys.append((invoice.partner_id.id, invoice.ref))

                            for key in cache_keys:
                                duplicate_cache[key] = True

            # Process file
            for i, row in enumerate(csv_reader):
                if i == 0:
                    continue

                total_rows += 1

                expected_cols = 30 if self.operation_type == 'purchase' else 28
                if len(row) < expected_cols:
                    facturas_omitidas += 1
                    errores_detallados['filas_cortas'] += 1
                    self._log_error(i, f"Omitted due to insufficient columns ({len(row)}<{expected_cols})", row_data=row)
                    continue

                try:
                    cuit = row[7].strip().replace('-', '').replace(' ', '') if row[7] else ''
                    name = row[8].strip() if row[8] else 'No name'
                    doc_type_code = row[1].strip() if len(row) > 1 else ''

                    if self.operation_type == 'purchase':
                        if doc_type_code == '11':
                            amount_str = row[29].strip().replace(' ', '') if len(row) > 29 and row[29] else '0'
                        else:
                            amount_str = row[24].strip().replace(' ', '') if len(row) > 24 and row[24] else '0'
                    else:
                        if doc_type_code == '11':
                            amount_str = row[27].strip().replace(' ', '') if len(row) > 27 and row[27] else '0'
                        else:
                            amount_str = row[22].strip().replace(' ', '') if len(row) > 22 and row[22] else '0'

                    # Exchange Rate Logic
                    if self.update_exchange_rates:
                        try:
                            if self.operation_type == 'purchase':
                                exchange_rate_str = row[11].strip().replace(',', '.') if len(row) > 11 else '0'
                                currency_code = row[12].strip().upper() if len(row) > 12 else ''
                            else:
                                exchange_rate_str = row[9].strip().replace(',', '.') if len(row) > 9 else '0'
                                currency_code = row[10].strip().upper() if len(row) > 10 else ''

                            if currency_code in ['DOL', 'USD']:
                                rate_value = float(exchange_rate_str)
                                if rate_value > 0:
                                    # Parse Date
                                    date_str = row[0].strip()
                                    if '/' in date_str:
                                        parts = date_str.split('/')
                                        if len(parts) == 3:
                                            rate_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                                        else:
                                            rate_date = fields.Date.today()
                                    else:
                                        rate_date = fields.Date.today()
                                    
                                    self._create_currency_rate(rate_date, rate_value)
                        except Exception:
                            pass

                    if not cuit or len(cuit) < 7:
                        facturas_omitidas += 1
                        errores_detallados['cuits_invalidos'] += 1
                        self._log_error(i, f"Omitted due to invalid CUIT '{cuit}'", cuit=cuit, row_data=row)
                        continue

                    amount = self._parse_amount(amount_str)

                    if amount == 0:
                        facturas_omitidas += 1
                        errores_detallados['montos_cero'] += 1
                        self._log_error(i, "Omitted due to zero amount", cuit=cuit, row_data=row)
                        continue

                    partner_existed_before = cuit in partner_cache
                    partner = self._get_or_create_partner_optimized(cuit, name, row, partner_cache)

                    if partner and not partner_existed_before and cuit in partner_cache:
                        partners_creados += 1

                    if not partner:
                        facturas_omitidas += 1
                        errores_detallados['partners_invalidos'] += 1
                        self._log_error(i, f"Omitted due to invalid partner for CUIT '{cuit}'", cuit=cuit, row_data=row)
                        continue

                    point_of_sale = row[2].zfill(5) if len(row) > 2 and row[2] else '00001'
                    doc_number = row[3].zfill(8) if len(row) > 3 and row[3] else '00000001'
                    document_ref = f"{point_of_sale}-{doc_number}"

                    if self.import_type == 'new_documents':
                        is_duplicate = self._check_duplicate_optimized(partner, document_ref, doc_type_code, duplicate_cache)
                        if is_duplicate:
                            facturas_omitidas += 1
                            duplicados_omitidos += 1
                            errores_detallados['duplicados'] += 1
                            self._log_error(i, f"Omitted duplicate - Partner: {partner.name}, Doc: {document_ref}", cuit=cuit, row_data=row)
                            continue

                    factura = self._create_invoice_simple(partner, row, amount, doc_type_code, point_of_sale, doc_number)

                    if factura:
                        facturas_creadas += 1
                    else:
                        facturas_omitidas += 1
                        errores_detallados['errores_creacion'] += 1
                        self._log_error(i, f"Error creating invoice - Partner: {partner.name}, Amount: {amount}", cuit=cuit, row_data=row)

                except Exception as e:
                    facturas_omitidas += 1
                    errores_detallados['errores_creacion'] += 1
                    self._log_error(i, f"Processing error - {type(e).__name__}: {str(e)[:100]}", cuit=cuit if 'cuit' in locals() else False, row_data=row)
                    continue

            self.state = 'done'

        except Exception as e:
            raise ValidationError(_('Error processing file: %s') % str(e))

    # -------------------------------------------------------------------------
    # EXCHANGE RATE METHODS
    # -------------------------------------------------------------------------

    def _create_currency_rate(self, date, rate):
        """Create or update currency rate for USD."""
        currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        if not currency:
            return

        existing_rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', currency.id),
            ('name', '=', date),
            ('company_id', '=', self.company_id.id)
        ], limit=1)

        if not existing_rate:
            vals = {
                'currency_id': currency.id,
                'name': date,
                'rate': 1.0 / rate if rate > 0 else 0,
                'company_id': self.company_id.id,
                'account_iva_file_id': self.id,
            }
            self.env['res.currency.rate'].create(vals)
        else:
            # If rate exists, link it to this file so the user can see it in the tab
            # Only update if it is not already linked to another file (or just overwrite to show current context)
            existing_rate.write({'account_iva_file_id': self.id})

    # -------------------------------------------------------------------------
    # PARTNER METHODS
    # -------------------------------------------------------------------------

    def _get_or_create_partner_optimized(self, cuit, name, row, partner_cache):
        """Optimized method to get or create partner using cache."""
        try:
            if cuit in partner_cache:
                return partner_cache[cuit]

            doc_type_code = row[1].strip() if len(row) > 1 else ''

            partner_vals = {
                'name': name,
                'vat': cuit,
                'company_type': 'company',
                'account_iva_file_id': self.id,
                'company_id': self.company_id.id,
            }

            try:
                cuit_type = self.env['l10n_latam.identification.type'].search([
                    ('name', 'ilike', 'CUIT')
                ], limit=1)
                if cuit_type:
                    partner_vals['l10n_latam_identification_type_id'] = cuit_type.id
            except Exception:
                pass

            try:
                fiscal_positions = {
                    'ri': ['1', '2', '3', '201'],
                    'cf': ['6', '7', '8', '202'],
                    'mono': ['11', '12', '13', '203'],
                }

                fiscal_name = None
                if doc_type_code in fiscal_positions['ri']:
                    fiscal_name = 'IVA Responsable Inscripto'
                elif doc_type_code in fiscal_positions['cf']:
                    fiscal_name = 'Consumidor Final'
                elif doc_type_code in fiscal_positions['mono']:
                    fiscal_name = 'Responsable Monotributo'
                else:
                    fiscal_name = 'IVA Responsable Inscripto'

                if fiscal_name:
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', fiscal_name)
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
            except Exception:
                pass

            if self.operation_type == 'purchase':
                partner_vals['supplier_rank'] = 1
            else:
                partner_vals['customer_rank'] = 1

            partner = self.env['res.partner'].with_context(check_vat=False).create(partner_vals)
            partner_cache[cuit] = partner

            return partner

        except Exception:
            fallback_partner = self.env['res.partner'].search([
                ('vat', '=', cuit),
                ('company_id', 'in', [self.company_id.id, False])
            ], limit=1)
            if fallback_partner:
                partner_cache[cuit] = fallback_partner
                return fallback_partner
            return None

    # -------------------------------------------------------------------------
    # DUPLICATE DETECTION
    # -------------------------------------------------------------------------

    def _check_duplicate_document(self, partner, document_number, doc_type_code):
        """Check if a duplicate document exists BEFORE creating the invoice."""
        try:
            point_of_sale, doc_num = document_number.split('-') if '-' in document_number else ('00001', document_number)
            document_name_afip = self._get_document_name_by_type(doc_type_code, point_of_sale, doc_num)

            existing_by_name = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('name', '=', document_name_afip),
                ('state', '!=', 'cancel')
            ], limit=1)

            if existing_by_name:
                return True

            search_patterns = [
                f"%{point_of_sale}-{doc_num}%",
                f"%{doc_num}%",
            ]

            for pattern in search_patterns:
                existing_pattern = self.env['account.move'].search([
                    ('partner_id', '=', partner.id),
                    ('name', 'ilike', pattern),
                    ('state', '!=', 'cancel')
                ], limit=1)

                if existing_pattern:
                    return True

            existing_by_ref = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('ref', '=', document_number),
                ('state', '!=', 'cancel')
            ], limit=1)

            if existing_by_ref:
                return True

            return False

        except Exception:
            return False

    def _check_duplicate_optimized(self, partner, document_number, doc_type_code, duplicate_cache):
        """Check duplicates using optimized cache."""
        try:
            point_of_sale, doc_num = document_number.split('-') if '-' in document_number else ('00001', document_number)
            document_name_afip = self._get_document_name_by_type(doc_type_code, point_of_sale, doc_num)

            cache_keys = [
                (partner.id, document_name_afip),
                (partner.id, document_number),
            ]

            for cache_key in cache_keys:
                if cache_key in duplicate_cache:
                    return True

            return False

        except Exception:
            return self._check_duplicate_document(partner, document_number, doc_type_code)

    # -------------------------------------------------------------------------
    # INVOICE CREATION
    # -------------------------------------------------------------------------

    def _create_invoice_simple(self, partner, row, amount, doc_type_code=None, point_of_sale=None, doc_number=None):
        """Simplified method to create invoices using Odoo's native logic."""
        try:
            if not partner or len(partner) != 1:
                return None

            if not doc_type_code:
                doc_type_code = row[1].strip() if len(row) > 1 else ''
            if not point_of_sale:
                point_of_sale = row[2].zfill(5) if len(row) > 2 and row[2] else '00001'
            if not doc_number:
                doc_number = row[3].zfill(8) if len(row) > 3 and row[3] else '00000001'

            if self.operation_type == 'purchase':
                move_type = 'in_refund' if doc_type_code in ['3', '8', '13', '203'] else 'in_invoice'
            else:
                move_type = 'out_refund' if doc_type_code in ['3', '8', '13', '203'] else 'out_invoice'

            if self.operation_type == 'purchase':
                currency_code = row[12].strip().upper() if len(row) > 12 else ''
            else:
                currency_code = row[10].strip().upper() if len(row) > 10 else ''

            if currency_code in ['DOL', 'USD']:
                currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
                currency_id = currency.id if currency else self.env.company.currency_id.id
            else:
                currency_id = self.env.company.currency_id.id

            document_name = self._get_document_name_by_type(doc_type_code, point_of_sale, doc_number)
            document_ref = f"{point_of_sale}-{doc_number}"

            l10n_latam_document_type_id = False
            if doc_type_code:
                doc_type = self.env['l10n_latam.document.type'].search([
                    ('code', '=', doc_type_code)
                ], limit=1)
                if doc_type:
                    l10n_latam_document_type_id = doc_type.id

            if self.import_type == 'initial_balances':
                tax_ids = self._detect_tax_from_csv_row(row, doc_type_code)
                line_vals = {
                    'name': 'Initial balance',
                    'quantity': 1,
                    'price_unit': amount,
                    'tax_ids': [(6, 0, tax_ids)],
                }
            else:
                if self.product_id:
                    tax_ids = self._get_taxes_for_document(doc_type_code)
                    line_vals = {
                        'product_id': self.product_id.id,
                        'name': self.product_id.name or 'Invoice',
                        'quantity': 1,
                        'price_unit': amount,
                        'product_uom_id': self.product_id.uom_id.id,
                        'tax_ids': [(6, 0, tax_ids)],
                    }
                else:
                    line_vals = {
                        'name': 'Invoice',
                        'quantity': 1,
                        'price_unit': amount,
                        'tax_ids': [(6, 0, [])],
                    }

            try:
                if len(row) > 0 and row[0] and row[0].strip():
                    date_str = row[0].strip()
                    if '/' in date_str:
                        parts = date_str.split('/')
                        if len(parts) == 3:
                            try:
                                invoice_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                            except Exception:
                                invoice_date = fields.Date.today()
                        else:
                            invoice_date = fields.Date.today()
                    else:
                        invoice_date = date_str
                else:
                    invoice_date = fields.Date.today()
            except Exception:
                invoice_date = fields.Date.today()

            invoice_vals = {
                'move_type': move_type,
                'partner_id': partner.id,
                'invoice_date': invoice_date,
                'journal_id': self.journal_id.id,
                'account_iva_file_id': self.id,
                'file_amount': amount,
                'currency_id': currency_id,
                'company_id': self.company_id.id,
                'invoice_line_ids': [(0, 0, line_vals)],
            }

            if self.import_type == 'new_documents':
                invoice_vals['ref'] = document_ref
                if l10n_latam_document_type_id:
                    invoice_vals['l10n_latam_document_type_id'] = l10n_latam_document_type_id

            try:
                factura = self.env['account.move'].create(invoice_vals)

                try:
                    factura.write({'name': document_name})
                except Exception:
                    pass

                return factura
            except Exception:
                return None

        except Exception:
            return None

    # -------------------------------------------------------------------------
    # TAX DETECTION
    # -------------------------------------------------------------------------

    def _detect_tax_from_csv_row(self, row, doc_type_code):
        """Detect VAT rate from CSV row data."""
        try:
            tax_ids = []

            def parse_amount(value):
                try:
                    if not value or value.strip() in ['', '0', '0,00', '0.00']:
                        return 0.0
                    cleaned = value.strip().replace(',', '.').replace(' ', '').replace('$', '')
                    return float(cleaned)
                except Exception:
                    return 0.0

            if self.operation_type == 'purchase':
                iva_21_amount = parse_amount(row[20]) if len(row) > 20 else 0.0
                iva_10_5_amount = parse_amount(row[18]) if len(row) > 18 else 0.0
                iva_27_amount = parse_amount(row[22]) if len(row) > 22 else 0.0
                iva_5_amount = parse_amount(row[16]) if len(row) > 16 else 0.0
                iva_2_5_amount = parse_amount(row[14]) if len(row) > 14 else 0.0
                no_taxable_amount = parse_amount(row[25]) if len(row) > 25 else 0.0
            else:
                iva_21_amount = parse_amount(row[18]) if len(row) > 18 else 0.0
                iva_10_5_amount = parse_amount(row[16]) if len(row) > 16 else 0.0
                iva_27_amount = parse_amount(row[20]) if len(row) > 20 else 0.0
                iva_5_amount = parse_amount(row[14]) if len(row) > 14 else 0.0
                iva_2_5_amount = parse_amount(row[12]) if len(row) > 12 else 0.0
                no_taxable_amount = parse_amount(row[23]) if len(row) > 23 else 0.0

            tax_amounts = [
                (27, iva_27_amount),
                (21, iva_21_amount),
                (10.5, iva_10_5_amount),
                (5, iva_5_amount),
                (2.5, iva_2_5_amount),
            ]

            for tax_amount, iva_value in tax_amounts:
                if iva_value > 0:
                    tax = self._find_tax_by_amount(tax_amount)
                    if tax:
                        tax_ids.append(tax.id)

            if no_taxable_amount > 0:
                tax_use = 'purchase' if self.operation_type == 'purchase' else 'sale'
                tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', tax_use),
                    ('amount', '=', 0),
                    ('company_id', '=', self.company_id.id),
                    '|',
                    ('name', 'ilike', 'No Gravado'),
                    ('name', 'ilike', 'Untaxed')
                ], limit=1)
                if tax:
                    tax_ids.append(tax.id)

            if not tax_ids and doc_type_code == '11':
                tax_use = 'purchase' if self.operation_type == 'purchase' else 'sale'
                tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', tax_use),
                    ('company_id', '=', self.company_id.id),
                    '|', '|', '|',
                    ('name', 'ilike', 'IVA No Corresp'),
                    ('name', 'ilike', 'IVA No Correspond'),
                    ('name', 'ilike', 'No Correspond'),
                    ('name', 'ilike', 'No Corresp')
                ], limit=1)
                if tax:
                    tax_ids.append(tax.id)

            return tax_ids

        except Exception:
            return []

    def _find_tax_by_amount(self, amount):
        """Find tax by percentage."""
        try:
            tax_use = 'purchase' if self.operation_type == 'purchase' else 'sale'
            tax = self.env['account.tax'].search([
                ('type_tax_use', '=', tax_use),
                ('amount', '=', amount),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            return tax
        except Exception:
            return None

    def _get_taxes_for_document(self, doc_type_code):
        """Get taxes according to document type."""
        try:
            tax_ids = []
            tax_use = 'purchase' if self.operation_type == 'purchase' else 'sale'

            iva_21_docs = ['1', '2', '3', '51', '52', '53']
            iva_10_5_docs = ['201', '202', '203']
            no_iva_docs = ['6', '7', '12', '13']
            iva_no_corresp_docs = ['11']

            if doc_type_code in iva_21_docs:
                tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', tax_use),
                    ('amount', '=', 21),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
                if tax:
                    tax_ids.append(tax.id)

            elif doc_type_code in iva_10_5_docs:
                tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', tax_use),
                    ('amount', '=', 10.5),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
                if tax:
                    tax_ids.append(tax.id)

            elif doc_type_code in iva_no_corresp_docs:
                tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', tax_use),
                    ('company_id', '=', self.company_id.id),
                    '|', '|', '|',
                    ('name', 'ilike', 'IVA No Corresp'),
                    ('name', 'ilike', 'IVA No Correspond'),
                    ('name', 'ilike', 'No Correspond'),
                    ('name', 'ilike', 'No Corresp')
                ], limit=1)
                if tax:
                    tax_ids.append(tax.id)

            elif doc_type_code in no_iva_docs:
                tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', tax_use),
                    ('amount', '=', 0),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
                if tax:
                    tax_ids.append(tax.id)

            else:
                tax = self.env['account.tax'].search([
                    ('type_tax_use', '=', tax_use),
                    ('amount', '=', 21),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
                if tax:
                    tax_ids.append(tax.id)

            return tax_ids

        except Exception:
            return []


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    account_iva_file_id = fields.Many2one(
        'account.iva.file',
        string='Import File',
        ondelete='cascade',
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Computed field for displaying exchange rate in the tree view
    display_exchange_rate = fields.Float(
        string='Exchange Rate',
        compute='_compute_display_exchange_rate',
        digits=(12, 4),
    )

    @api.depends('amount_total', 'amount_total_signed', 'currency_id')
    def _compute_display_exchange_rate(self):
        for move in self:
            if move.currency_id == move.company_id.currency_id:
                move.display_exchange_rate = 1.0
            elif move.amount_total != 0:
                move.display_exchange_rate = abs(move.amount_total_signed / move.amount_total)
            else:
                move.display_exchange_rate = 0.0
