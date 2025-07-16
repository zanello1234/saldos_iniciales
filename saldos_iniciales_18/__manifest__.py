{
    "name": "Saldos Iniciales",
    "summary": """
        Importación de Saldos por Cobrar y Pagar
        """,
    "description": """
        Módulo para importar archivos CSV con saldos por cobrar o pagar, o comprobantes nuevos en Odoo 18.
        
        Características:
        - Importación de saldos iniciales (monto total sin detalles de IVA)
        - Importación de comprobantes nuevos con detalles de IVA (alícuota e impuesto)
        - Verificación de duplicados para comprobantes nuevos
        - Funciona con archivos CSV en formato AFIP
        - Soporte para múltiples monedas (DOL -> USD, PES -> ARS)
        - Actualización automática de tipos de cambio
        - Creación automática de contactos (proveedores/clientes)
        
        Tipos de importación:
        • Saldos iniciales: Para importar saldos existentes sin verificar duplicados
        • Comprobantes nuevos: Para importar nuevos comprobantes con verificación de duplicados y detalles de IVA
    """,
    "category": "Accounting",
    "version": "18.0.1.2.0",
    "depends": ["base", "account", "l10n_ar", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "account_view.xml",
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
