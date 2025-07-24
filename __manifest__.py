{
    'name': "Importación de IVA Argentino",
    'summary': """
        Importador de IVA desde archivos CSV para facturas de proveedores en Argentina
    """,
    'description': """
        Este módulo permite importar facturas de proveedores desde un archivo CSV con
        formato específico para el IVA en Argentina. Verifica facturas duplicadas y
        permite importar solo las nuevas.
    """,
    'author': "Zanel  Dev",
    'website': "",
    'category': 'Accounting/Localizations',
    'version': '18.0.1.0.0',
    'license': 'AGPL-3',
    'depends': ['base', 'account', 'l10n_ar'],
    'data': [
        'security/ir.model.access.csv',
        'views/menu_views.xml',  # Colocar esta línea ANTES de account_move_views.xml
        'views/account_iva_file_views.xml',
        'views/account_view.xml',
        'views/account_move_views.xml',
        'wizards/account_iva_import_wizard_views.xml',
        'wizards/account_selection_wizard_views.xml',
        'views/menus.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
