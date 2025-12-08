# -*- coding: utf-8 -*-

"""
Módulo para importación de saldos iniciales desde archivos CSV de AFIP.

Estructura del CSV de Facturas de Venta AFIP (separado por ;):
FORMATO NUEVO (28 columnas):
Columna 1 (índice 0): Fecha de Emisión
Columna 2 (índice 1): Tipo de Comprobante
Columna 3 (índice 2): Punto de Venta
Columna 4 (índice 3): Número Desde
Columna 5 (índice 4): Número Hasta
Columna 6 (índice 5): Cód. Autorización
Columna 7 (índice 6): Tipo Doc. Receptor
Columna 8 (índice 7): Nro. Doc. Receptor (CUIT)
Columna 9 (índice 8): Denominación Receptor
Columna 10 (índice 9): Tipo Cambio
Columna 11 (índice 10): Moneda
Columna 12 (índice 11): Imp. Neto Gravado IVA 0%
...
Columna 23 (índice 22): Imp. Neto Gravado Total *** ESTE ES EL MONTO CORRECTO ***
Columna 24 (índice 23): Imp. Neto No Gravado
Columna 25 (índice 24): Imp. Op. Exentas
Columna 26 (índice 25): Otros Tributos
Columna 27 (índice 26): Total IVA
Columna 28 (índice 27): Imp. Total (Para facturas tipo 11 con IVA incluido)
"""

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import base64
import csv
import re
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
    company_id = fields.Many2one('res.company', string='Compañía', 
                                default=lambda self: self.env.company, 
                                required=True, tracking=True,
                                help="Compañía a la que pertenece este archivo de importación")
    operation_type = fields.Selection([
        ('purchase', 'Compras'),
        ('sale', 'Ventas')
    ], string='Tipo de Operación', required=True, default='purchase', tracking=True)
    import_type = fields.Selection([
        ('initial_balances', 'Saldos iniciales'),
        ('new_documents', 'Comprobantes nuevos')
    ], string='Tipo de Importación', required=True, default='initial_balances', tracking=True)
    product_id = fields.Many2one('product.product', string='Producto', required=False)
    journal_id = fields.Many2one('account.journal', string='Diario', required=True)
    date = fields.Date('Fecha', default=fields.Date.today(), readonly=True)
    iva_file = fields.Binary('Archivo CSV')
    filename = fields.Char('Nombre del Archivo')
    separator = fields.Char('Separador CSV', default=';')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('analyzed', 'Analizado'),
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
    
    # Campos para almacenar resultados del análisis
    analysis_total_rows = fields.Integer('Total Filas Leídas', readonly=True)
    analysis_valid_rows = fields.Integer('Filas Válidas', readonly=True)
    analysis_omitted_rows = fields.Integer('Filas Omitidas', readonly=True)
    analysis_success_percentage = fields.Float('Porcentaje de Éxito', readonly=True, digits=(5,2))
    analysis_total_net = fields.Float('Total Neto', readonly=True, digits=(12,2))
    analysis_total_tax = fields.Float('Total IVA', readonly=True, digits=(12,2))
    analysis_total_amount = fields.Float('Total General', readonly=True, digits=(12,2))
    analysis_existing_documents = fields.Integer('Comprobantes Existentes', readonly=True)
    analysis_new_documents = fields.Integer('Comprobantes Nuevos', readonly=True)
    analysis_duplicate_percentage = fields.Float('Porcentaje Duplicados', readonly=True, digits=(5,2))
    analysis_report = fields.Html('Reporte de Análisis', readonly=True)
    
    # Campo para mensajes de debugging
    debug_messages = fields.Html('Mensajes de Debug', readonly=True, default="<pre>No hay mensajes de debug aún...</pre>")

    def _add_debug_message(self, message):
        """Agregar mensaje de debug a la solapa - Solo errores y advertencias"""
        try:
            # Solo mostrar mensajes que contengan errores (❌) o advertencias (⚠️)
            if '❌' in message or '⚠️' in message:
                current_messages = self.debug_messages or "<pre>"
                # Si es el primer mensaje real, limpiar el mensaje por defecto
                if "No hay mensajes de debug aún..." in current_messages:
                    current_messages = "<pre>"
                
                # Agregar timestamp
                from datetime import datetime
                timestamp = datetime.now().strftime("%H:%M:%S")
                new_message = f"[{timestamp}] {message}\n"
                
                # Actualizar mensajes
                updated_messages = current_messages + new_message + "</pre>"
                self.debug_messages = updated_messages
        except Exception as e:
            pass  # No interrumpir el procesamiento por errores de logging

    def _clear_debug_messages(self):
        """Limpiar mensajes de debug al iniciar un nuevo procesamiento"""
        self.debug_messages = "<pre>🚀 PROCESAMIENTO INICIADO - Solo se mostrarán errores y advertencias\n</pre>"

    @api.onchange('operation_type')
    def _onchange_operation_type(self):
        self.journal_id = False
        return {
            'domain': {
                'journal_id': [('type', '=', self.operation_type)]
            }
        }

    @api.onchange('import_type')
    def _onchange_import_type(self):
        """Limpiar producto cuando se selecciona saldos iniciales"""
        if self.import_type == 'initial_balances':
            self.product_id = False

    @api.constrains('product_id', 'import_type')
    def _check_product_required(self):
        """Validar que el producto sea requerido solo para facturas nuevas"""
        for record in self:
            if record.import_type == 'new_documents' and not record.product_id:
                raise ValidationError('El producto es obligatorio para importar facturas nuevas.')

    def _get_document_name_by_type(self, doc_type_code, point_of_sale, doc_number):
        """Generar nombre de documento según el tipo AFIP"""
        try:
            # Mapeo de códigos AFIP a nombres de documento
            document_types = {
                # Facturas
                '1': 'FA-A',    # Factura A
                '6': 'FA-B',    # Factura B
                '11': 'FA-C',   # Factura C
                # Notas de Débito
                '2': 'ND-A',    # Nota de Débito A
                '7': 'ND-B',    # Nota de Débito B
                '12': 'ND-C',   # Nota de Débito C
                # Notas de Crédito
                '3': 'NC-A',    # Nota de Crédito A
                '8': 'NC-B',    # Nota de Crédito B
                '13': 'NC-C',   # Nota de Crédito C
                # MiPyme
                '201': 'FA-A',  # Factura MiPyme A
                '202': 'FA-B',  # Factura MiPyme B
                '203': 'NC-A',  # Nota de Crédito MiPyme
                # Facturas M
                '51': 'FA-M',   # Factura M
                '52': 'ND-M',   # Nota de Débito M
                '53': 'NC-M',   # Nota de Crédito M
            }
            
            # Obtener prefijo según tipo de documento
            prefix = document_types.get(doc_type_code, 'FA-A')  # Default a Factura A
            
            # Formatear número: PREFIX PPPP-NNNNNNNN
            formatted_number = f"{prefix} {point_of_sale}-{doc_number}"
            
            return formatted_number
            
        except Exception as e:
            # Si hay error, usar formato básico
            return f"FA-A {point_of_sale}-{doc_number}"

    def btn_analyze_file(self):
        """Botón para analizar el archivo sin procesarlo"""
        if not self.iva_file:
            raise ValidationError('Debe cargar un archivo CSV')
        
        try:
            csv_data = base64.b64decode(self.iva_file)
            data_file = StringIO(csv_data.decode("utf-8"))
            csv_reader = csv.reader(data_file, delimiter=self.separator)
            
            # Contadores detallados para debugging
            total_rows = 0
            valid_rows = 0
            duplicados_existentes = 0
            comprobantes_nuevos = 0
            total_neto = 0.0
            total_iva = 0.0
            total_general = 0.0
            
            # Contadores de errores específicos para debugging
            filas_cortas = 0
            cuits_invalidos = 0
            montos_cero = 0
            
            for i, row in enumerate(csv_reader):
                if i == 0:  # Header
                    continue
                
                total_rows += 1
                
                # Verificar fila completa (nuevo formato AFIP tiene 28 columnas)
                if len(row) < 28:
                    filas_cortas += 1
                    continue
                
                try:
                    # Extraer datos básicos con limpieza mejorada
                    cuit = row[7].strip().replace('-', '').replace(' ', '') if row[7] else ''
                    doc_type_code = row[1].strip() if len(row) > 1 else ''
                    
                    # Para tipo 11 (comprobantes de compra), usar total en lugar de neto
                    if doc_type_code == '11':
                        amount_str = row[27].strip().replace(' ', '') if len(row) > 27 and row[27] else '0'  # Columna 28: Imp. Total
                    else:
                        amount_str = row[22].strip().replace(' ', '') if len(row) > 22 and row[22] else '0'  # Columna 23: Imp. Neto Gravado Total
                    
                    if not cuit or len(cuit) < 7:  # Menos estricto
                        cuits_invalidos += 1
                        continue
                    
                    # Convertir monto con mejor manejo de formatos
                    try:
                        # Limpiar el string del monto
                        amount_clean = amount_str.replace(',', '.').replace(' ', '').replace('$', '')
                        # Remover puntos que no sean decimales (separadores de miles)
                        parts = amount_clean.split('.')
                        if len(parts) > 2:
                            # Si hay más de un punto, el último es decimal
                            amount_clean = ''.join(parts[:-1]) + '.' + parts[-1]
                        elif len(parts) == 2 and len(parts[1]) > 2:
                            # Si el último grupo tiene más de 2 dígitos, no es decimal
                            amount_clean = ''.join(parts)
                        
                        amount = float(amount_clean)
                    except:
                        amount = 0.0
                    
                    if amount == 0:
                        montos_cero += 1
                        continue
                    
                    valid_rows += 1
                    
                    # Verificar si ya existe (solo para documentos nuevos)
                    if self.import_type == 'new_documents':
                        point_of_sale = row[2].zfill(5) if len(row) > 2 and row[2] else '00001'
                        doc_number = row[3].zfill(8) if len(row) > 3 and row[3] else '00000001'
                        document_number = f"{point_of_sale}-{doc_number}"
                        
                        # Buscar partner - ARREGLO para singleton
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
                    
                    # Calcular totales según tipo de documento (validar amount > 0)
                    if amount > 0:  # Solo procesar si amount es válido
                        if doc_type_code in ['1', '2', '3', '51', '52', '53', '201']:  # Con IVA 21%
                            neto = amount / 1.21
                            iva = amount - neto
                            total_neto += neto
                            total_iva += iva
                        elif doc_type_code in ['202', '203']:  # Con IVA 10.5%
                            neto = amount / 1.105
                            iva = amount - neto
                            total_neto += neto
                            total_iva += iva
                        else:  # Sin IVA o exento
                            total_neto += amount
                    
                    total_general += amount
                    
                except Exception as e:
                    continue
            
            # Generar reporte detallado con información de debugging
            success_percentage = (valid_rows/total_rows*100) if total_rows > 0 else 0
            analysis_message = f"""📊 ANÁLISIS DETALLADO DEL ARCHIVO:

📋 RESUMEN GENERAL:
• Total filas leídas: {total_rows}
• Filas válidas procesables: {valid_rows}
• Filas omitidas: {total_rows - valid_rows}
• Porcentaje de éxito: {success_percentage:.1f}%

🔍 DETALLES DE FILAS OMITIDAS:
• Filas con menos de 17 columnas: {filas_cortas}
• CUITs inválidos (menos de 8 dígitos): {cuits_invalidos}
• Montos en cero: {montos_cero}

💰 TOTALES FINANCIEROS:
• Total Neto a importar: ${total_neto:,.2f}
• Total IVA a importar: ${total_iva:,.2f}
• Total General: ${total_general:,.2f}

🔍 ESTADO DE COMPROBANTES:"""

            if self.import_type == 'new_documents':
                duplicate_percentage = (duplicados_existentes/valid_rows*100) if valid_rows > 0 else 0
                analysis_message += f"""
• Comprobantes ya existentes: {duplicados_existentes}
• Comprobantes nuevos detectados: {comprobantes_nuevos}
• Ratio de duplicados: {duplicate_percentage:.1f}%"""
            else:
                analysis_message += f"""
• Saldos iniciales a procesar: {comprobantes_nuevos}"""

            # Agregar información por tipo de documento
            analysis_message += f"""

📑 DISTRIBUCIÓN POR TIPO:
• Documentos con IVA 21%: Facturas A, Notas A, MiPyme A
• Documentos con IVA 10.5%: MiPyme B y C  
• Documentos exentos: Facturas B y C

✅ ARCHIVO LISTO PARA PROCESAR"""

            # Guardar datos del análisis en campos del modelo
            success_percentage = (valid_rows/total_rows*100) if total_rows > 0 else 0
            duplicate_percentage = (duplicados_existentes/valid_rows*100) if valid_rows > 0 else 0
            
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

            self._add_debug_message(f"{analysis_message}")
            
        except Exception as e:
            raise ValidationError(f'Error analizando archivo: {str(e)}')

    def btn_process_file(self):
        if not self.iva_file:
            raise ValidationError('Debe cargar un archivo CSV')
        
        if self.state != 'analyzed':
            raise ValidationError('Debe analizar el archivo antes de procesarlo')
        
        # Limpiar mensajes de debug anteriores
        self._clear_debug_messages()
        
        try:
            csv_data = base64.b64decode(self.iva_file)
            data_file = StringIO(csv_data.decode("utf-8"))
            csv_reader = csv.reader(data_file, delimiter=self.separator)
            
            # Contadores detallados con información de debug
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
            
            # OPTIMIZACIÓN: Cache inteligente para partners y facturas existentes
            # Inicializar cache para optimización (sin mensaje debug)
            partner_cache = {}  # {cuit: partner_record} - Solo partners necesarios
            duplicate_cache = {}  # {(partner_id, document_name): boolean}
            
            # OPTIMIZACIÓN INTELIGENTE: Pre-cargar solo CUITs que aparecen en el CSV
            csv_cuits = set()
            
            # Primera pasada: extraer todos los CUITs únicos del CSV
            csv_data_temp = base64.b64decode(self.iva_file)
            data_file_temp = StringIO(csv_data_temp.decode("utf-8"))
            csv_reader_temp = csv.reader(data_file_temp, delimiter=self.separator)
            
            for i, row in enumerate(csv_reader_temp):
                if i == 0:  # Saltar header
                    continue
                if len(row) > 7 and row[7]:
                    cuit = row[7].strip().replace('-', '').replace(' ', '')
                    if cuit and len(cuit) >= 7:
                        csv_cuits.add(cuit)
            
            # Cargar partners existentes (sin mensaje debug de éxito)
            
            # Pre-cargar SOLO los partners que necesitamos
            if csv_cuits:
                existing_partners = self.env['res.partner'].search([('vat', 'in', list(csv_cuits))])
                for partner in existing_partners:
                    if partner.vat:
                        partner_cache[partner.vat] = partner
                # Cache cargado exitosamente (sin mensaje debug)
            else:
                self._add_debug_message("⚠️ No se encontraron CUITs válidos en el CSV")
            
            # Pre-cargar facturas existentes si es necesario para detectar duplicados - OPTIMIZADO
            if self.import_type == 'new_documents':
                # Pre-cargar facturas para detectar duplicados (sin mensaje debug de éxito)
                
                # OPTIMIZACIÓN: Solo cargar facturas de partners que están en el CSV
                partner_ids_to_check = [p.id for p in partner_cache.values()]
                
                if partner_ids_to_check:
                    existing_invoices = self.env['account.move'].search([
                        ('state', '!=', 'cancel'),
                        ('name', '!=', False),
                        ('partner_id', 'in', partner_ids_to_check)  # Solo partners relevantes
                    ])
                    
                    for invoice in existing_invoices:
                        if invoice.name and invoice.partner_id:
                            # Crear múltiples claves de búsqueda para el mismo documento
                            cache_keys = [
                                (invoice.partner_id.id, invoice.name),
                            ]
                            # También agregar variaciones del número si está en el campo ref
                            if invoice.ref:
                                cache_keys.append((invoice.partner_id.id, invoice.ref))
                            
                            for key in cache_keys:
                                duplicate_cache[key] = True
                    
                    total_invoices = self.env['account.move'].search_count([
                        ('state', '!=', 'cancel'),
                        ('name', '!=', False),
                        ('partner_id', '!=', False)
                    ])
                    
                    # Cache de duplicados cargado (sin mensaje debug)
                else:
                    self._add_debug_message("⚠️ No hay partners existentes para verificar duplicados")
            
            # Procesar archivo
            # Mensaje inicial más simple
            self._add_debug_message(f"🚀 PROCESANDO: {self.operation_type} - {self.import_type} | Diario: {self.journal_id.name}")
            
            for i, row in enumerate(csv_reader):
                if i == 0:  # Saltar header
                    continue
                
                total_rows += 1
                
                # Solo mostrar progreso cada 100 filas para archivos grandes
                if i % 100 == 0:
                    self._add_debug_message(f"📊 Procesando fila {i}...")
                
                # Verificar que la fila tenga suficientes columnas (nuevo formato AFIP tiene 28)
                if len(row) < 28:
                    facturas_omitidas += 1
                    errores_detallados['filas_cortas'] += 1
                    self._add_debug_message(f"❌ FILA {i}: Omitida por columnas insuficientes ({len(row)}<28)")
                    continue
                
                # DEBUG: Confirmación de que pasó la validación de columnas - solo para problemas
                
                try:
                    # Extraer datos básicos con limpieza mejorada
                    cuit = row[7].strip().replace('-', '').replace(' ', '') if row[7] else ''
                    name = row[8].strip() if row[8] else 'Sin nombre'
                    doc_type_code = row[1].strip() if len(row) > 1 else ''
                    
                    # Para tipo 11 (comprobantes de compra), usar total en lugar de neto
                    if doc_type_code == '11':
                        amount_str = row[27].strip().replace(' ', '') if len(row) > 27 and row[27] else '0'  # Columna 28: Imp. Total
                    else:
                        amount_str = row[22].strip().replace(' ', '') if len(row) > 22 and row[22] else '0'  # Columna 23: Imp. Neto Gravado Total
                    
                    # Validar datos mínimos - CUIT menos estricto
                    if not cuit or len(cuit) < 7:  # Cambiar de 8 a 7 para ser menos estricto
                        facturas_omitidas += 1
                        errores_detallados['cuits_invalidos'] += 1
                        self._add_debug_message(f"❌ FILA {i}: Omitida por CUIT inválido '{cuit}' (menos de 7 dígitos)")
                        continue
                    
                    # Convertir monto con mejor manejo de formatos
                    try:
                        # Limpiar el string del monto
                        amount_clean = amount_str.replace(',', '.').replace(' ', '').replace('$', '')
                        # Remover puntos que no sean decimales (separadores de miles)
                        parts = amount_clean.split('.')
                        if len(parts) > 2:
                            # Si hay más de un punto, el último es decimal
                            amount_clean = ''.join(parts[:-1]) + '.' + parts[-1]
                        elif len(parts) == 2 and len(parts[1]) > 2:
                            # Si el último grupo tiene más de 2 dígitos, no es decimal
                            amount_clean = ''.join(parts)
                        
                        amount = float(amount_clean)
                    except:
                        facturas_omitidas += 1
                        errores_detallados['montos_cero'] += 1
                        self._add_debug_message(f"❌ FILA {i}: Omitida por monto inválido '{amount_str}'")
                        continue
                    
                    if amount == 0:
                        facturas_omitidas += 1
                        errores_detallados['montos_cero'] += 1
                        self._add_debug_message(f"❌ FILA {i}: Omitida por monto en cero")
                        continue
                    
                    # Crear o buscar partner - OPTIMIZACIÓN INTELIGENTE
                    # Elegir método según tamaño de datos
                    total_partners_db = self.env['res.partner'].search_count([('vat', '!=', False)])
                    csv_partners_count = len(csv_cuits)
                    
                    # Verificar si el partner ya existía antes de llamar a los métodos
                    partner_existed_before = cuit in partner_cache
                    
                    # Si el CSV tiene pocos partners únicos VS muchos en BD, usar cache optimizado
                    # Si el CSV tiene muchos partners únicos, usar método híbrido
                    if csv_partners_count < 1000 and total_partners_db > 5000:
                        # Usar cache optimizado (ya cargado)
                        partner = self._get_or_create_partner_optimized(cuit, name, row, partner_cache)
                    else:
                        # Usar método híbrido para grandes volúmenes
                        partner = self._get_or_create_partner_hybrid(cuit, name, row, partner_cache)
                    
                    # Contar partners creados (no existían antes)
                    if partner and not partner_existed_before and cuit in partner_cache:
                        partners_creados += 1
                    
                    # Verificar que el partner sea válido
                    if not partner:
                        facturas_omitidas += 1
                        errores_detallados['partners_invalidos'] += 1
                        self._add_debug_message(f"❌ FILA {i}: Omitida por partner inválido para CUIT '{cuit}'")
                        continue
                        if i <= 20:  # Log primeros 20 partners inválidos
                            self._add_debug_message(f"❌ Fila {i} partner inválido para CUIT: '{cuit}', nombre: '{name}'")
                        continue
                    
                    # Extraer datos del documento para duplicados
                    doc_type_code = row[1].strip() if len(row) > 1 else ''
                    point_of_sale = row[2].zfill(5) if len(row) > 2 and row[2] else '00001'
                    doc_number = row[3].zfill(8) if len(row) > 3 and row[3] else '00000001'
                    document_ref = f"{point_of_sale}-{doc_number}"
                    
                    # Verificar duplicados ANTES de crear la factura - OPTIMIZADO
                    if self.import_type == 'new_documents':
                        # OPTIMIZACIÓN: Usar cache en lugar de _check_duplicate_document
                        is_duplicate = self._check_duplicate_optimized(partner, document_ref, doc_type_code, duplicate_cache)
                        if is_duplicate:
                            facturas_omitidas += 1
                            duplicados_omitidos += 1
                            errores_detallados['duplicados'] += 1
                            self._add_debug_message(f"❌ FILA {i}: Omitida por duplicado - Partner: {partner.name}, Doc: {document_ref}")
                            continue
                    
                    # Crear factura - Ya verificamos duplicados arriba
                    factura = self._create_invoice_simple(partner, row, amount, doc_type_code, point_of_sale, doc_number)
                    
                    if factura:
                        facturas_creadas += 1
                    else:
                        facturas_omitidas += 1
                        errores_detallados['errores_creacion'] += 1
                        self._add_debug_message(f"❌ FILA {i}: Error al crear factura - Partner: {partner.name}, Monto: {amount}")
                        
                except Exception as e:
                    facturas_omitidas += 1
                    errores_detallados['errores_creacion'] += 1
                    self._add_debug_message(f"❌ FILA {i}: Error de procesamiento - {type(e).__name__}: {str(e)[:100]}")
                    continue
            
            # Resumen detallado con información de debugging
            total_partners_db = self.env['res.partner'].search_count([('vat', '!=', False)])
            csv_partners_count = len(csv_cuits)
            strategy_used = "CACHE OPTIMIZADO" if csv_partners_count < 1000 and total_partners_db > 5000 else "HÍBRIDO"
            
            summary_message = (f"Proceso completado:\n"
                             f"• Total filas procesadas: {total_rows}\n"
                             f"• Facturas creadas: {facturas_creadas}\n"
                             f"• Facturas omitidas: {facturas_omitidas}\n"
                             f"• Partners creados: {partners_creados}\n\n"
                             f"OPTIMIZACIONES APLICADAS:\n"
                             f"• Estrategia utilizada: {strategy_used}\n"
                             f"• Partners únicos en CSV: {csv_partners_count}\n"
                             f"• Partners totales en BD: {total_partners_db}\n"
                             f"• Cache de partners: {len(partner_cache)} partners en memoria\n"
                             f"• Cache de duplicados: {len(duplicate_cache)} documentos indexados\n"
                             f"• Ahorro de memoria: {((total_partners_db - len(partner_cache)) / total_partners_db * 100):.1f}%\n\n"
                             f"DETALLES DE ERRORES:\n"
                             f"• Filas cortas (< 17 columnas): {errores_detallados['filas_cortas']}\n"
                             f"• CUITs inválidos: {errores_detallados['cuits_invalidos']}\n"
                             f"• Montos en cero: {errores_detallados['montos_cero']}\n"
                             f"• Partners inválidos: {errores_detallados['partners_invalidos']}\n"
                             f"• Duplicados: {errores_detallados['duplicados']}\n"
                             f"• Errores de creación: {errores_detallados['errores_creacion']}")
            
            if duplicados_omitidos > 0:
                summary_message += f"\n• Duplicados omitidos: {duplicados_omitidos}"
            
            self._add_debug_message(f"{summary_message}")
            
            self.state = 'done'
            
        except Exception as e:
            raise ValidationError(f'Error procesando archivo: {str(e)}')

    def _get_or_create_partner(self, cuit, name, row):
        """Método seguro para obtener o crear partner sin duplicados"""
        try:
            # Buscar partner existente por CUIT/VAT de manera segura
            existing_partners = self.env['res.partner'].search([
                ('vat', '=', cuit),
                ('company_id', 'in', [self.company_id.id, False])
            ])
            
            if existing_partners:
                # Si hay varios, tomar el primero y marcar como existente
                partner = existing_partners[0]
                partner._was_existing = True
                return partner
            
            # No existe, crear nuevo partner
            doc_type_code = row[1].strip() if len(row) > 1 else ''
            
            partner_vals = {
                'name': name,
                'vat': cuit,
                'company_type': 'company',
                'account_iva_file_id': self.id,
                'company_id': self.company_id.id,
            }
            
            # Configurar identificación fiscal (CUIT)
            try:
                cuit_type = self.env['l10n_latam.identification.type'].search([
                    ('name', 'ilike', 'CUIT')
                ], limit=1)
                if cuit_type:
                    partner_vals['l10n_latam_identification_type_id'] = cuit_type.id
            except:
                pass
            
            # Determinar posición fiscal según tipo de documento
            try:
                if doc_type_code in ['1', '2', '3', '201']:  # Factura A, ND A, NC A, MiPyme A
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'IVA Responsable Inscripto')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: IVA Responsable Inscripto (Factura A)")
                elif doc_type_code in ['6', '7', '8', '202']:  # Factura B, ND B, NC B, MiPyme B
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'Consumidor Final')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: Consumidor Final (Factura B)")
                elif doc_type_code in ['11', '12', '13', '203']:  # Factura C, ND C, NC C, MiPyme C
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'Responsable Monotributo')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: Responsable Monotributo (Factura C)")
                else:
                    # Por defecto IVA Responsable Inscripto para tipos no reconocidos
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'IVA Responsable Inscripto')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: IVA Responsable Inscripto (Por defecto)")
            except:
                pass
            
            if self.operation_type == 'purchase':
                partner_vals['supplier_rank'] = 1
            else:
                partner_vals['customer_rank'] = 1
            
            # Crear partner - usar with_context para evitar problemas de concurrencia
            partner = self.env['res.partner'].with_context(check_vat=False).create(partner_vals)
            return partner
            
        except Exception as e:
            # Si hay error, buscar cualquier partner existente con ese CUIT
            fallback_partner = self.env['res.partner'].search([
                ('vat', '=', cuit),
                ('company_id', 'in', [self.company_id.id, False])
            ], limit=1)
            if fallback_partner:
                return fallback_partner
            return None

    def _create_invoice_simple(self, partner, row, amount, doc_type_code=None, point_of_sale=None, doc_number=None):
        """Método simplificado para crear facturas usando lógica nativa de Odoo basado en Odoo 17"""
        try:
            # DEBUG: Log de entrada al método
            self._add_debug_message(f"🔧 DEBUG _create_invoice_simple: Iniciando para partner {partner.name if partner else 'None'}, amount {amount}")
            
            # Verificar que partner sea un singleton válido
            if not partner or len(partner) != 1:
                self._add_debug_message(f"❌ DEBUG: Partner inválido - partner: {partner}, len: {len(partner) if partner else 'N/A'}")
                return None
                
            # Determinar tipo de factura
            if not doc_type_code:
                doc_type_code = row[1].strip() if len(row) > 1 else ''
            if not point_of_sale:
                point_of_sale = row[2].zfill(5) if len(row) > 2 and row[2] else '00001'
            if not doc_number:
                doc_number = row[3].zfill(8) if len(row) > 3 and row[3] else '00000001'
            
            self._add_debug_message(f"🔧 DEBUG: doc_type_code='{doc_type_code}', operation_type='{self.operation_type}'")
                
            if self.operation_type == 'purchase':
                move_type = 'in_refund' if doc_type_code in ['3', '8', '13', '203'] else 'in_invoice'
            else:
                move_type = 'out_refund' if doc_type_code in ['3', '8', '13', '203'] else 'out_invoice'
            
            self._add_debug_message(f"🔧 DEBUG: move_type determinado = '{move_type}'")
            
            # Obtener moneda
            currency_code = row[10].strip() if len(row) > 10 else ''
            if currency_code == 'DOL':
                currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
                currency_id = currency.id if currency else self.env.company.currency_id.id
            else:
                currency_id = self.env.company.currency_id.id
            
            # Número de documento - usar valores pasados como parámetros
            # Para saldos iniciales y documentos nuevos, usar formato AFIP
            document_name = self._get_document_name_by_type(doc_type_code, point_of_sale, doc_number)
            document_ref = f"{point_of_sale}-{doc_number}"  # Para campo ref
            
            self._add_debug_message(f"🔧 DEBUG: document_name='{document_name}', document_ref='{document_ref}'")
            
            # Buscar tipo de documento AFIP
            l10n_latam_document_type_id = False
            if doc_type_code:
                doc_type = self.env['l10n_latam.document.type'].search([
                    ('code', '=', doc_type_code)
                ], limit=1)
                if doc_type:
                    l10n_latam_document_type_id = doc_type.id
                    self._add_debug_message(f"🔧 DEBUG: Tipo documento AFIP encontrado: {doc_type.name}")
                else:
                    self._add_debug_message(f"⚠️ DEBUG: Tipo documento AFIP NO encontrado para código {doc_type_code}")
            
            # LÍNEA DE FACTURA - Clave: Lógica simple de Odoo 17
            self._add_debug_message(f"🔧 DEBUG: import_type='{self.import_type}', product_id='{self.product_id}'")
            
            if self.import_type == 'initial_balances':
                # SALDOS INICIALES: Sin producto, sin impuestos
                line_vals = {
                    'name': 'Saldo inicial',
                    'quantity': 1,
                    'price_unit': amount,
                    'tax_ids': [(6, 0, [])],  # Lista vacía = SIN impuestos
                }
                self._add_debug_message(f"🔧 DEBUG: Línea para saldos iniciales SIN impuestos")
            else:
                # FACTURAS NUEVAS: Con producto y con impuestos
                if self.product_id:
                    tax_ids = self._get_taxes_for_document(doc_type_code)
                    line_vals = {
                        'product_id': self.product_id.id,
                        'name': self.product_id.name or 'Factura',
                        'quantity': 1,
                        'price_unit': amount,
                        'product_uom_id': self.product_id.uom_id.id,
                        'tax_ids': [(6, 0, tax_ids)],
                    }
                    self._add_debug_message(f"🔧 DEBUG: Línea con producto y taxes: {tax_ids}")
                else:
                    # Sin producto configurado
                    line_vals = {
                        'name': 'Factura',
                        'quantity': 1,
                        'price_unit': amount,
                        'tax_ids': [(6, 0, [])],
                    }
                    self._add_debug_message(f"🔧 DEBUG: Línea sin producto configurado")
            
            # CREAR FACTURA - Lógica simple con mejor manejo de fecha
            try:
                # Manejar fecha de manera más robusta
                if len(row) > 0 and row[0] and row[0].strip():
                    date_str = row[0].strip()
                    if '/' in date_str:
                        # Formato DD/MM/YYYY (argentino)
                        parts = date_str.split('/')
                        if len(parts) == 3:
                            try:
                                invoice_date = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
                            except:
                                invoice_date = fields.Date.today()
                        else:
                            invoice_date = fields.Date.today()
                    else:
                        invoice_date = date_str
                else:
                    invoice_date = fields.Date.today()
            except:
                invoice_date = fields.Date.today()
            
            self._add_debug_message(f"🔧 DEBUG: invoice_date='{invoice_date}', journal_id={self.journal_id.id}")
            
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
            
            # Solo agregar campos adicionales para facturas nuevas
            if self.import_type == 'new_documents':
                invoice_vals['ref'] = document_ref
                if l10n_latam_document_type_id:
                    invoice_vals['l10n_latam_document_type_id'] = l10n_latam_document_type_id
            
            self._add_debug_message(f"🔧 DEBUG: invoice_vals preparados: {invoice_vals}")
            
            # Crear la factura con manejo de errores mejorado
            try:
                self._add_debug_message(f"🔧 DEBUG: Intentando crear factura...")
                factura = self.env['account.move'].create(invoice_vals)
                self._add_debug_message(f"✅ DEBUG: Factura creada exitosamente: ID={factura.id}")
                
                # Establecer número AFIP
                try:
                    factura.write({'name': document_name})
                    self._add_debug_message(f"✅ DEBUG: Nombre AFIP establecido: {document_name}")
                except Exception as name_error:
                    self._add_debug_message(f"⚠️ DEBUG: Error estableciendo nombre AFIP: {name_error}")
                
                return factura
            except Exception as e:
                # Log del error específico para debugging
                error_msg = f"Error creando factura para partner {partner.name}: {str(e)}"
                self._add_debug_message(f"❌ ERROR CRÍTICO en create(): {error_msg}")
                self._add_debug_message(f"❌ DETALLES DEL ERROR: {type(e).__name__}: {e}")
                return None
            
        except Exception as e:
            # Error general en el método
            self._add_debug_message(f"❌ ERROR GENERAL en _create_invoice_simple: {type(e).__name__}: {e}")
            return None

    def _get_taxes_for_document(self, doc_type_code):
        """Obtener impuestos según el tipo de documento"""
        try:
            tax_ids = []
            
            # Códigos de documentos que normalmente llevan IVA 21%
            # Facturas A (código 1), Notas de Débito A (código 2), Notas de Crédito A (código 3)
            # Facturas M (código 51), etc.
            iva_21_docs = ['1', '2', '3', '51', '52', '53']
            
            # Códigos de documentos que normalmente llevan IVA 10.5%
            # Algunos productos tienen alícuota reducida
            iva_10_5_docs = ['201', '202', '203']  # Incluye nota de crédito MiPyme 203
            
            # Códigos de documentos que normalmente son exentos o sin IVA
            # Facturas B (código 6), C (sin el 11), etc.
            no_iva_docs = ['6', '7', '12', '13']
            
            # Código específico para IVA No Corresponde
            iva_no_corresp_docs = ['11']
            
            if doc_type_code in iva_21_docs:
                # Buscar IVA 21% para compras o ventas
                if self.operation_type == 'purchase':
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'purchase'),
                        ('amount', '=', 21),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                else:
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'sale'),
                        ('amount', '=', 21),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                
                if tax:
                    tax_ids.append(tax.id)
            
            elif doc_type_code in iva_10_5_docs:
                # Buscar IVA 10.5% para compras o ventas
                if self.operation_type == 'purchase':
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'purchase'),
                        ('amount', '=', 10.5),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                else:
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'sale'),
                        ('amount', '=', 10.5),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                
                if tax:
                    tax_ids.append(tax.id)
            
            elif doc_type_code in iva_no_corresp_docs:
                # Para tipo 11: Buscar IVA No Corresponde / IVA No Correspóndiente
                if self.operation_type == 'purchase':
                    # Buscar por diferentes variaciones del nombre
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'purchase'),
                        ('company_id', '=', self.company_id.id),
                        '|', '|', '|',
                        ('name', 'ilike', 'IVA No Corresp'),
                        ('name', 'ilike', 'IVA No Correspond'),
                        ('name', 'ilike', 'No Correspond'),
                        ('name', 'ilike', 'No Corresp')
                    ], limit=1)
                else:
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'sale'),
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
                # Documentos sin IVA (exentos)
                if self.operation_type == 'purchase':
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'purchase'),
                        ('amount', '=', 0),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                else:
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'sale'),
                        ('amount', '=', 0),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                
                if tax:
                    tax_ids.append(tax.id)
            
            else:
                # Para otros tipos de documento, usar IVA 21% por defecto
                if self.operation_type == 'purchase':
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'purchase'),
                        ('amount', '=', 21),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                else:
                    tax = self.env['account.tax'].search([
                        ('type_tax_use', '=', 'sale'),
                        ('amount', '=', 21),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                
                if tax:
                    tax_ids.append(tax.id)
            
            return tax_ids
            
        except Exception as e:
            # Si hay error, devolver lista vacía
            return []

    def _check_duplicate_document(self, partner, document_number, doc_type_code):
        """Verificar si existe un documento duplicado ANTES de crear la factura"""
        try:
            self._add_debug_message(f"🔍 DEBUG: Verificando duplicados para partner {partner.name}, doc {document_number}")
            
            # Generar los diferentes formatos que podría tener el documento
            point_of_sale, doc_num = document_number.split('-') if '-' in document_number else ('00001', document_number)
            document_name_afip = self._get_document_name_by_type(doc_type_code, point_of_sale, doc_num)
            
            self._add_debug_message(f"🔍 DEBUG: Buscando duplicados - name: '{document_name_afip}', ref: '{document_number}'")
            
            # Buscar por diferentes criterios de duplicados
            duplicate_found = False
            duplicate_source = ""
            
            # 1. PRIORIDAD: Buscar por nombre de factura (campo name) - formato FA-A 00001-00000001
            # Este es el campo que SIEMPRE se llena en Odoo
            existing_by_name = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('name', '=', document_name_afip),
                ('state', '!=', 'cancel')
            ], limit=1)
            
            if existing_by_name:
                duplicate_found = True
                duplicate_source = f"name='{document_name_afip}'"
                self._add_debug_message(f"🔍 DEBUG: Duplicado encontrado por NAME: {existing_by_name.name}")
            
            # 2. Búsqueda por patrones similares en el campo name
            if not duplicate_found:
                # Buscar variaciones del número de documento en el campo name
                # Ejemplo: "FA-A 00001-00000123" o "00001-00000123" o "123"
                search_patterns = [
                    f"%{point_of_sale}-{doc_num}%",  # Buscar 00001-00000123 en cualquier parte
                    f"%{doc_num}%",                   # Buscar solo el número de documento
                ]
                
                for pattern in search_patterns:
                    existing_pattern = self.env['account.move'].search([
                        ('partner_id', '=', partner.id),
                        ('name', 'ilike', pattern),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    
                    if existing_pattern:
                        duplicate_found = True
                        duplicate_source = f"name pattern '{pattern}': {existing_pattern.name}"
                        self._add_debug_message(f"🔍 DEBUG: Duplicado encontrado por PATTERN en NAME: {existing_pattern.name}")
                        break
            
            # 3. SECUNDARIO: Buscar por referencia (campo ref) - solo si existe
            if not duplicate_found:
                existing_by_ref = self.env['account.move'].search([
                    ('partner_id', '=', partner.id),
                    ('ref', '=', document_number),
                    ('state', '!=', 'cancel')
                ], limit=1)
                
                if existing_by_ref:
                    duplicate_found = True
                    duplicate_source = f"ref='{document_number}'"
                    self._add_debug_message(f"🔍 DEBUG: Duplicado encontrado por REF: {existing_by_ref.name}")
            
            # 4. Si hay tipo de documento AFIP, buscar por tipo específico
            if not duplicate_found and doc_type_code:
                doc_type = self.env['l10n_latam.document.type'].search([
                    ('code', '=', doc_type_code)
                ], limit=1)
                
                if doc_type:
                    existing_by_type = self.env['account.move'].search([
                        ('partner_id', '=', partner.id),
                        ('l10n_latam_document_type_id', '=', doc_type.id),
                        '|',
                        ('name', 'ilike', f"%{point_of_sale}-{doc_num}%"),
                        ('ref', '=', document_number),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    
                    if existing_by_type:
                        duplicate_found = True
                        duplicate_source = f"type+doc: {existing_by_type.name}"
                        self._add_debug_message(f"🔍 DEBUG: Duplicado encontrado por TYPE: {existing_by_type.name}")
            
            # 5. Búsqueda amplia por números del documento
            if not duplicate_found:
                # Extraer solo los números del documento para búsqueda amplia
                import re
                numbers_only = re.sub(r'[^0-9]', '', document_number)
                if len(numbers_only) >= 6:  # Solo si tiene suficientes dígitos
                    existing_similar = self.env['account.move'].search([
                        ('partner_id', '=', partner.id),
                        ('name', 'ilike', f"%{numbers_only[-6:]}%"),  # Últimos 6 dígitos
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    
                    if existing_similar:
                        duplicate_found = True
                        duplicate_source = f"similar numbers: {existing_similar.name}"
                        self._add_debug_message(f"🔍 DEBUG: Duplicado encontrado por NÚMEROS SIMILARES: {existing_similar.name}")
            
            if duplicate_found:
                self._add_debug_message(f"⚠️ DUPLICADO DETECTADO: {document_number} para partner {partner.name} ({duplicate_source})")
            else:
                self._add_debug_message(f"✅ DEBUG: No se encontraron duplicados para {document_number}")
            
            return duplicate_found
            
        except Exception as e:
            self._add_debug_message(f"❌ DEBUG: Error verificando duplicados: {type(e).__name__}: {e}")
            # En caso de error, asumir que no es duplicado para permitir la creación
            return False

    def _get_or_create_partner_optimized(self, cuit, name, row, partner_cache):
        """Método optimizado para obtener o crear partner usando cache"""
        try:
            # OPTIMIZACIÓN: Buscar en cache primero
            if cuit in partner_cache:
                partner = partner_cache[cuit]
                return partner
            
            # No existe en cache, crear nuevo partner
            doc_type_code = row[1].strip() if len(row) > 1 else ''
            
            partner_vals = {
                'name': name,
                'vat': cuit,
                'company_type': 'company',
                'account_iva_file_id': self.id,
                'company_id': self.company_id.id,
            }
            
            # Configurar identificación fiscal (CUIT)
            try:
                cuit_type = self.env['l10n_latam.identification.type'].search([
                    ('name', 'ilike', 'CUIT')
                ], limit=1)
                if cuit_type:
                    partner_vals['l10n_latam_identification_type_id'] = cuit_type.id
            except:
                pass
            
            # Determinar posición fiscal según tipo de documento
            try:
                if doc_type_code in ['1', '2', '3', '201']:  # Factura A, ND A, NC A, MiPyme A
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'IVA Responsable Inscripto')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: IVA Responsable Inscripto (Factura A)")
                elif doc_type_code in ['6', '7', '8', '202']:  # Factura B, ND B, NC B, MiPyme B
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'Consumidor Final')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: Consumidor Final (Factura B)")
                elif doc_type_code in ['11', '12', '13', '203']:  # Factura C, ND C, NC C, MiPyme C
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'Responsable Monotributo')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: Responsable Monotributo (Factura C)")
                else:
                    # Por defecto IVA Responsable Inscripto para tipos no reconocidos
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'IVA Responsable Inscripto')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: IVA Responsable Inscripto (Por defecto)")
            except:
                pass
            
            if self.operation_type == 'purchase':
                partner_vals['supplier_rank'] = 1
            else:
                partner_vals['customer_rank'] = 1
            
            # Crear partner - usar with_context para evitar problemas de concurrencia
            partner = self.env['res.partner'].with_context(check_vat=False).create(partner_vals)
            
            # OPTIMIZACIÓN: Agregar al cache inmediatamente
            partner_cache[cuit] = partner
            
            return partner
            
        except Exception as e:
            # Si hay error, buscar cualquier partner existente con ese CUIT
            fallback_partner = self.env['res.partner'].search([
                ('vat', '=', cuit),
                ('company_id', 'in', [self.company_id.id, False])
            ], limit=1)
            if fallback_partner:
                # Agregar al cache para futuras consultas
                partner_cache[cuit] = fallback_partner
                return fallback_partner
            return None

    def _check_duplicate_optimized(self, partner, document_number, doc_type_code, duplicate_cache):
        """Verificar duplicados usando cache optimizado"""
        try:
            self._add_debug_message(f"🔍 DEBUG: Verificando duplicados OPTIMIZADO para partner {partner.name}, doc {document_number}")
            
            # Generar el nombre de documento AFIP
            point_of_sale, doc_num = document_number.split('-') if '-' in document_number else ('00001', document_number)
            document_name_afip = self._get_document_name_by_type(doc_type_code, point_of_sale, doc_num)
            
            # OPTIMIZACIÓN: Buscar en cache primero
            cache_keys = [
                (partner.id, document_name_afip),
                (partner.id, document_number),
            ]
            
            for cache_key in cache_keys:
                if cache_key in duplicate_cache:
                    self._add_debug_message(f"🔍 DEBUG: Duplicado encontrado en CACHE: {cache_key}")
                    return True
            
            # Si no está en cache, significa que no es duplicado
            # (porque pre-cargamos todas las facturas existentes)
            self._add_debug_message(f"✅ DEBUG: No duplicado encontrado en cache")
            return False
            
        except Exception as e:
            self._add_debug_message(f"❌ DEBUG: Error verificando duplicados optimizado: {type(e).__name__}: {e}")
            # En caso de error, usar método original como fallback
            return self._check_duplicate_document(partner, document_number, doc_type_code)

    def _get_or_create_partner_hybrid(self, cuit, name, row, partner_cache):
        """Método híbrido: cache + consulta directa para casos no cacheados"""
        try:
            # OPTIMIZACIÓN: Buscar en cache primero
            if cuit in partner_cache:
                partner = partner_cache[cuit]
                return partner
            
            # No está en cache, hacer consulta directa
            existing_partners = self.env['res.partner'].search([
                ('vat', '=', cuit),
                ('company_id', 'in', [self.company_id.id, False])
            ])
            
            if existing_partners:
                # Encontrado, agregar al cache para futuras consultas
                partner = existing_partners[0]
                partner_cache[cuit] = partner  # Actualizar cache dinámicamente
                return partner
            
            # No existe, crear nuevo partner (mismo código que antes)
            doc_type_code = row[1].strip() if len(row) > 1 else ''
            
            partner_vals = {
                'name': name,
                'vat': cuit,
                'company_type': 'company',
                'account_iva_file_id': self.id,
                'company_id': self.company_id.id,
            }
            
            # Configurar identificación fiscal (CUIT)
            try:
                cuit_type = self.env['l10n_latam.identification.type'].search([
                    ('name', 'ilike', 'CUIT')
                ], limit=1)
                if cuit_type:
                    partner_vals['l10n_latam_identification_type_id'] = cuit_type.id
            except:
                pass
            
            # Determinar posición fiscal según tipo de documento
            try:
                if doc_type_code in ['1', '2', '3', '201']:  # Factura A, ND A, NC A, MiPyme A
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'IVA Responsable Inscripto')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: IVA Responsable Inscripto (Factura A)")
                elif doc_type_code in ['6', '7', '8', '202']:  # Factura B, ND B, NC B, MiPyme B
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'Consumidor Final')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: Consumidor Final (Factura B)")
                elif doc_type_code in ['11', '12', '13', '203']:  # Factura C, ND C, NC C, MiPyme C
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'Responsable Monotributo')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: Responsable Monotributo (Factura C)")
                else:
                    # Por defecto IVA Responsable Inscripto para tipos no reconocidos
                    fiscal_pos = self.env['account.fiscal.position'].search([
                        ('name', 'ilike', 'IVA Responsable Inscripto')
                    ], limit=1)
                    if fiscal_pos:
                        partner_vals['property_account_position_id'] = fiscal_pos.id
                        self._add_debug_message(f"✅ Nuevo partner: {name} - Tipo AFIP: IVA Responsable Inscripto (Por defecto)")
            except:
                pass
            
            if self.operation_type == 'purchase':
                partner_vals['supplier_rank'] = 1
            else:
                partner_vals['customer_rank'] = 1
            
            # Crear partner - usar with_context para evitar problemas de concurrencia
            partner = self.env['res.partner'].with_context(check_vat=False).create(partner_vals)
            
            # OPTIMIZACIÓN: Agregar al cache inmediatamente
            partner_cache[cuit] = partner
            
            return partner
            
        except Exception as e:
            # Si hay error, buscar cualquier partner existente con ese CUIT
            fallback_partner = self.env['res.partner'].search([
                ('vat', '=', cuit),
                ('company_id', 'in', [self.company_id.id, False])
            ], limit=1)
            if fallback_partner:
                # Agregar al cache para futuras consultas
                partner_cache[cuit] = fallback_partner
                return fallback_partner
            return None
