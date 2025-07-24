# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class ImportInvoiceAccountSelection(models.TransientModel):
    _name = 'import.invoice.account.selection'
    _description = 'Selección de Cuentas para Facturas Importadas'

    iva_file_id = fields.Many2one('account.iva.file', string='Archivo IVA', readonly=True)
    invoice_data_ids = fields.One2many('import.invoice.account.line.data', 'wizard_id', string='Líneas de factura')
    
    def confirm_selection(self):
        """Continuar con la importación después de seleccionar cuentas"""
        # Crear un diccionario para almacenar las selecciones de cuentas
        account_selections = {}
        
        for line in self.invoice_data_ids:
            # Usamos el número de línea como clave
            key = line.line_number
            account_selections[key] = {
                'vat_account_id': line.vat_account_id.id if line.vat_account_id else False,
                'novat_account_id': line.novat_account_id.id if line.novat_account_id else False,
                'other_account_id': line.other_account_id.id if line.other_account_id else False
            }
        
        # Ahora importamos usando las cuentas seleccionadas
        return self.iva_file_id.with_context(
            manual_account_selection=True,
            account_selections=account_selections
        ).continue_import_with_accounts()

class ImportInvoiceAccountLineData(models.TransientModel):
    _name = 'import.invoice.account.line.data'
    _description = 'Datos de Línea para Selección de Cuentas'
    
    wizard_id = fields.Many2one('import.invoice.account.selection', string='Wizard')
    line_number = fields.Integer('Línea en archivo')
    invoice_number = fields.Char('Número de Factura')
    partner_name = fields.Char('Proveedor')
    amount_vat = fields.Float('Importe Gravado')
    amount_novat = fields.Float('Importe No Gravado')
    amount_other = fields.Float('Otros Tributos')
    
    vat_account_id = fields.Many2one('account.account', string='Cuenta Gravado',
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable')), ('deprecated', '=', False)]")
    novat_account_id = fields.Many2one('account.account', string='Cuenta No Gravado',
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable')), ('deprecated', '=', False)]")
    other_account_id = fields.Many2one('account.account', string='Cuenta Otros Tributos',
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable')), ('deprecated', '=', False)]")