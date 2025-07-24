# Correcciones para Comprobantes Nuevos

## Problemas Identificados y Solucionados

### 1. Método `_get_document_type` Inexistente
**Problema**: El método `_create_invoice_with_tax_details` llamaba a `_get_document_type` que no existía.
**Solución**: Reemplazado con la lógica existente del método `_create_invoice`.

### 2. Inconsistencia en Número de Documento
**Problema**: Los métodos usaban diferentes formatos para el número de documento.
- `_is_duplicate_document`: Usaba `row[6]` (número simple)
- `_create_invoice`: Usaba `'%s-%s' % (row[2].zfill(5), row[3].zfill(8))` (número completo)

**Solución**: Unificado para usar el formato completo en ambos métodos.

### 3. Falta de Logs de Debugging
**Problema**: No había suficientes logs para identificar dónde fallaba el proceso.
**Solución**: Agregados logs detallados para:
- Tipo de importación
- Procesamiento de cada fila
- Creación de facturas
- Errores específicos

### 4. Manejo de Tipos de Factura
**Problema**: Lógica simplificada que no consideraba tipos de documento para facturas/notas de crédito.
**Solución**: Implementada la misma lógica que el método original para determinar `move_type`.

### 5. Campos Faltantes en Líneas de Factura
**Problema**: Faltaba el campo `product_uom_id` y inicialización correcta de `tax_ids`.
**Solución**: Agregados campos faltantes con valores por defecto.

## Correcciones Implementadas

### A. Método `_create_invoice_with_tax_details`
```python
# Antes
currency_id = self.env.company.currency_id.id
if currency_code == 'DOL':
    usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
    if usd_currency:
        currency_id = usd_currency.id

# Después
currency_id = self._get_currency_from_csv(currency_code)
```

### B. Método `_is_duplicate_document`
```python
# Antes
document_number = row[6]  # Número simple

# Después
document_number = '%s-%s' % (row[2].zfill(5), row[3].zfill(8))  # Número completo
```

### C. Lógica de Tipos de Factura
```python
# Antes
move_type = 'in_invoice' if self.operation_type == 'purchase' else 'out_invoice'

# Después
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
```

### D. Manejo de Errores Mejorado
```python
# Agregado traceback para mejor debugging
except Exception as e:
    print(f"Error creando factura con IVA: {str(e)}")
    import traceback
    traceback.print_exc()
    return None
```

### E. Logs de Debugging
```python
# Agregados logs detallados en cada paso
print(f"Tipo de importación: {self.import_type}")
print(f"  -> Creando factura con detalles de IVA...")
print(f"  -> ✓ Factura creada exitosamente (ID: {factura.id})")
```

## Flujo de Procesamiento Corregido

1. **Análisis de archivo**: Lee el CSV y extrae tipos de cambio
2. **Verificación de duplicados**: Solo para `new_documents`
3. **Actualización de tipos de cambio**: Procesa USD si es necesario
4. **Procesamiento de facturas**: Usa el método correcto según tipo de importación
5. **Creación con IVA**: Extrae alícuota, impuesto y monto neto
6. **Logs detallados**: Muestra progreso y errores específicos

## Expectativas de Funcionamiento

### Para Saldos Iniciales:
- Comportamiento sin cambios
- Importa todas las facturas sin verificar duplicados
- Usa solo monto total

### Para Comprobantes Nuevos:
- Verifica duplicados antes de crear
- Procesa detalles de IVA (alícuota, impuesto, neto)
- Busca y aplica impuestos automáticamente
- Logs detallados de cada operación

## Debugging

Si sigue sin funcionar, los logs mostrarán:
- Qué tipo de importación está seleccionado
- Cuántas filas se procesarán
- Para cada fila: monto, partner, resultado de creación
- Errores específicos con stack trace completo
- Resumen final con estadísticas

Los logs aparecerán en el log de Odoo y en el chatter del registro.
