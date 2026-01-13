# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResPartner(models.Model):
    """Extension of res.partner to link with import files."""

    _inherit = 'res.partner'

    account_iva_file_id = fields.Many2one(
        'account.iva.file',
        string='Import File',
        help="Reference to the import file that created this partner.",
    )
