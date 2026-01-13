# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class AccountMove(models.Model):
    """Extension of account.move to link with import files."""

    _inherit = 'account.move'

    account_iva_file_id = fields.Many2one(
        'account.iva.file',
        string='Import File',
        help="Reference to the import file that created this invoice.",
    )
    file_amount = fields.Float(
        string='File Amount',
        help="Original amount from the import file.",
    )
