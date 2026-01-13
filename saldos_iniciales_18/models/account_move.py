# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


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

    # Computed field for displaying exchange rate in the tree view
    display_exchange_rate = fields.Float(
        string='Exchange Rate',
        compute='_compute_display_exchange_rate',
        digits=(12, 4),
    )

    @api.depends('amount_total', 'amount_total_signed', 'currency_id')
    def _compute_display_exchange_rate(self):
        for move in self:
            if move.currency_id == move.company_id.currency_id:
                move.display_exchange_rate = 1.0
            elif move.amount_total != 0:
                move.display_exchange_rate = abs(move.amount_total_signed / move.amount_total)
            else:
                move.display_exchange_rate = 0.0
