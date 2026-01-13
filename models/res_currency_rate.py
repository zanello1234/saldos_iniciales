# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCurrencyRate(models.Model):
    """Extension of res.currency.rate to link with import files."""

    _inherit = 'res.currency.rate'

    account_iva_file_id = fields.Many2one(
        'account.iva.file',
        string='Import File',
        ondelete='cascade',
        help="Reference to the import file that created this exchange rate.",
    )
