# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from io import StringIO
import base64
import csv
import logging

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    account_iva_file_id = fields.Many2one('account.iva.file', string='Archivo de IVA')
    file_amount = fields.Float('Monto Archivo IVA')
    requires_review = fields.Boolean(
        string='Requiere revisión',
        default=False,
        help='Marcado automáticamente cuando la factura contiene percepciones u otros conceptos que requieren revisión manual'
    )
    
    @api.model
    def create(self, vals):
        # Crear la factura normalmente
        move = super(AccountMove, self).create(vals)
        
        # Si la factura viene de una importación de IVA, verificar líneas duplicadas
        if move.account_iva_file_id and move.invoice_line_ids:
            # Detectar líneas de IVA por nombre
            iva_keywords = ['iva', 'i.v.a', 'impuesto']
            iva_lines = move.invoice_line_ids.filtered(
                lambda l: l.name and any(keyword in l.name.lower() for keyword in iva_keywords)
            )
            
            if iva_lines:
                _logger.info(f"Se encontraron {len(iva_lines)} líneas de IVA en la factura {move.name}. Se eliminarán.")
                iva_lines.sudo().unlink()
                move.message_post(
                    body=_("Se eliminaron líneas de IVA duplicadas durante la importación."),
                    message_type='notification'
                )
        
        return move

class ResPartner(models.Model):
    _inherit = 'res.partner'

    account_iva_file_id = fields.Many2one('account.iva.file',string='Archivo de IVA')

class AccountIvaFile(models.Model):
    _name = "account.iva.file"
    _inherit = ['mail.thread','mail.activity.mixin']  
    _description = "Importacion IVA"

    name = fields.Char('Nombre', tracking=True)
    product_vat_id = fields.Many2one('product.product', string='Producto IVA (Opcional)')
    product_novat_id = fields.Many2one('product.product', string='Producto No Gravado (Opcional)')
    product_exempt_id = fields.Many2one('product.product', string='Producto Exento (Opcional)')
    product_other_taxes_id = fields.Many2one('product.product', string='Producto Otros Tributos (Opcional)')
    date = fields.Date('Fecha Ingreso', default=fields.Date.today(), readonly=True)
    iva_file = fields.Binary('Archivo')
    separator = fields.Char('Separador', default=';', help="Separador de campos en el archivo CSV")
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("done", "Procesado"),
        ],
        default="draft",
        tracking=True
    )
    partner_ids = fields.One2many(comodel_name="res.partner", inverse_name="account_iva_file_id", string='Proveedores creados', readonly=True)
    move_ids = fields.One2many(comodel_name="account.move", inverse_name="account_iva_file_id", string='Facturas creadas', readonly=True)
    iva_file_name = fields.Char("Nombre del archivo")

    # Additional fields for account configuration
    use_historical_accounts = fields.Boolean(
        string="Sugerir cuentas basado en historial", 
        default=True,
        help="Si está marcado, el sistema sugerirá cuentas contables basándose en facturas anteriores del mismo proveedor"
    )
    manual_account_selection = fields.Boolean(
        string="Selección manual de cuentas",
        default=False,
        help="Si está marcado, el sistema permitirá seleccionar cuentas contables manualmente durante la importación"
    )
    
    # Default accounts (instead of products)
    account_vat_id = fields.Many2one('account.account', string='Cuenta IVA', 
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable')), ('deprecated', '=', False)]")
    account_novat_id = fields.Many2one('account.account', string='Cuenta No Gravado',
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable')), ('deprecated', '=', False)]")
    account_exempt_id = fields.Many2one('account.account', string='Cuenta Exento',
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable')), ('deprecated', '=', False)]")
    account_other_taxes_id = fields.Many2one('account.account', string='Cuenta Otros Tributos',
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable')), ('deprecated', '=', False)]")

    def btn_process_file(self):
        self.ensure_one()
        if not self.iva_file:
            raise ValidationError(_('No hay archivo cargado'))
        
        try:
            csv_lines = self._parse_csv_file()
            existing_invoices, new_invoices = self._process_csv_lines(csv_lines)
            
            if not new_invoices:
                return self._show_no_invoices_message()
            
            if self.manual_account_selection:
                return self._show_account_selection_wizard(new_invoices, csv_lines)
            
            return self._show_import_wizard(existing_invoices, new_invoices)
            
        except Exception as e:
            raise ValidationError(f"Error procesando el archivo: {str(e)}")

    def _parse_csv_file(self):
        """Parse CSV file and return lines"""
        csv_data = base64.b64decode(self.iva_file)
        data_file = StringIO(csv_data.decode("utf-8"))
        data_file.seek(0)
        
        separator = self.separator or ';'
        csv_reader = csv.reader(data_file, delimiter=separator)
        return list(csv_reader)

    def _process_csv_lines(self, csv_lines):
        """Process CSV lines and separate existing and new invoices"""
        existing_invoices = []
        new_invoices = []
        
        for i, items in enumerate(csv_lines):
            if i == 0:  # Skip header
                continue
                
            invoice_data = self._create_invoice_data(items, i + 1)
            
            if self._is_duplicate_invoice(items, invoice_data):
                existing_invoices.append(invoice_data)
            else:
                new_invoices.append(invoice_data)
        
        return existing_invoices, new_invoices

    def _create_invoice_data(self, items, line_number):
        """Create invoice data dict from CSV line"""
        cuit = items[7]
        partner = self.env['res.partner'].search([('vat', '=', cuit)], limit=1)
        
        return {
            'line_number': line_number,
            'document': f"{items[2].zfill(5)}-{items[3].zfill(8)}",
            'partner_name': partner.name if partner else items[8],
            'date': items[0],
            'amount': float(items[16].replace(',', '.') if items[16] else 0),
            'cuit': cuit
        }

    def _is_duplicate_invoice(self, items, invoice_data):
        """Check if invoice already exists"""
        cuit = items[7]
        partner = self.env['res.partner'].search([('vat', '=', cuit)], limit=1)
        
        if not partner:
            return False
        
        move_type = 'in_refund' if items[1] in ['3', '8', '13'] else 'in_invoice'
        document_number = invoice_data['document']
        
        existing_move = self.env['account.move'].search([
            ('move_type', '=', move_type),
            ('partner_id', '=', partner.id),
            '|', ('ref', '=', document_number), 
            ('name', 'ilike', document_number)
        ], limit=1)
        
        if existing_move:
            return (existing_move.name and document_number in existing_move.name) or \
                   (existing_move.ref and existing_move.ref == document_number)
        
        return False

    def _show_no_invoices_message(self):
        """Show message when no new invoices to import"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('No hay facturas nuevas para importar'),
                'message': _('Todas las facturas en el archivo ya existen en el sistema.'),
                'sticky': False,
                'type': 'warning',
            }
        }

    def _show_account_selection_wizard(self, new_invoices, csv_lines):
        """Show account selection wizard"""
        line_data = []
        for inv in new_invoices:
            line_index = inv['line_number'] - 1
            if line_index < len(csv_lines):
                items = csv_lines[line_index]
                
                # Get amounts from CSV
                amount_vat = float(items[11].replace(',', '.') if items[11] else 0) if len(items) > 11 else 0
                amount_novat = float(items[12].replace(',', '.') if items[12] else 0) if len(items) > 12 else 0
                amount_other = float(items[14].replace(',', '.') if items[14] else 0) if len(items) > 14 else 0
                
                # Get partner for suggestions
                partner = self.env['res.partner'].search([('vat', '=', items[7])], limit=1)
                partner_id = partner.id if partner else False
                
                # Get suggested accounts
                vat_account_id = self._get_suggested_account(partner_id, 'vat') if partner_id else self.account_vat_id.id
                novat_account_id = self._get_suggested_account(partner_id, 'novat') if partner_id else self.account_novat_id.id
                other_account_id = self._get_suggested_account(partner_id, 'other') if partner_id else self.account_other_taxes_id.id
                
                line_data.append({
                    'line_number': inv['line_number'],
                    'invoice_number': inv['document'],
                    'partner_name': inv['partner_name'],
                    'amount_vat': amount_vat,
                    'amount_novat': amount_novat,
                    'amount_other': amount_other,
                    'vat_account_id': vat_account_id if amount_vat > 0 else False,
                    'novat_account_id': novat_account_id if amount_novat > 0 else False,
                    'other_account_id': other_account_id if amount_other > 0 else False,
                })
        
        selection_wizard = self.env['import.invoice.account.selection'].create({
            'iva_file_id': self.id,
            'invoice_data_ids': [(0, 0, data) for data in line_data]
        })
        
        return {
            'name': _('Selección de Cuentas Contables'),
            'type': 'ir.actions.act_window',
            'res_model': 'import.invoice.account.selection',
            'res_id': selection_wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _show_import_wizard(self, existing_invoices, new_invoices):
        """Show import wizard"""
        wizard_vals = {
            'existing_invoices': str(existing_invoices),
            'new_invoices': str(new_invoices),
            'existing_count': len(existing_invoices),
            'new_count': len(new_invoices),
            'iva_file_id': self.id,
            'csv_data': self.iva_file,
            'separator': self.separator,
        }
        
        wizard = self.env['account.iva.import.wizard'].create(wizard_vals)
        return {
            'name': _('Reporte de Importación de IVA'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.iva.import.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _prepare_invoice_lines(self, partner_id, monto_gravado, neto_nogravado, otros_tributos, total, doc_type=None):
        """Prepara las líneas de factura sin procesar IVA"""
        lines = []
        
        # Obtener cuentas y configuración necesaria
        account_vat_id = self._get_suggested_account(partner_id, 'vat')
        account_novat_id = self._get_suggested_account(partner_id, 'novat')
        account_other_taxes_id = self._get_suggested_account(partner_id, 'other')
        
        # Determinar impuesto a aplicar al monto gravado
        original_iva = self.env.context.get('original_iva', 0)
        tax_vat = self._detect_and_get_tax(monto_gravado, original_iva, doc_type)
        
        # Crear las líneas apropiadas
        if doc_type == '11':  # Factura tipo 11
            # Una sola línea para todo el total
            line_vals = {
                'name': 'Factura Tipo 11',
                'price_unit': total,
                'quantity': 1,
                'tax_ids': [(6, 0, [tax_vat.id])] if tax_vat else [(6, 0, [])],
            }
            if account_novat_id:
                line_vals['account_id'] = account_novat_id
            elif self.product_novat_id:
                line_vals['product_id'] = self.product_novat_id.id
            lines.append((0, 0, line_vals))
        else:  # Facturas normales
            # 1. Línea para monto gravado con impuesto
            if monto_gravado > 0:
                line_vals = {
                    'name': 'Monto Gravado',
                    'price_unit': monto_gravado,
                    'quantity': 1,
                    'tax_ids': [(6, 0, [tax_vat.id])] if tax_vat else [(6, 0, [])],
                }
                if account_vat_id:
                    line_vals['account_id'] = account_vat_id
                elif self.product_vat_id:
                    line_vals['product_id'] = self.product_vat_id.id
                lines.append((0, 0, line_vals))
                
            # 2. Línea sin IVA (no gravado)
            if neto_nogravado > 0:
                line_vals = {
                    'name': 'No Gravado',
                    'price_unit': neto_nogravado,
                    'quantity': 1,
                    'tax_ids': [(6, 0, [])],
                }
                if account_novat_id:
                    line_vals['account_id'] = account_novat_id
                elif self.product_novat_id:
                    line_vals['product_id'] = self.product_novat_id.id
                lines.append((0, 0, line_vals))
                
            # 3. Línea para otros tributos
            if otros_tributos > 0:
                line_vals = {
                    'name': 'Otros Tributos',
                    'price_unit': otros_tributos,
                    'quantity': 1,
                    'tax_ids': [(6, 0, [])],
                }
                if account_other_taxes_id:
                    line_vals['account_id'] = account_other_taxes_id
                elif self.product_other_taxes_id:
                    line_vals['product_id'] = self.product_other_taxes_id.id
                lines.append((0, 0, line_vals))
                
        return lines

    def _get_suggested_account(self, partner_id, amount_type='vat'):
        """
        Busca cuentas contables sugeridas para un proveedor basado en facturas anteriores
        
        :param partner_id: ID del partner
        :param amount_type: Tipo de monto ('vat' para gravado, 'novat' para no gravado, 
                            'exempt' para exento, 'other' para otros tributos)
        :return: ID de la cuenta más usada o la configurada en el asistente
        """
        if not self.use_historical_accounts:
            # Si no está habilitada la sugerencia, devolver la cuenta configurada
            if amount_type == 'vat':
                return self.account_vat_id.id if self.account_vat_id else False
            elif amount_type == 'novat':
                return self.account_novat_id.id if self.account_novat_id else False
            elif amount_type == 'exempt':
                return self.account_exempt_id.id if self.account_exempt_id else False
            else:  # other
                return self.account_other_taxes_id.id if self.account_other_taxes_id else False
        
        # Obtener facturas anteriores del proveedor
        prev_invoices = self.env['account.move'].search([
            ('partner_id', '=', partner_id),
            ('move_type', 'in', ['in_invoice', 'in_refund']),
            ('state', '!=', 'cancel'),
        ], order='invoice_date desc', limit=10)
        
        if not prev_invoices:
            # Si no hay facturas anteriores, usar cuentas por defecto
            if amount_type == 'vat':
                return self.account_vat_id.id if self.account_vat_id else False
            elif amount_type == 'novat':
                return self.account_novat_id.id if self.account_novat_id else False
            elif amount_type == 'exempt':
                return self.account_exempt_id.id if self.account_exempt_id else False
            else:  # other
                return self.account_other_taxes_id.id if self.account_other_taxes_id else False
        
        # Contar cuentas por tipo
        account_counts = {}
        for invoice in prev_invoices:
            for line in invoice.invoice_line_ids:
                if not line.account_id:
                    continue
                
                has_tax = bool(line.tax_ids.filtered(lambda t: t.amount > 0))
                
                # Clasificar línea según tipo de monto y presencia de impuestos
                if amount_type == 'vat' and has_tax:
                    account_counts[line.account_id.id] = account_counts.get(line.account_id.id, 0) + 1
                elif amount_type == 'novat' and not has_tax:
                    account_counts[line.account_id.id] = account_counts.get(line.account_id.id, 0) + 1
                elif amount_type == 'other' and line.name and ('tributo' in line.name.lower() or 'impuesto' in line.name.lower()):
                    account_counts[line.account_id.id] = account_counts.get(line.account_id.id, 0) + 1
        
        # Encontrar la cuenta más usada
        if account_counts:
            most_used_account_id = max(account_counts.items(), key=lambda x: x[1])[0]
            return most_used_account_id
        
        # Si no encuentra cuentas específicas, usar las configuradas por defecto
        if amount_type == 'vat':
            return self.account_vat_id.id if self.account_vat_id else False
        elif amount_type == 'novat':
            return self.account_novat_id.id if self.account_novat_id else False
        elif amount_type == 'exempt':
            return self.account_exempt_id.id if self.account_exempt_id else False
        else:  # other
            return self.account_other_taxes_id.id if self.account_other_taxes_id else False

    def continue_import_with_accounts(self):
        """Continuar la importación con las cuentas seleccionadas manualmente"""
        self.ensure_one()
        
        if not self.iva_file:
            raise ValidationError(_('No hay archivo cargado'))
        
        account_selections = self.env.context.get('account_selections', {})
        
        csv_data = base64.b64decode(self.iva_file)
        data_file = StringIO(csv_data.decode("utf-8"))
        data_file.seek(0)
        
        # Usar el separador configurado
        separator = self.separator or ';'
        csv_reader = csv.reader(data_file, delimiter=separator)
        csv_lines = list(csv_reader)
        
        created_invoices = 0
        created_partners = 0
        
        # Procesar solo las líneas específicas
        for i, items in enumerate(csv_lines):
            if i == 0:  # Saltar encabezado
                continue
                
            line_number = i + 1
            if line_number not in account_selections:
                continue
                
            # Obtener selección de cuentas para esta línea
            line_accounts = account_selections[line_number]
            
            # Procesar CUIT y tipo de identificación
            cuit = items[7]
            razonsocial = items[8]
            partner_id = self.env['res.partner'].search([('vat', '=', cuit)], limit=1)
            
            identification_type_id = self.env.ref('l10n_ar.it_cuit').id
            
            # Crear partner si no existe
            if not partner_id:
                vals_partner = {
                    'name': razonsocial,
                    'company_type': 'company',
                    'l10n_latam_identification_type_id': identification_type_id,
                    'l10n_ar_afip_responsibility_type_id': self.env.ref('l10n_ar.res_IVARI').id,
                    'supplier_rank': 1,
                    'account_iva_file_id': self.id,
                }
                partner_id = self.env['res.partner'].create(vals_partner)
                partner_id.write({'vat': cuit})
                created_partners += 1
            
            # Determinar tipo de movimiento
            move_type = 'in_refund' if items[1] in ['3', '8', '13'] else 'in_invoice'
            
            # Preparar número de documento
            document_number = f"{items[2].zfill(5)}-{items[3].zfill(8)}"
            doc_type = items[1]
            doc_type_id = self.env['l10n_latam.document.type'].search([('code', '=', doc_type)], limit=1)
            
            if not doc_type_id:
                # Si no encuentra código exacto, buscar que contiene el código
                doc_type_id = self.env['l10n_latam.document.type'].search([('code', 'ilike', doc_type)], limit=1)
                
                if not doc_type_id:
                    # Si todavía no encuentra, usar factura por defecto
                    doc_type_id = self.env.ref('l10n_ar.dc_a_f')
                
            # Limpiar y convertir montos
            for idx in range(11, 17):
                if len(items) > idx:
                    items[idx] = items[idx].replace(',', '.') if items[idx] else '0'
            
            # CORRECCIÓN: El índice de las columnas está mal en el código actual
            # El orden correcto según el CSV es:
            # 11: Imp. Neto Gravado
            # 12: Imp. Neto No Gravado
            # 13: Imp. Op. Exentas 
            # 14: Otros Tributos <- CLAVE
            # 15: IVA
            # 16: Imp. Total

            monto_gravado = float(items[11]) if len(items) > 11 else 0
            neto_nogravado = float(items[12]) if len(items) > 12 else 0
            imp_op_exentas = float(items[13]) if len(items) > 13 else 0  # No se usa actualmente
            otros_tributos = float(items[14]) if len(items) > 14 else 0  # Columna correcta de Otros Tributos
            iva_original = float(items[15]) if len(items) > 15 else 0  # IVA está en índice 15
            total = float(items[16]) if len(items) > 16 else 0

            # Detectar moneda y tipo de cambio
            currency_id = self.env.company.currency_id.id  # Moneda predeterminada (ARS)
            currency_rate = 1.0

            # Columna 10 contiene el código de moneda
            if len(items) > 10 and items[10] == 'DOL':
                # Buscar la moneda USD en el sistema
                usd_currency = self.env.ref('base.USD')
                if usd_currency:
                    currency_id = usd_currency.id
                    # Obtener tipo de cambio de la columna 9 (Tipo Cambio)
                    try:
                        if len(items) > 9 and items[9]:
                            currency_rate = float(items[9].replace(',', '.'))
                        else:
                            # Si no hay tipo de cambio, usar el de la fecha de la factura
                            invoice_date = fields.Date.from_string(items[0])
                            currency_rate = usd_currency._get_conversion_rate(
                                usd_currency, self.env.company.currency_id, 
                                self.env.company, invoice_date or fields.Date.today()
                            )
                    except (ValueError, TypeError):
                        _logger.warning(f"No se pudo detectar el tipo de cambio para la factura {document_number}, usando 1.0")
                        currency_rate = 1.0
                    
                    _logger.info(f"Factura {document_number} en USD detectada con tipo de cambio {currency_rate}")

            # Verificar si hay concepto que requieran revisión manual
            # Sólo las facturas con Otros Tributos necesitan revisión
            has_other_taxes = otros_tributos > 0
            _logger.info(f"Factura {document_number} - Otros Tributos: {otros_tributos}. Requiere revisión: {has_other_taxes}")

            # Preparar líneas con cuentas personalizadas
            invoice_line_ids = self._prepare_invoice_lines_with_accounts(
                partner_id.id,
                monto_gravado,
                neto_nogravado,
                otros_tributos,
                total, 
                line_accounts,
                iva_original,
                doc_type=items[1]
            )

            # IMPORTANTE: Asegurarse de que solo se marque para revisión cuando hay otros tributos
            vals_move = {
                'move_type': move_type,
                'partner_id': partner_id.id,
                'invoice_date': items[0],
                'l10n_latam_document_number': document_number,
                'account_iva_file_id': self.id,
                'l10n_latam_document_type_id': doc_type_id.id,
                'invoice_line_ids': invoice_line_ids,
                'file_amount': total,
                'requires_review': has_other_taxes,  # SOLO cuando hay otros tributos
                'currency_id': currency_id,
            }

            # Crear factura
            move_id = self.env['account.move'].create(vals_move)

            # Agregar nota sobre el tipo de cambio para facturas en USD
            if currency_id != self.env.company.currency_id.id:
                move_id.message_post(
                    body=_("⚠️ Nota: Esta factura fue importada desde un CSV en USD con tipo de cambio {:.2f}. "
                          "Por favor ajuste manualmente el tipo de cambio en Odoo si es necesario.").format(currency_rate),
                    message_type='notification'
                )
            
            # Verificar que se hayan creado las líneas correctamente
            _logger.info(f"Factura {document_number} creada con {len(move_id.invoice_line_ids)} líneas:")
            for idx, line in enumerate(move_id.invoice_line_ids):
                _logger.info(f"  - Línea {idx+1}: {line.name} - {line.price_unit}")

            # Verificar si se marcó para revisión correctamente
            if otros_tributos > 0 and not move_id.requires_review:
                _logger.warning(f"ADVERTENCIA: La factura {document_number} tiene Otros Tributos pero NO se marcó para revisión")
            elif otros_tributos == 0 and move_id.requires_review:
                _logger.warning(f"ADVERTENCIA: La factura {document_number} se marcó para revisión pero NO tiene Otros Tributos")
            
            # Agregar notas en el chatter según el caso
            if has_other_taxes:
                move_id.message_post(
                    body=_("Esta factura contiene otros tributos que requieren revisión manual."),
                    message_type='notification'
                )
            
            created_invoices += 1
                
        # Marcar como procesado solo si se importaron facturas
        if created_invoices > 0:
            self.write({'state': 'done'})
        
        # Mostrar mensaje de éxito con estadísticas
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Importación completa'),
                'message': _(f'Se importaron {created_invoices} facturas y se crearon {created_partners} proveedores.'),
                'sticky': False,
                'type': 'success',
            }
        }

    def _prepare_invoice_lines_with_accounts(self, partner_id, monto_gravado, neto_nogravado, otros_tributos, total, accounts, iva_original=0, doc_type=None):
        """
        Prepara las líneas de factura usando las cuentas seleccionadas manualmente
        Sin crear líneas para IVA
        """
        lines = []
        
        # Determinar si es comprobante tipo 11 o tipo A
        is_doc_type_11 = (doc_type == '11')
        is_doc_type_A = (doc_type == '1')
        is_doc_type_C = (doc_type == '6')
        
        # Para Facturas A, calcular monto gravado si es necesario
        if is_doc_type_A and monto_gravado == 0 and iva_original > 0:
            # Calcular monto gravado basado en el IVA original del CSV
            tasa_iva = 21  # Por defecto
            if total > 0:
                # Detectar tasa más probable
                prop_105 = abs((iva_original / (total * 0.105)) - 1)
                prop_21 = abs((iva_original / (total * 0.21)) - 1)
                prop_27 = abs((iva_original / (total * 0.27)) - 1)
                
                # Determinar qué proporción está más cerca
                diffs = [prop_105, prop_21, prop_27]
                min_idx = diffs.index(min(diffs))
                
                if min_idx == 0:
                    tasa_iva = 10.5
                elif min_idx == 2:
                    tasa_iva = 27
                    
            # Calcular monto gravado
            monto_gravado = (iva_original * 100) / tasa_iva
            _logger.info(f"Factura A (manual): Calculado monto gravado {monto_gravado:.2f} con tasa {tasa_iva}%")
        
        # Detectar tasa de IVA para aplicar impuesto correcto
        tasa_iva = 21  # Por defecto
        if monto_gravado > 0 and iva_original > 0:
            tasa_calculada = (iva_original / monto_gravado) * 100
            if 9.5 <= tasa_calculada <= 11.5:
                tasa_iva = 10.5
            elif 19.5 <= tasa_calculada <= 22.5:
                tasa_iva = 21
            elif 26 <= tasa_calculada <= 28:
                tasa_iva = 27
        
        # IMPORTANTE: Buscar impuesto según tipo de documento y tasa
        tax_vat = None
        if is_doc_type_11:
            # Para tipo 11, buscar impuesto "IVA No Corresponde" o similar
            no_tax_refs = [
                'l10n_ar.1_vat_no_corresponde',
                'l10n_ar.1_vat_no_gravado',
                'l10n_ar.ri_tax_vat_no_gravado',
                'l10n_ar.ri_tax_vat_exempt',
                'l10n_ar.iva_no_gravado',
                'l10n_ar.iva_exento'
            ]
            
            for tax_ref in no_tax_refs:
                try:
                    tax_vat = self.env.ref(tax_ref, raise_if_not_found=False)
                    if tax_vat:
                        break
                except:
                    continue
                    
            # Buscar impuesto con porcentaje 0% si no se encontró por referencia
            if not tax_vat:
                tax_vat = self.env['account.tax'].search([
                    ('type_tax_use', '=', 'purchase'),
                    ('amount', '=', 0),
                    ('company_id', '=', self.env.company.id)
                ], limit=1)
        elif doc_type == '6':  # Factura C
            # Para facturas C, usar impuesto "IVA No Corresponde"
            no_tax_refs = [
                'l10n_ar.1_vat_no_corresponde',
                'l10n_ar.1_vat_no_gravado',
                'l10n_ar.ri_tax_vat_no_gravado',
                'l10n_ar.ri_tax_vat_exempt',
                'l10n_ar.iva_no_gravado',
                'l10n_ar.iva_exento'
            ]
            
            for tax_ref in no_tax_refs:
                try:
                    tax_vat = self.env.ref(tax_ref, raise_if_not_found=False)
                    if tax_vat:
                        break
                except:
                    continue
                    
            # Buscar impuesto con porcentaje 0% si no se encontró por referencia
            if not tax_vat:
                tax_vat = self.env['account.tax'].search([
                    ('type_tax_use', '=', 'purchase'),
                    ('amount', '=', 0),
                    ('company_id', '=', self.env.company.id)
                ], limit=1)
        else:
            # Para facturas normales, buscar impuesto según tasa
            if tasa_iva == 10.5:
                possible_refs = ['l10n_ar.1_vat_105_compras', 'l10n_ar.ri_tax_vat_105_compras', 'l10n_ar.iva_compras_105']
            elif tasa_iva == 27:
                possible_refs = ['l10n_ar.1_vat_27_compras', 'l10n_ar.ri_tax_vat_27_compras', 'l10n_ar.iva_compras_27']
            else:  # 21% por defecto
                possible_refs = ['l10n_ar.1_vat_21_compras', 'l10n_ar.ri_tax_vat_21_compras', 'l10n_ar.iva_compras_21']
            
            for tax_ref in possible_refs:
                try:
                    tax_vat = self.env.ref(tax_ref, raise_if_not_found=False)
                    if tax_vat:
                        break
                except:
                    continue
                    
            # Buscar por porcentaje si no se encuentra por referencia
            if not tax_vat:
                tax_vat = self.env['account.tax'].search([
                    ('type_tax_use', '=', 'purchase'),
                    ('amount', '=', tasa_iva),
                    ('company_id', '=', self.env.company.id)
                ], limit=1)
        
        # IMPORTANTE: NUNCA crear una línea para el importe del IVA
        # Crear líneas de factura según el tipo de documento
        if is_doc_type_11:
            # Para tipo 11, crear una sola línea con el total
            line_vals = {
                'name': 'Factura Tipo 11 - No Gravado',
                'price_unit': total,  # Usar el total como precio unitario
                'quantity': 1,
                'tax_ids': [(6, 0, [tax_vat.id])] if tax_vat else [(6, 0, [])],
            }
            
            # Usar cuenta seleccionada manualmente
            if accounts.get('novat_account_id'):
                line_vals['account_id'] = accounts['novat_account_id']
            
            lines.append((0, 0, line_vals))
        elif is_doc_type_C:
            # Para facturas tipo C, crear una sola línea con el total e IVA No Corresponde
            line_vals = {
                'name': 'Factura Tipo C - IVA No Corresponde',
                'price_unit': total,  # Usar el total como precio unitario
                'quantity': 1,
                'tax_ids': [(6, 0, [tax_vat.id])] if tax_vat else [(6, 0, [])],
            }
            
            # Usar cuenta seleccionada manualmente (preferir cuenta gravada para facturas C)
            if accounts.get('vat_account_id'):
                line_vals['account_id'] = accounts['vat_account_id']
            elif accounts.get('novat_account_id'):
                line_vals['account_id'] = accounts['novat_account_id']
            
            lines.append((0, 0, line_vals))
        else:
            # 1. Línea con impuesto (gravado)
            if monto_gravado > 0:
                tax_ids = [(6, 0, [tax_vat.id])] if tax_vat else [(6, 0, [])]
                line_vals = {
                    'name': 'Monto Gravado',
                    'price_unit': monto_gravado,  # Base imponible
                    'quantity': 1,
                    'tax_ids': tax_ids,  # El impuesto calculará el IVA automáticamente
                }
                
                # Usar cuenta seleccionada manualmente
                if accounts.get('vat_account_id'):
                    line_vals['account_id'] = accounts['vat_account_id']
                
                lines.append((0, 0, line_vals))
            
            # 2. Línea sin IVA (no gravado)
            if neto_nogravado > 0:
                line_vals = {
                    'name': 'No Gravado',
                    'price_unit': neto_nogravado,
                    'quantity': 1,
                    'tax_ids': [(6, 0, [])],
                }
                
                # Usar cuenta seleccionada manualmente
                if accounts.get('novat_account_id'):
                    line_vals['account_id'] = accounts['novat_account_id']
                    
                lines.append((0, 0, line_vals))
            
            # 3. Línea para otros tributos - Asegurar que se cree correctamente
            if otros_tributos > 0:
                _logger.info(f"IMPORTANTE: Creando línea para Otros Tributos: {otros_tributos} en la factura tipo {doc_type}")
                line_vals = {
                    'name': 'Otros Tributos',
                    'price_unit': otros_tributos,
                    'quantity': 1,
                    'tax_ids': [(6, 0, [])],
                }
                if accounts.get('other_account_id'):
                    line_vals['account_id'] = accounts['other_account_id']
                    _logger.info(f"  - Usando cuenta: {accounts['other_account_id']}")
                elif self.product_other_taxes_id:
                    line_vals['product_id'] = self.product_other_taxes_id.id
                    _logger.info(f"  - Usando producto: {self.product_other_taxes_id.name}")
                else:
                    _logger.warning(f"  - No se encontró cuenta ni producto para Otros Tributos")
                    
                lines.append((0, 0, line_vals))
                _logger.info(f"  - Línea de Otros Tributos agregada correctamente")
            
            # Si no hay líneas específicas, crear una línea con el total
            if not lines:
                line_vals = {
                    'name': 'Total factura',
                    'price_unit': total,
                    'quantity': 1,
                    'tax_ids': [(6, 0, [])],
                }
                
                # Usar la primera cuenta disponible
                if accounts.get('vat_account_id'):
                    line_vals['account_id'] = accounts['vat_account_id']
                elif accounts.get('novat_account_id'):
                    line_vals['account_id'] = accounts['novat_account_id']
                    
                lines.append((0, 0, line_vals))
        
        return lines

    def _detect_and_get_tax(self, monto_gravado, iva_original, doc_type=None):
        """
        Detecta la tasa de IVA y devuelve el impuesto correspondiente
        """
        # Para documentos tipo 11 (exento) y tipo 6 (Factura C)
        if doc_type in ['11', '6']:
            # Buscar impuesto "IVA No Corresponde" o similar
            no_tax_refs = [
                'l10n_ar.1_vat_no_corresponde',
                'l10n_ar.1_vat_no_gravado',
                'l10n_ar.ri_tax_vat_no_gravado',
                'l10n_ar.ri_tax_vat_exempt',
                'l10n_ar.iva_no_gravado',
                'l10n_ar.iva_exento'
            ]
            
            for tax_ref in no_tax_refs:
                try:
                    tax_vat = self.env.ref(tax_ref, raise_if_not_found=False)
                    if tax_vat:
                        return tax_vat
                except:
                    continue
                    
            # Buscar impuesto con porcentaje 0%
            return self.env['account.tax'].search([
                ('type_tax_use', '=', 'purchase'),
                ('amount', '=', 0),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
        
        # Para el resto de documentos, detectar la tasa
        tasa_iva = 21  # Por defecto
        if monto_gravado > 0 and iva_original > 0:
            tasa_calculada = (iva_original / monto_gravado) * 100
            if 9.5 <= tasa_calculada <= 11.5:
                tasa_iva = 10.5
            elif 19.5 <= tasa_calculada <= 22.5:
                tasa_iva = 21
            elif 26 <= tasa_calculada <= 28:
                tasa_iva = 27

        # Buscar impuesto por XML ID
        if tasa_iva == 10.5:
            possible_refs = ['l10n_ar.1_vat_105_compras', 'l10n_ar.ri_tax_vat_105_compras', 'l10n_ar.iva_compras_105']
        elif tasa_iva == 27:
            possible_refs = ['l10n_ar.1_vat_27_compras', 'l10n_ar.ri_tax_vat_27_compras', 'l10n_ar.iva_compras_27']
        else:  # 21% por defecto
            possible_refs = ['l10n_ar.1_vat_21_compras', 'l10n_ar.ri_tax_vat_21_compras', 'l10n_ar.iva_compras_21']
            
        for tax_ref in possible_refs:
            try:
                tax_vat = self.env.ref(tax_ref, raise_if_not_found=False)
                if tax_vat:
                    return tax_vat
            except:
                continue
                
        # Buscar por tasa
        return self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('amount', '=', tasa_iva),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        # Filtrar cualquier línea que sea de IVA antes de crearla
        filtered_vals_list = []
        for vals in vals_list:
            name = vals.get('name', '').lower() if vals.get('name') else ''
            price = vals.get('price_unit', 0)
            
            # Detectar si parece una línea de IVA
            es_linea_iva = False
            
            # Por nombre
            if 'iva' in name or 'i.v.a' in name or 'impuesto' in name:
                es_linea_iva = True
            
            # Por proporción respecto a otra línea (si forma parte de un conjunto)
            if not es_linea_iva and vals.get('move_id') and price > 0:
                # Buscar las otras líneas que se están creando para la misma factura
                otras_lineas = [v for v in vals_list if v.get('move_id') == vals.get('move_id') and v != vals]
                
                # Verificar si hay alguna línea que parece ser "monto gravado"
                for otra_linea in otras_lineas:
                    if otra_linea.get('price_unit', 0) > 0:
                        otra_name = otra_linea.get('name', '').lower()
                        if 'grav' in otra_name:
                            # Calcular la proporción
                            proporcion = (price / otra_linea.get('price_unit')) * 100
                            # Si la proporción es cercana a una tasa de IVA conocida
                            if (9.5 <= proporcion <= 11.5) or (19.5 <= proporcion <= 22.5) or (26 <= proporcion <= 28):
                                es_linea_iva = True
                                _logger.warning(f"Línea '{name}' con valor {price} detectada como IVA por proporción ({proporcion:.1f}%) respecto a otra línea.")
                                break
            
            if es_linea_iva:
                _logger.info(f"Ignorando creación de línea de IVA: {name} - {price}")
                continue
                
            filtered_vals_list.append(vals)
            
        # Crear solo las líneas filtradas
        return super(AccountMoveLine, self).create(filtered_vals_list)
