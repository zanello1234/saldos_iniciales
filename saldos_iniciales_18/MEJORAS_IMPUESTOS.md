# Mejoras en el Sistema de Impuestos para Comprobantes Nuevos

## Cambios Realizados

### 1. Método `_get_tax_by_rate` Mejorado
- **Antes**: Búsqueda simple por tasa de impuesto
- **Después**: Lógica robusta copiada del módulo IVA_Import que:
  - Busca impuestos por XML ID primero (más confiable)
  - Maneja correctamente tasas especiales (0%, 10.5%, 21%, 27%)
  - Diferencia entre compras y ventas
  - Fallback a búsqueda por porcentaje si no encuentra por XML ID

### 2. Método `_create_invoice_with_tax_details` Refactorizado
- **Mapeo correcto de columnas CSV**: Ahora usa las mismas columnas que el módulo IVA_Import:
  - `row[11]` = Imp. Neto Gravado
  - `row[12]` = Imp. Neto No Gravado
  - `row[13]` = Imp. Op. Exentas
  - `row[14]` = Otros Tributos
  - `row[15]` = IVA (Impuesto)
  - `row[16]` = Imp. Total

- **Creación de múltiples líneas**: Ahora crea líneas separadas para:
  - Monto gravado (con impuesto IVA)
  - Monto no gravado (sin impuesto)
  - Operaciones exentas (sin impuesto)
  - Otros tributos (sin impuesto)

### 3. Nuevo Método `_detect_tax_rate`
- Detecta automáticamente la tasa de IVA basándose en la relación entre monto gravado y monto de IVA
- Redondea a las tasas estándar argentinas (10.5%, 21%, 27%)
- Maneja casos especiales como documentos tipo 11 (exentos)

## Beneficios

1. **Impuestos Correctos**: Los comprobantes nuevos ahora tendrán los impuestos IVA aplicados correctamente
2. **Compatibilidad**: Usa la misma lógica probada del módulo IVA_Import
3. **Flexibilidad**: Maneja diferentes tipos de documentos y tasas de IVA
4. **Robustez**: Mejor manejo de errores y casos especiales

## Formato del CSV

El sistema ahora espera que las columnas del CSV contengan:
- Columna 15: Monto del IVA
- Columna 11: Monto neto gravado (base imponible)
- Columna 12: Monto no gravado
- Columna 13: Operaciones exentas
- Columna 14: Otros tributos

## Uso

Cuando se selecciona "Comprobantes nuevos" como tipo de importación, el sistema:
1. Analiza los montos de IVA y base imponible
2. Calcula automáticamente la tasa de IVA
3. Busca y aplica el impuesto correspondiente
4. Crea las líneas de factura con los impuestos correctos

## Ejemplo de Funcionamiento

Para una factura con:
- Monto gravado: $100
- IVA: $21
- Total: $121

El sistema:
1. Calcula tasa: 21/100 * 100 = 21%
2. Busca impuesto IVA 21% para compras
3. Crea línea con $100 + impuesto IVA 21%
4. Odoo calcula automáticamente el IVA de $21
