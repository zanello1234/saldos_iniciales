{
    "name": "l10n_ar_saldos_import",
    "summary": """
        Importación de Saldos por Cobrar y Pagar
        """,
    "description": """
        Módulo para importar archivos CSV con saldos por cobrar o pagar en Odoo 17 Enterprise Edition.
        - Permite cargar archivos CSV con información de facturas de proveedores o clientes.
        - Funciona con el monto total de cada factura, sin detalles de IVA.
        - Compatible con formato de archivo de AFIP.
        - Soporte para múltiples monedas (DOL -> USD, PES -> ARS).
        - Actualización automática de tipos de cambio.
    """,
    "category": "Accounting",
    "version": "17.0.1.2.0",
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
