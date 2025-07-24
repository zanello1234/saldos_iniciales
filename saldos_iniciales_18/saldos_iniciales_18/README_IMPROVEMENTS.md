# Mejoras en Módulo Saldos Iniciales

## Nueva Funcionalidad: Tipo de Importación

### Descripción
Se ha agregado un nuevo campo "Tipo de importación" que permite dos tipos de procesamiento:

1. **Saldos iniciales** (por defecto)
2. **Comprobantes nuevos**

### Ubicación del Campo
- **Posición**: Debajo del campo "Tipo de operación" en la vista de formulario
- **Tipo**: Radio buttons horizontales
- **Obligatorio**: Sí

### Funcionalidades por Tipo

#### 1. Saldos Iniciales
- **Comportamiento**: Comportamiento original del módulo
- **Procesamiento**: Importa todos los registros sin verificar duplicados
- **Detalles IVA**: No procesa detalles de IVA (solo monto total)
- **Uso**: Para cargar saldos existentes al inicializar el sistema

#### 2. Comprobantes Nuevos
- **Comportamiento**: Nuevo comportamiento con verificación de duplicados
- **Procesamiento**: Solo importa comprobantes que no existen en el sistema
- **Detalles IVA**: Procesa alícuota e impuesto IVA desde las columnas del CSV
- **Verificación**: Compara con facturas existentes del mismo tipo de operación

### Verificación de Duplicados (Comprobantes Nuevos)

La verificación se realiza buscando facturas existentes que coincidan con:
- **Partner**: Mismo CUIT
- **Número de documento**: Mismo número de comprobante
- **Tipo de factura**: Según tipo de operación (compra/venta)
- **Monto**: Mismo monto total
- **Estado**: Facturas no canceladas

### Procesamiento de IVA (Comprobantes Nuevos)

Para comprobantes nuevos, el sistema extrae y procesa:
- **Columna 13**: Monto neto (base gravable)
- **Columna 14**: Impuesto IVA (monto del impuesto)
- **Columna 15**: Alícuota IVA (tasa del impuesto)
- **Columna 16**: Monto total (net + IVA)

### Estructura del CSV

```
Columna 0:  Fecha
Columna 1:  Tipo de documento
Columna 6:  Número de comprobante
Columna 7:  CUIT del partner
Columna 8:  Nombre del partner
Columna 9:  Tipo de cambio
Columna 10: Código de moneda
Columna 13: Monto neto (nuevo)
Columna 14: Impuesto IVA (nuevo)
Columna 15: Alícuota IVA (nuevo)
Columna 16: Monto total
```

### Flujo de Procesamiento

1. **Análisis inicial**: Se analiza el archivo CSV
2. **Verificación de duplicados**: (Solo para comprobantes nuevos)
3. **Extracción de tipos de cambio**: Para facturas en USD
4. **Actualización de tipos de cambio**: Si está habilitado
5. **Procesamiento de facturas**: Creación con/sin detalles de IVA
6. **Resumen final**: Estadísticas del proceso

### Logs y Debugging

El sistema incluye logs detallados que muestran:
- Tipo de importación seleccionado
- Comprobantes duplicados omitidos
- Facturas creadas con detalles de IVA
- Tipos de cambio procesados
- Resumen de estadísticas

### Compatibilidad

- **Versión**: Odoo 18.0
- **Dependencias**: base, account, l10n_ar, mail
- **Backward compatibility**: Sí (comportamiento por defecto sin cambios)

### Casos de Uso

#### Saldos Iniciales
```
- Migración inicial de datos
- Carga de saldos históricos
- Importación masiva sin verificaciones
```

#### Comprobantes Nuevos
```
- Sincronización periódica con sistemas externos
- Importación de facturas recientes
- Prevención de duplicados
- Procesamiento completo de IVA
```

### Configuración Recomendada

1. **Para saldos iniciales**: 
   - Tipo de importación: "Saldos iniciales"
   - Ejecutar una sola vez al inicializar

2. **Para comprobantes nuevos**:
   - Tipo de importación: "Comprobantes nuevos"
   - Ejecutar periódicamente
   - Verificar configuración de impuestos IVA

### Mejoras Técnicas

- Método `_is_duplicate_document()`: Verificación de duplicados
- Método `_create_invoice_with_tax_details()`: Creación con IVA
- Método `_get_tax_by_rate()`: Búsqueda de impuestos por tasa
- Logs mejorados para debugging
- Validación de datos más robusta

### Notas Importantes

- Los duplicados se omiten silenciosamente (con log)
- Los impuestos IVA se buscan por tasa y tipo de uso
- El monto neto se usa como base para el precio unitario
- Compatible con monedas USD y ARS
- Mantiene compatibilidad con funcionalidad existente
