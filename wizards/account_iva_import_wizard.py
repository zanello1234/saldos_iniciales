# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import base64
import csv
from io import StringIO
import logging

_logger = logging.getLogger(__name__)

class AccountIvaImportWizard(models.TransientModel):
    _name = "account.iva.import.wizard"
    _description = "Asistente de Importación IVA"
    
    existing_invoices = fields.Text('Datos Facturas Existentes', readonly=True)
    new_invoices = fields.Text('Datos Facturas Nuevas', readonly=True)
    existing_count = fields.Integer('Cantidad de Facturas Existentes', readonly=True)
    new_count = fields.Integer('Cantidad de Facturas Nuevas', readonly=True)
    iva_file_id = fields.Many2one('account.iva.file', string="Archivo IVA", readonly=True)
    csv_data = fields.Binary('Datos CSV', readonly=True)
    separator = fields.Char('Separador', readonly=True)
    
    # Campos HTML para mostrar las tablas de forma más amigable
    existing_invoices_html = fields.Html('Vista Facturas Existentes', compute='_compute_html_tables')
    new_invoices_html = fields.Html('Vista Facturas Nuevas', compute='_compute_html_tables')
    
    @api.depends('existing_invoices', 'new_invoices')
    def _compute_html_tables(self):
        for wizard in self:
            # Convertir las cadenas de texto en listas de Python
            existing = eval(wizard.existing_invoices) if wizard.existing_invoices else []
            new = eval(wizard.new_invoices) if wizard.new_invoices else []
            
            # Generar tabla HTML para facturas existentes
            existing_html = """
            <table class="table table-bordered table-sm">
                <thead>
                    <tr>
                        <th>Línea</th>
                        <th>Documento</th>
                        <th>Proveedor</th>
                        <th>Fecha</th>
                        <th>Monto</th>
                        <th>Estado</th>
                    </tr>
                </thead>
                <tbody>
            """
            for inv in existing:
                existing_html += f"""
                <tr>
                    <td>{inv['line_number']}</td>
                    <td>{inv['document']}</td>
                    <td>{inv['partner_name']}</td>
                    <td>{inv['date']}</td>
                    <td>{inv['amount']}</td>
                    <td>{"Borrador" if inv.get('state') == 'draft' else "Publicada"}</td>
                </tr>
                """
            existing_html += "</tbody></table>"
            
            # Generar tabla HTML para facturas nuevas
            new_html = """
            <table class="table table-bordered table-sm">
                <thead>
                    <tr>
                        <th>Línea</th>
                        <th>Documento</th>
                        <th>Proveedor</th>
                        <th>Fecha</th>
                        <th>Monto</th>
                        <th>CUIT</th>
                    </tr>
                </thead>
                <tbody>
            """
            for inv in new:
                new_html += f"""
                <tr>
                    <td>{inv['line_number']}</td>
                    <td>{inv['document']}</td>
                    <td>{inv['partner_name']}</td>
                    <td>{inv['date']}</td>
                    <td>{inv['amount']}</td>
                    <td>{inv.get('cuit', '')}</td>
                </tr>
                """
            new_html += "</tbody></table>"
            
            wizard.existing_invoices_html = existing_html
            wizard.new_invoices_html = new_html
    
    def confirm_import(self):
        """Proceder con la importación de las facturas nuevas"""
        self.ensure_one()
        
        if not self.new_count:
            return {'type': 'ir.actions.act_window_close'}
            
        # Obtener el objeto de archivo IVA
        iva_file = self.iva_file_id
        
        try:
            # Convertir las listas de Python
            new_invoices = eval(self.new_invoices) if self.new_invoices else []
            
            # Decodificar archivo CSV
            csv_data = base64.b64decode(self.csv_data)
            data_file = StringIO(csv_data.decode("utf-8"))
            data_file.seek(0)
            
            # Usar el separador configurado
            csv_reader = csv.reader(data_file, delimiter=self.separator)
            csv_lines = list(csv_reader)
            
            # Extraer los números de línea de las facturas nuevas
            new_line_numbers = [inv['line_number'] for inv in new_invoices]
            
            # Contadores para estadísticas
            created_invoices = 0
            created_partners = 0
            
            # Procesar solo las líneas que corresponden a facturas nuevas
            for i, items in enumerate(csv_lines):
                line_number = i + 1
                
                if i == 0 or line_number not in new_line_numbers:  # Saltar encabezado y facturas existentes
                    continue
                    
                # Determinar tipo de movimiento
                doc_type = items[1]
                move_type = 'in_refund' if doc_type in ['3', '8', '13'] else 'in_invoice'

                # Preparar número de documento
                document_number = f"{items[2].zfill(5)}-{items[3].zfill(8)}"
                doc_type_id = self.env['l10n_latam.document.type'].search([('code', '=', doc_type)], limit=1)

                if not doc_type_id:
                    # Si no encuentra código exacto, buscar que contiene el código
                    doc_type_id = self.env['l10n_latam.document.type'].search([('code', 'ilike', doc_type)], limit=1)
                    
                    if not doc_type_id:
                        # Si todavía no encuentra, usar factura por defecto
                        doc_type_id = self.env.ref('l10n_ar.dc_a_f')

                # Verificar si hay otros tributos (columna 14, no 15)
                requires_review = False
                if len(items) > 14 and items[14]:  # CAMBIAR 15 por 14
                    try:
                        otros_tributos_amount = float(items[14].replace(',', '.') if items[14] else 0)  # CAMBIAR 15 por 14
                        if otros_tributos_amount > 0:
                            requires_review = True
                            _logger.info(f"Factura {document_number}: Contiene Otros Tributos por {otros_tributos_amount}, marcada para revisión")
                    except (ValueError, TypeError):
                        # Si no se puede convertir, asumir que hay datos para revisión
                        if items[14].strip():  # CAMBIAR 15 por 14
                            requires_review = True
                            _logger.info(f"Factura {document_number}: Contiene datos no numéricos en Otros Tributos, marcada para revisión")
                
                # Debug para verificar los valores de las columnas
                _logger.info(f"""
COLUMNAS CSV DE LA FACTURA {document_number}:
- [11] Imp. Neto Gravado: {items[11] if len(items) > 11 else 'N/A'}
- [12] Imp. Neto No Gravado: {items[12] if len(items) > 12 else 'N/A'}
- [13] Imp. Op. Exentas: {items[13] if len(items) > 13 else 'N/A'}
- [14] Otros Tributos: {items[14] if len(items) > 14 else 'N/A'}
- [15] IVA: {items[15] if len(items) > 15 else 'N/A'}
- [16] Imp. Total: {items[16] if len(items) > 16 else 'N/A'}
""")

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

                # Procesar CUIT y tipo de identificación
                cuit = items[7]
                razonsocial = items[8]
                partner_id = self.env['res.partner'].search([('vat', '=', cuit)], limit=1)
                
                identification_type_id = self.env.ref(
                    'l10n_ar.it_cuit' if items[6] == 'CUIT' else 'l10n_ar.it_Sigd'
                ).id
                
                # Crear partner si no existe
                if not partner_id:
                    vals_partner = {
                        'name': razonsocial,
                        'company_type': 'company',
                        'l10n_latam_identification_type_id': identification_type_id,
                        'l10n_ar_afip_responsibility_type_id': self.env.ref('l10n_ar.res_IVARI').id,
                        'supplier_rank': 1,
                        'account_iva_file_id': iva_file.id,
                    }
                    partner_id = self.env['res.partner'].create(vals_partner)
                    partner_id.write({'vat': cuit})
                    created_partners += 1
                
                # Limpiar y convertir montos
                for idx in range(11, 17):
                    if len(items) > idx:  # Verificar que hay suficientes columnas
                        items[idx] = items[idx].replace(',', '.') if items[idx] else '0'

                # Leer el IVA de la columna 15, no de la 12
                iva_original = float(items[15].replace(',', '.')) if len(items) > 15 and items[15] else 0  # CAMBIAR 12 por 15

                # CORRECCIONES en la preparación de líneas:
                invoice_line_ids = iva_file.with_context(original_iva=iva_original)._prepare_invoice_lines(
                    partner_id.id,
                    float(items[11].replace(',', '.')) if len(items) > 11 and items[11] else 0,  # Monto gravado
                    float(items[12].replace(',', '.')) if len(items) > 12 and items[12] else 0,  # No gravado (CAMBIAR 13 por 12)
                    float(items[14].replace(',', '.')) if len(items) > 14 and items[14] else 0,  # Otros tributos (CAMBIAR 15 por 14)
                    float(items[16].replace(',', '.')) if len(items) > 16 and items[16] else 0,  # Total
                    doc_type=doc_type
                )

                # Preparar valores del movimiento - SOLO establecer la moneda, no el tipo de cambio
                vals_move = {
                    'move_type': move_type,
                    'partner_id': partner_id.id,
                    'invoice_date': items[0],
                    'l10n_latam_document_number': document_number,
                    'account_iva_file_id': iva_file.id,
                    'l10n_latam_document_type_id': doc_type_id.id,
                    'invoice_line_ids': invoice_line_ids,
                    'file_amount': float(items[16]) if len(items) > 16 else 0,
                    'requires_review': requires_review,
                    'currency_id': currency_id,  # Moneda USD si corresponde
                }

                # Crear factura
                move_id = self.env['account.move'].create(vals_move)
                created_invoices += 1

                # Agregar nota sobre el tipo de cambio para facturas en USD
                if currency_id != self.env.company.currency_id.id:
                    move_id.message_post(
                        body=_("⚠️ Nota: Esta factura fue importada desde un CSV en USD con tipo de cambio {:.2f}. "
                               "Por favor verifique que el tipo de cambio en Odoo sea correcto.").format(currency_rate),
                        message_type='notification'
                    )

                # Verificación de IVA
                tax_lines = move_id.line_ids.filtered(lambda l: l.tax_line_id)
                iva_en_factura = sum(line.price_total for line in tax_lines)
                _logger.info(f"""
                VERIFICACIÓN FACTURA {document_number}:
                - IVA en archivo CSV: {iva_original}
                - IVA calculado en factura: {iva_en_factura}
                - Diferencia: {abs(iva_original - iva_en_factura)}
                """)

                if abs(iva_original - iva_en_factura) > 0.01:
                    move_id.message_post(
                        body=_(f"⚠️ ADVERTENCIA: El IVA importado ({iva_original}) no coincide con el calculado ({iva_en_factura})."),
                        message_type='notification'
                    )
                
                # Si requiere revisión, agregar una nota
                if requires_review:
                    move_id.message_post(
                        body=_("Esta factura contiene otros tributos que requieren revisión manual."),
                        message_type='notification'
                    )
                    
            # Marcar como procesado solo si se importaron facturas
            if created_invoices > 0:
                iva_file.write({'state': 'done'})
            
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
            
        except Exception as e:
            # Enhanced error reporting
            import traceback
            error_trace = traceback.format_exc()
            _logger.error(f"Error importando facturas: {str(e)}\n{error_trace}")
            
            # More user-friendly error message with detailed info
            if "External ID not found" in str(e):
                raise ValidationError(_(
                    "Error con referencias de impuestos: {}\n\n"
                    "Por favor verifique que los impuestos estén correctamente configurados "
                    "en su sistema antes de continuar.").format(str(e)))
            else:
                raise ValidationError(_(f"Error importando facturas: {str(e)}"))
        
        return {'type': 'ir.actions.act_window_close'}
    
    def cancel_import(self):
        """Cancelar la importación"""
        return {'type': 'ir.actions.act_window_close'}
    
    def action_view_duplicate(self):
        """
        Abrir factura duplicada para verificación
        """
        self.ensure_one()
        if not self.existing_invoices:
            return
            
        view_id = self.env.ref('account.view_move_form').id
        
        # Obtener el primer duplicado de la lista para verificación
        duplicates = eval(self.existing_invoices) if self.existing_invoices else []
        if not duplicates:
            raise ValidationError(_('No hay facturas duplicadas para verificar'))

        # Tomar el ID de la primera factura duplicada
        move_id = duplicates[0].get('move_id', False)
        if not move_id:
            raise ValidationError(_('No se pudo determinar la factura a verificar'))
        
        return {
            'name': _('Verificar Factura Duplicada'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move',
            'view_id': view_id,
            'res_id': move_id,
            'type': 'ir.actions.act_window',
        }

    def _get_tax_by_rate(self, monto_gravado, iva_original):
        """Detecta y devuelve el impuesto apropiado según la tasa de IVA"""
        # Detectar tasa de IVA
        tasa_iva = 21  # Por defecto
        if monto_gravado > 0 and iva_original > 0:
            tasa_calculada = (iva_original / monto_gravado) * 100
            if 9.5 <= tasa_calculada <= 11.5:
                tasa_iva = 10.5
            elif 19.5 <= tasa_calculada <= 22.5:
                tasa_iva = 21
            elif 26 <= tasa_calculada <= 28:
                tasa_iva = 27
                
        # Buscar impuesto por referencia XML ID
        tax_vat = None
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
                
        # Si no se encuentra por referencia, buscar por tasa
        if not tax_vat:
            tax_vat = self.env['account.tax'].search([
                ('type_tax_use', '=', 'purchase'),
                ('amount', '=', tasa_iva),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
                
        return tax_vat