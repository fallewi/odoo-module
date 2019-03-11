# -*- coding: utf-8 -*-
from odoofrom odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    payment_amount = fields.Float(string='Payment Amount', default=0.0)
