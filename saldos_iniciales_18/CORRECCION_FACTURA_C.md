# Corrección: Aplicación de IVA No Corresponde para Facturas C

## Problema Identificado
Las facturas tipo C (código '6') no estaban aplicando correctamente el impuesto "IVA No Corresponde" porque la lógica anterior solo aplicaba impuestos cuando `monto_gravado > 0`.

## Solución Implementada

### 1. Modificación en `_create_invoice_with_tax_details`

**Problema anterior:**
```python
# Solo aplicaba impuesto si monto_gravado > 0
if monto_gravado > 0:
    tax = self._get_tax_by_rate(tasa_iva, doc_type_code)
    # ... crear línea
```

**Solución nueva:**
```python
# CASO ESPECIAL: Facturas tipo C (código '6')
if doc_type_code == '6':
    # Para facturas C, crear una línea con el total y aplicar IVA No Corresponde
    tax = self._get_tax_by_rate(0.0, doc_type_code)  # Forzar tasa 0
    line_vals = {
        'name': f"Factura C - {document_number}",
        'price_unit': total_amount,  # Usar el total completo
        'tax_ids': [(6, 0, [tax.id])] if tax else [(6, 0, [])],
    }
```

### 2. Casos Manejados

| Tipo de Factura | Código | Lógica Aplicada |
|------------------|--------|-----------------|
| **Factura C** | '6' | Línea única con total + IVA No Corresponde (0%) |
| **Factura Exenta** | '11' | Línea única con total + IVA No Corresponde (0%) |
| **Factura A/B** | '1', '2', etc. | Líneas separadas según montos + IVA calculado |

### 3. Mejoras en Debug

Agregado debug detallado para rastrear el flujo:

```python
print(f"  -> Tipo de documento: {doc_type_code}")
print(f"  -> Monto gravado: {monto_gravado}")
print(f"  -> IVA amount: {iva_amount}")
print(f"  -> Total amount: {total_amount}")
print(f"  -> Tasa IVA detectada: {tasa_iva}")
```

En `_get_tax_by_rate`:
```python
print(f"    _get_tax_by_rate: rate={rate}, doc_type_code={doc_type_code}")
print(f"    -> Buscando impuesto IVA No Corresponde")
print(f"    -> ✓ Encontrado impuesto por XML ID: {tax_ref}")
```

### 4. Flujo de Ejecución para Facturas C

1. **Detección**: `doc_type_code == '6'`
2. **Forzar tasa 0**: `tax = self._get_tax_by_rate(0.0, doc_type_code)`
3. **Buscar impuesto**: Se busca "IVA No Corresponde" por XML ID
4. **Crear línea**: Una sola línea con el total completo
5. **Aplicar impuesto**: Se aplica el impuesto encontrado

### 5. XML IDs Buscados (en orden de prioridad)

1. `l10n_ar.1_vat_no_corresponde`
2. `l10n_ar.1_vat_no_gravado`
3. `l10n_ar.ri_tax_vat_no_gravado`
4. `l10n_ar.ri_tax_vat_exempt`
5. `l10n_ar.iva_no_gravado`
6. `l10n_ar.iva_exento`

**Fallback**: Si no encuentra por XML ID, busca por `amount = 0`

### 6. Mensaje de Confirmación

Cuando se procesa una factura C exitosamente:
```
  -> Factura C detectada: usando IVA No Corresponde - Total: 1000.00
    _get_tax_by_rate: rate=0.0, doc_type_code=6
    -> Buscando impuesto IVA No Corresponde
    -> ✓ Encontrado impuesto por XML ID: l10n_ar.1_vat_no_corresponde
```

## Validación

Para verificar que funciona:

1. Importar un CSV con facturas tipo C (código '6')
2. Revisar los logs de consola para ver los mensajes de debug
3. Verificar que la factura creada tenga:
   - Una línea única con el total
   - Impuesto "IVA No Corresponde" (0%)
   - Nombre de línea: "Factura C - [número documento]"

## Comportamiento Esperado

✅ **Facturas C**: Línea única con total + IVA No Corresponde  
✅ **Facturas Exentas**: Línea única con total + IVA No Corresponde  
✅ **Facturas A/B**: Líneas separadas + IVA calculado  
✅ **Debug detallado**: Logs claros para identificar problemas
