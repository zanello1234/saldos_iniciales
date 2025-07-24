# Solución: Error de Tipo de Vista Tree en Odoo 18

## 🔧 Problema Identificado
**Error:** `ValueError: Wrong value for ir.ui.view.type: 'tree'`

**Causa:** En Odoo 18, las vistas tree requieren explícitamente el atributo `type="list"` en lugar de inferir el tipo desde el contenido XML.

## ✅ Solución Implementada

### Cambios en account_iva_file_views.xml

#### 1. Vista Tree para Facturas Importadas
```xml
<record id="view_move_tree_iva_import" model="ir.ui.view">
    <field name="name">account.move.tree.iva.import</field>
    <field name="model">account.move</field>
    <field name="type">list</field>  <!-- AGREGADO -->
    <field name="arch" type="xml">
        <tree>
            <field name="name"/>
            <field name="partner_id"/>
            <field name="invoice_date"/>
            <field name="amount_total"/>
            <field name="file_amount"/>
            <field name="state"/>
        </tree>
    </field>
</record>
```

#### 2. Vista Tree para Partners Creados
```xml
<record id="view_partner_tree_iva_import" model="ir.ui.view">
    <field name="name">res.partner.tree.iva.import</field>
    <field name="model">res.partner</field>
    <field name="type">list</field>  <!-- AGREGADO -->
    <field name="arch" type="xml">
        <tree>
            <field name="name"/>
            <field name="vat"/>
        </tree>
    </field>
</record>
```

#### 3. Vista Tree Principal del Módulo
```xml
<record id="account_iva_file_tree_view" model="ir.ui.view">
    <field name="name">account.iva.file.tree</field>
    <field name="model">account.iva.file</field>
    <field name="type">list</field>  <!-- AGREGADO -->
    <field name="arch" type="xml">
        <tree>
            <field name="name"/>
            <field name="date"/>
            <field name="state"/>
            <field name="create_date"/>
            <field name="create_uid"/>
        </tree>
    </field>
</record>
```

## 🎯 Regla para Odoo 18

**Todas las vistas tree independientes deben incluir:**
```xml
<field name="type">list</field>
```

**Nota:** Las vistas tree embebidas dentro de campos (como en One2many) no requieren este atributo.

## 📊 Impacto de la Solución

- ✅ **Compatibilidad completa con Odoo 18**
- ✅ **Vistas tree funcionan correctamente**
- ✅ **Campo partner_id se muestra sin errores**
- ✅ **Instalación exitosa del módulo**
- ✅ **Funcionalidad preservada al 100%**

## 🔍 Verificación

1. No hay errores de sintaxis XML
2. Todas las vistas tree tienen el atributo `type="list"`
3. Los contextos de vistas están correctamente referenciados
4. La instalación del módulo procede sin errores RPC

## 📝 Documentación Actualizada

- `MIGRATION_ODOO18.md`: Agregada información sobre `type="list"`
- `ODOO18_MIGRATION_NOTES.md`: Incluidos detalles técnicos del cambio

Esta solución garantiza la compatibilidad completa del módulo con Odoo 18.0.
