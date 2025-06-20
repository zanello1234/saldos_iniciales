# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import base64
import csv
from io import StringIO
from datetime import datetime


class AccountMove(models.Model):
    _inherit = 'account.move'

    account_iva_file_id = fields.Many2one('account.iva.file', string='Archivo de Saldos')
    file_amount = fields.Float('Monto del Archivo')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    account_iva_file_id = fields.Many2one('account.iva.file', string='Archivo de Saldos')


class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    account_iva_file_id = fields.Many2one('account.iva.file', string='Archivo de Saldos')


class AccountIvaFile(models.Model):
    _name = "account.iva.file"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Importación de Saldos"

    name = fields.Char('Nombre', required=True, tracking=True)
    operation_type = fields.Selection([
        ('purchase', 'Compras'),
        ('sale', 'Ventas')
    ], string='Tipo de Operación', required=True, default='purchase', tracking=True)
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    journal_id = fields.Many2one('account.journal', string='Diario', required=True)
    date = fields.Date('Fecha', default=fields.Date.today(), readonly=True)
    iva_file = fields.Binary('Archivo CSV')
    filename = fields.Char('Nombre del Archivo')
    separator = fields.Char('Separador CSV', default=';')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('done', 'Procesado'),
    ], default='draft', tracking=True)
    
    # Campos para tipo de cambio
    usd_exchange_rate = fields.Float('Tipo de Cambio USD', digits=(12, 4), 
                                   help="Tipo de cambio del dólar para esta fecha (1 USD = X ARS)")
    update_exchange_rates = fields.Boolean('Actualizar Tipos de Cambio', default=True,
                                         help="Crear/actualizar tipos de cambio automáticamente cuando se encuentren facturas en USD")
    
    partner_ids = fields.One2many('res.partner', 'account_iva_file_id', string='Contactos Creados')
    move_ids = fields.One2many('account.move', 'account_iva_file_id', string='Facturas Creadas')
    currency_rate_ids = fields.One2many('res.currency.rate', 'account_iva_file_id', string='Tipos de Cambio Actualizados')

    @api.onchange('operation_type')
    def _onchange_operation_type(self):
        self.journal_id = False
        return {
            'domain': {
                'journal_id': [('type', '=', self.operation_type)]
            }
        }

    def btn_analyze_file(self):
        """Botón para analizar el archivo sin procesarlo"""
        if not self.iva_file:
            raise ValidationError('Debe cargar un archivo CSV')
        
        try:
            csv_data = base64.b64decode(self.iva_file)
            data_file = StringIO(csv_data.decode("utf-8"))
            csv_reader = csv.reader(data_file, delimiter=self.separator)
            
            analysis = []
            
            for i, row in enumerate(csv_reader):
                if i == 0:
                    analysis.append(f"HEADER: {row}")
                    continue
                if i > 10:  # Solo analizar las primeras 10 filas
                    break
                    
                currency_code = row[10].strip() if len(row) > 10 and row[10] else 'VACIO'
                amount = row[16] if len(row) > 16 else 'N/A'
                
                analysis.append(f"Fila {i}: Moneda='{currency_code}', Monto='{amount}'")
            
            message = "\n".join(analysis)
            self.message_post(body=f"<pre>{message}</pre>")
            
        except Exception as e:
            raise ValidationError(f'Error analizando archivo: {str(e)}')

    def btn_process_file(self):
        if not self.iva_file:
            raise ValidationError('Debe cargar un archivo CSV')
        
        try:
            csv_data = base64.b64decode(self.iva_file)
            data_file = StringIO(csv_data.decode("utf-8"))
            csv_reader = csv.reader(data_file, delimiter=self.separator)
            
            # Variables para controlar tipos de cambio
            usd_invoices_found = False
            exchange_rates_by_date = {}  # Diccionario para almacenar tipos de cambio por fecha
            rows_to_process = []  # Almacenar las filas para procesarlas después
            
            # PASO 1: PRIMERA PASADA - Extraer tipos de cambio
            print("\n=== PASO 1: EXTRAYENDO TIPOS DE CAMBIO ===")
            
            for i, row in enumerate(csv_reader):
                if i == 0:  # Es el header
                    print(f"HEADER: {row}")
                    continue
                
                if len(row) < 17:  # Filas incompletas
                    continue
                
                # Guardar la fila para procesarla después
                rows_to_process.append(row)
                
                # Verificar moneda en columna 10
                currency_code = row[10].strip() if len(row) > 10 and row[10] else ''
                
                # Si es una factura en USD, extraer el tipo de cambio
                if currency_code == 'DOL':
                    usd_invoices_found = True
                    
                    # Extraer fecha de la factura (columna 0)
                    invoice_date_str = row[0]
                    
                    # Extraer tipo de cambio (columna 9)
                    exchange_rate_str = row[9] if len(row) > 9 and row[9] else '0'
                    
                    try:
                        # Convertir fecha
                        invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
                        
                        # Convertir tipo de cambio
                        exchange_rate = float(exchange_rate_str.replace(',', '.'))
                        
                        if exchange_rate > 0:
                            # Guardar el tipo de cambio por fecha
                            exchange_rates_by_date[invoice_date] = exchange_rate
                            print(f"Tipo de cambio extraído - Fecha: {invoice_date}, TC: {exchange_rate}")
                        else:
                            print(f"Tipo de cambio inválido en fila {i}: {exchange_rate_str}")
                            
                    except (ValueError, TypeError) as e:
                        print(f"Error procesando fecha/TC en fila {i}: {e}")
            
            # PASO 2: ACTUALIZAR TIPOS DE CAMBIO PRIMERO
            print(f"\n=== PASO 2: ACTUALIZANDO TIPOS DE CAMBIO ===")
            
            if usd_invoices_found and self.update_exchange_rates:
                if exchange_rates_by_date:
                    print(f"Tipos de cambio a procesar: {len(exchange_rates_by_date)}")
                    for fecha, tc in exchange_rates_by_date.items():
                        print(f"  - {fecha}: {tc}")
                    
                    # Actualizar tipos de cambio ANTES de crear facturas
                    self._update_currency_rates_from_csv(exchange_rates_by_date)
                    print("Tipos de cambio actualizados exitosamente")
                elif self.usd_exchange_rate:
                    # Usar tipo de cambio manual como fallback
                    print(f"Usando tipo de cambio manual: {self.usd_exchange_rate}")
                    self._update_currency_rates_usd()
            
            # PASO 3: PROCESAR FACTURAS
            print(f"\n=== PASO 3: PROCESANDO FACTURAS ===")
            print(f"Filas a procesar: {len(rows_to_process)}")
            
            facturas_creadas = 0
            partners_creados_ids = []  # Lista para rastrear IDs de partners creados
            
            for i, row in enumerate(rows_to_process, start=1):
                # Verificar moneda
                currency_code = row[10].strip() if len(row) > 10 and row[10] else ''
                
                print(f"Procesando fila {i}: Moneda={currency_code}")
                
                # Procesar partner
                cuit = row[7]
                name = row[8]
                partner, is_new = self._get_or_create_partner(cuit, name)
                
                # Si el partner es nuevo y no está en nuestra lista, agregarlo
                if is_new and partner.id not in partners_creados_ids:
                    partners_creados_ids.append(partner.id)
                
                # Procesar factura (columna 16 = Imp.Total)
                amount = float(row[16].replace(',', '.')) if row[16] else 0.0
                if amount != 0:
                    factura = self._create_invoice(partner, row, amount)
                    if factura:
                        facturas_creadas += 1
            
            # Contar partners únicos creados
            partners_creados = len(partners_creados_ids)
            
            # PASO 4: RESUMEN FINAL
            print(f"\n=== RESUMEN FINAL ===")
            print(f"Tipos de cambio procesados: {len(exchange_rates_by_date)}")
            print(f"Partners creados: {partners_creados}")
            print(f"Facturas creadas: {facturas_creadas}")
            
            # Mensaje en el chatter
            summary_lines = [
                f"Proceso completado exitosamente:",
                f"• {len(exchange_rates_by_date)} tipos de cambio actualizados",
                f"• {partners_creados} contactos creados",
                f"• {facturas_creadas} facturas creadas"
            ]
            
            if exchange_rates_by_date:
                summary_lines.append("\nTipos de cambio por fecha:")
                for fecha, tc in sorted(exchange_rates_by_date.items()):
                    summary_lines.append(f"• {fecha}: 1 USD = {tc:.4f} ARS")
            
            self.message_post(body="<pre>" + "\n".join(summary_lines) + "</pre>")
            
            self.state = 'done'
            
        except Exception as e:
            print(f"ERROR: {str(e)}")
            raise ValidationError(f'Error procesando archivo: {str(e)}')

    def _update_currency_rates_from_csv(self, exchange_rates_by_date):
        """Actualiza los tipos de cambio USD basado en los datos extraidos del CSV"""
        
        print("Iniciando actualización de tipos de cambio...")
        
        # Buscar moneda USD
        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        if not usd_currency:
            raise ValidationError('No se encontró la moneda USD en el sistema')
        
        rates_created = 0
        rates_updated = 0
        
        # Procesar cada fecha con su tipo de cambio
        for invoice_date, exchange_rate in sorted(exchange_rates_by_date.items()):
            if not exchange_rate or exchange_rate <= 0:
                continue
            
            print(f"Procesando tipo de cambio para {invoice_date}: {exchange_rate}")
            
            # Verificar si ya existe un tipo de cambio para esta fecha
            existing_rate = self.env['res.currency.rate'].search([
                ('currency_id', '=', usd_currency.id),
                ('name', '=', invoice_date),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            
            # Odoo usa el inverso del tipo de cambio
            odoo_rate = 1 / exchange_rate
            
            rate_vals = {
                'currency_id': usd_currency.id,
                'name': invoice_date,
                'rate': odoo_rate,
                'company_id': self.env.company.id,
                'account_iva_file_id': self.id,
            }
            
            if existing_rate:
                if abs(existing_rate.rate - odoo_rate) > 0.000001:
                    existing_rate.write({
                        'rate': odoo_rate,
                        'account_iva_file_id': self.id
                    })
                    rates_updated += 1
                    print(f"✓ Tipo de cambio actualizado: {exchange_rate:.4f} para {invoice_date}")
                else:
                    print(f"→ Tipo de cambio ya existe y es igual para {invoice_date}")
            else:
                new_rate = self.env['res.currency.rate'].create(rate_vals)
                rates_created += 1
                print(f"✓ Tipo de cambio creado: {exchange_rate:.4f} para {invoice_date} (ID: {new_rate.id})")
        
        print(f"Tipos de cambio procesados: {rates_created} creados, {rates_updated} actualizados")
        
        # Forzar commit para que los tipos de cambio estén disponibles para las facturas
        self.env.cr.commit()
        
        return rates_created, rates_updated

    def _update_currency_rates_usd(self):
        """Actualiza el tipo de cambio USD para la fecha del proceso (método manual)"""
        
        if not self.usd_exchange_rate or self.usd_exchange_rate <= 0:
            return
            
        # Buscar moneda USD
        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        if not usd_currency:
            raise ValidationError('No se encontró la moneda USD en el sistema')
        
        # Verificar si ya existe un tipo de cambio para esta fecha
        existing_rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', usd_currency.id),
            ('name', '=', self.date),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        
        # Odoo usa el inverso del tipo de cambio
        odoo_rate = 1 / self.usd_exchange_rate
        
        rate_vals = {
            'currency_id': usd_currency.id,
            'name': self.date,
            'rate': odoo_rate,
            'company_id': self.env.company.id,
            'account_iva_file_id': self.id,
        }
        
        if existing_rate:
            existing_rate.write({
                'rate': odoo_rate,
                'account_iva_file_id': self.id
            })
            self.message_post(
                body=f"Tipo de cambio USD actualizado (manual): 1 USD = {self.usd_exchange_rate:.4f} ARS para la fecha {self.date}"
            )
        else:
            self.env['res.currency.rate'].create(rate_vals)
            self.message_post(
                body=f"Tipo de cambio USD creado (manual): 1 USD = {self.usd_exchange_rate:.4f} ARS para la fecha {self.date}"
            )

    def _get_or_create_partner(self, cuit, name):
        """
        Busca o crea un partner y retorna una tupla (partner, is_new)
        """
        partner = self.env['res.partner'].search([('vat', '=', cuit)], limit=1)
        
        if not partner:
            vals = {
                'name': name,
                'vat': cuit,
                'company_type': 'company',
                'account_iva_file_id': self.id,
            }
            
            if self.operation_type == 'purchase':
                vals['supplier_rank'] = 1
            else:
                vals['customer_rank'] = 1
                
            partner = self.env['res.partner'].create(vals)
            print(f"✓ Partner creado: {name} (CUIT: {cuit})")
            return partner, True  # True = es nuevo
        else:
            print(f"→ Partner existente: {name} (CUIT: {cuit})")
            return partner, False  # False = ya existía

    def _get_currency_from_csv(self, currency_code):
        """Obtiene la moneda de Odoo basada en el código del CSV"""
        
        # Limpiar el código de moneda
        currency_code = currency_code.strip() if currency_code else ''
        
        print(f"_get_currency_from_csv recibió: '{currency_code}' (tipo: {type(currency_code)})")
        
        if currency_code == 'DOL':
            currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
            if currency:
                print(f"  -> Retornando USD (ID: {currency.id})")
                return currency.id
            else:
                print("  -> ERROR: No se encontró moneda USD")
        elif currency_code == 'PES':
            currency = self.env['res.currency'].search([('name', '=', 'ARS')], limit=1)
            if currency:
                print(f"  -> Retornando ARS (ID: {currency.id})")
                return currency.id
            else:
                print("  -> ERROR: No se encontró moneda ARS")
        else:
            print(f"  -> Código de moneda no reconocido: '{currency_code}'")
        
        # Si no encuentra la moneda específica, usar la moneda de la compañía
        company_currency = self.env.company.currency_id
        print(f"  -> Usando moneda de la compañía: {company_currency.name} (ID: {company_currency.id})")
        return company_currency.id

    def _create_invoice(self, partner, row, amount):
        # Determinar el tipo de movimiento correcto según el tipo de operación
        doc_type_code = row[1].strip()
        
        if self.operation_type == 'purchase':
            if doc_type_code in ['3', '8', '13']:
                move_type = 'in_refund'
            else:
                move_type = 'in_invoice'
        else:
            if doc_type_code in ['3', '8', '13']:
                move_type = 'out_refund'
            else:
                move_type = 'out_invoice'
        
        # Buscar el tipo de documento correcto
        doc_type_id = False
        if doc_type_code:
            doc_type = self.env['l10n_latam.document.type'].search([
                ('code', '=', doc_type_code)
            ], limit=1)
            if doc_type:
                doc_type_id = doc_type.id
        
        # Obtener la moneda basada en la columna 10 del CSV (Moneda)
        currency_code = row[10] if len(row) > 10 else ''
        currency_id = self._get_currency_from_csv(currency_code)
        
        # Crear líneas de factura
        line_vals = {
            'product_id': self.product_id.id,
            'name': self.product_id.name or 'Saldo',
            'quantity': 1,
            'price_unit': amount,
            'product_uom_id': self.product_id.uom_id.id,
            'tax_ids': [(6, 0, [])],
        }
        
        # Número de documento
        document_number = '%s-%s' % (row[2].zfill(5), row[3].zfill(8))
        
        # Verificar si ya existe la factura
        existing_move = self.env['account.move'].search([
            ('move_type', '=', move_type),
            ('partner_id', '=', partner.id),
            ('l10n_latam_document_number', '=', document_number)
        ], limit=1)
        
        if existing_move:
            print(f"Factura ya existe: {document_number}")
            return existing_move
        
        # Crear factura con la moneda correcta
        invoice_vals = {
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': row[0],
            'journal_id': self.journal_id.id,
            'account_iva_file_id': self.id,
            'file_amount': amount,
            'currency_id': currency_id,
            'l10n_latam_document_number': document_number,
            'l10n_latam_document_type_id': doc_type_id,
            'invoice_line_ids': [(0, 0, line_vals)],
        }
        
        factura = self.env['account.move'].create(invoice_vals)
        print(f"✓ Factura creada: {document_number} - {currency_code} {amount}")
        
        return factura
