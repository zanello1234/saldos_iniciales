# 📊 Importador de Saldos Iniciales y Facturas

**Módulo profesional para la importación masiva de saldos iniciales y facturas desde archivos CSV con análisis avanzado y gestión de errores.**

## 🎯 **Características Principales**

### 📈 **Doble Funcionalidad**
- **Saldos Iniciales**: Importación de saldos de apertura sin impuestos
- **Facturas Nuevas**: Importación de comprobantes con productos e impuestos configurables

### 🔍 **Análisis Inteligente Pre-Procesamiento**
- Análisis completo del archivo CSV antes de la importación
- Detección automática de errores y duplicados
- Estadísticas detalladas de viabilidad de importación
- Reportes financieros con totales por tipo de comprobante

### ⚡ **Optimización y Performance**
- Cache inteligente para partners y facturas existentes
- Pre-carga optimizada de datos necesarios
- Procesamiento eficiente de archivos grandes
- Detección optimizada de duplicados

### 🛠️ **Gestión Avanzada de Errores**
- Sistema de debug con formato profesional
- Listado detallado de facturas rechazadas con motivos específicos
- Resumen ejecutivo de resultados de importación
- Seguimiento granular de cada tipo de error

## 📋 **Funcionalidades Detalladas**

### 🔧 **Configuración Flexible**
- **Tipos de Operación**: Compras y Ventas
- **Tipos de Importación**: Saldos iniciales y Facturas nuevas
- **Separadores CSV**: Configurable (punto y coma por defecto)
- **Diarios**: Selección de diario contable específico
- **Productos**: Configuración de producto para facturas nuevas

### 💱 **Gestión de Monedas**
- Soporte para múltiples monedas (ARS, USD)
- Actualización automática de tipos de cambio
- Configuración manual de tipo de cambio USD/ARS

### 🧾 **Tipos de Documento AFIP**
Soporte completo para todos los tipos de documentos argentinos:
- **Facturas A, B, C** (códigos 1, 6, 11)
- **Notas de Débito A, B, C** (códigos 2, 7, 12)
- **Notas de Crédito A, B, C** (códigos 3, 8, 13)
- **MiPymes A, B, C** (códigos 201, 202, 203)
- **Facturas M** (código 51)

### 🏢 **Gestión Automática de Partners**
- Creación automática de proveedores/clientes
- Configuración automática de tipos fiscales AFIP:
  - IVA Responsable Inscripto (Facturas A)
  - Consumidor Final (Facturas B)
  - Responsable Monotributo (Facturas C)
- Validación de CUIT/CUIL con flexibilidad configurable

### 📊 **Reportes y Análisis**

#### **Análisis Pre-Importación**
- Total de filas leídas vs. válidas
- Porcentaje de éxito estimado
- Totales financieros (Neto, IVA, Total)
- Detección de comprobantes duplicados
- Análisis de errores por categoría

#### **Reporte de Procesamiento**
- Resumen ejecutivo de importación
- Estadísticas de éxito/fallo
- Listado numerado de facturas rechazadas
- Clasificación de errores por tipo
- Recomendaciones de corrección

### 🔍 **Sistema de Debug Avanzado**
- **Formato profesional**: Similar al análisis, texto plano estructurado
- **Filtrado inteligente**: Solo muestra errores relevantes y resúmenes
- **Lista detallada**: Cada factura rechazada con número de fila y motivo específico
- **Categorización**: Errores agrupados por tipo para fácil corrección

## 📁 **Formato del Archivo CSV**

El archivo CSV debe contener **17 columnas** en el siguiente orden:

| Columna | Descripción | Ejemplo |
|---------|-------------|---------|
| 1 | Fecha | 15/08/2024 |
| 2 | Tipo de Documento | 1 (Factura A) |
| 3 | Punto de Venta | 00001 |
| 4 | Número de Documento | 00000123 |
| 5-7 | Campos adicionales | - |
| 8 | CUIT/CUIL | 20123456789 |
| 9 | Razón Social | PROVEEDOR SA |
| 10-16 | Campos adicionales | - |
| 17 | Monto Total | 12100.50 |

### 📝 **Ejemplos de Formato**
```csv
15/08/2024;1;00001;00000123;;;20123456789;PROVEEDOR SA;;;;;;12100.50
16/08/2024;6;00001;00000124;;;27987654321;CLIENTE SRL;;;;;;8500.00
```

## 🚀 **Instalación y Uso**

### **1. Instalación**
1. Descargar e instalar el módulo en Odoo 18.0
2. Actualizar la lista de aplicaciones
3. Instalar "Importador de Saldos Iniciales"

### **2. Configuración Inicial**
1. Ir a **Contabilidad > Importar Saldos**
2. Crear un nuevo proceso de importación
3. Configurar:
   - Tipo de operación (Compras/Ventas)
   - Tipo de importación (Saldos/Facturas)
   - Diario contable
   - Producto (solo para facturas nuevas)

### **3. Proceso de Importación**
1. **Cargar archivo CSV** con el formato requerido
2. **Analizar archivo** para verificar datos y detectar errores
3. **Revisar análisis** en la pestaña "Análisis"
4. **Procesar archivo** si el análisis es satisfactorio
5. **Revisar resultados** en las pestañas "Facturas", "Debug" y "Contactos"

## 📈 **Beneficios del Módulo**

### ⏱️ **Ahorro de Tiempo**
- Importación masiva vs. carga manual
- Detección automática de errores antes del procesamiento
- Creación automática de partners con configuración fiscal

### 🎯 **Precisión y Control**
- Validaciones exhaustivas de datos
- Detección inteligente de duplicados
- Reportes detallados de errores y correcciones necesarias

### 📊 **Transparencia Total**
- Análisis completo pre-importación
- Seguimiento granular de cada registro
- Reportes ejecutivos para toma de decisiones

### 🔧 **Flexibilidad**
- Configuración adaptable a diferentes necesidades
- Soporte para múltiples tipos de documento
- Gestión de monedas extranjeras

## 🛡️ **Gestión de Errores**

El módulo identifica y categoriza automáticamente:

- **Datos incompletos**: Filas con menos de 17 columnas
- **CUIT inválidos**: Números con menos de 7 dígitos
- **Montos inválidos**: Valores en cero o no numéricos
- **Proveedores problemáticos**: Errores en creación/búsqueda
- **Facturas duplicadas**: Comprobantes ya existentes
- **Errores de creación**: Problemas en la generación de facturas

## 🏢 **Casos de Uso Típicos**

### **Migración de Sistemas**
- Importación de saldos iniciales desde sistema anterior
- Transferencia masiva de facturas históricas

### **Integración de Datos**
- Carga de facturas desde sistemas externos
- Sincronización con plataformas de e-commerce

### **Procesos Masivos**
- Carga de facturas de múltiples proveedores
- Importación de comprobantes de períodos anteriores

## 🔧 **Requisitos Técnicos**

- **Odoo**: Versión 18.0
- **Módulos base**: account, base
- **Formato de archivo**: CSV con separador configurable
- **Codificación**: UTF-8

## 📞 **Soporte y Documentación**

Para soporte técnico, consultas o personalizaciones:
- Documentación incluida en el módulo
- Ejemplos de archivos CSV
- Guías de configuración paso a paso

---

**Desarrollado para Odoo 18.0 | Módulo Profesional de Importación de Facturas**

*Optimiza tu proceso de carga de datos contables con análisis inteligente y gestión avanzada de errores.*
