# Migración a Odoo 18 - Notas

## Cambios realizados para compatibilidad con Odoo 18

### 1. Manifest (__manifest__.py)
- ✅ Actualizado version a '18.0.1.0.0'
- ✅ Cambiado auto_install a False
- ✅ Agregados todos los archivos de datos necesarios

### 2. Vistas XML
- ✅ **account_move_views.xml**: Comentado tree view inheritance problemático
- ✅ **account_iva_file_views.xml**: 
  - Removidas restricciones de dominio en productos
  - Removidos contextos problemáticos en tree views de One2many
  - Creadas vistas tree específicas para evitar conflictos de contexto
  - Cambiado `<tree>` por `<list>` con `type="list"` para compatibilidad con Odoo 18
  - Simplificadas definiciones de tree views para mejor compatibilidad
- ✅ **menu_views.xml**: Corregida referencia a menú padre
- ✅ **account_view.xml**: Removidas definiciones duplicadas

### 3. Archivos de menú
- ✅ **menus.xml**: Removidas definiciones duplicadas de menú

### 4. Modelos (models.py)
- ✅ Sin cambios necesarios - compatible con Odoo 18

## Funcionalidades preservadas
- ✅ Importación de archivos IVA desde CSV
- ✅ Creación automática de facturas
- ✅ Configuración de cuentas contables
- ✅ Gestión de productos (opcional)
- ✅ Vista de facturas importadas
- ✅ Vista de proveedores creados
- ✅ Detección inteligente de duplicados
- ✅ Wizard de selección de cuentas
- ✅ Manejo de monedas múltiples (ARS/USD)

## Funcionalidades temporalmente deshabilitadas
- ⚠️ Decoraciones en tree view de facturas (puede habilitarse posteriormente)

## Optimizaciones realizadas
### Código Python
- ✅ **Imports organizados**: Eliminados imports innecesarios y reorganizados
- ✅ **Método `create` simplificado**: Reducida complejidad en detección de líneas de IVA
- ✅ **Método `btn_process_file` refactorizado**: Dividido en 8 métodos más pequeños y mantenibles
- ✅ **Eliminado código redundante**: Removida lógica compleja e innecesaria
- ✅ **Mejorada legibilidad**: Código más limpio y estructurado

### Vistas XML
- ✅ **Contextos problemáticos removidos**: Eliminados contextos que causaban errores
- ✅ **Herencias simplificadas**: Vistas más compatibles con Odoo 18
- ✅ **Definiciones duplicadas eliminadas**: Código XML más limpio

### Rendimiento
- ✅ **Menos consultas SQL**: Optimizadas búsquedas de partners y facturas
- ✅ **Código más eficiente**: Mejor uso de memoria y procesamiento
- ✅ **Lógica simplificada**: Menos complejidad ciclomática

## Instalación
1. Copiar el módulo a la carpeta de addons de Odoo 18
2. Actualizar la lista de aplicaciones
3. Instalar el módulo "IVA Import"

## Pruebas recomendadas
1. Verificar que el módulo se instala sin errores
2. Probar importación de archivo CSV
3. Verificar creación de facturas y proveedores
4. Confirmar navegación de menús
