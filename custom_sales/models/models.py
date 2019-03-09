# -*- coding: utf-8 -*-

from odoo import models, fields, api

class customSales(models.Model):
    
    _inherit = 'sale.order'

    demo_field = fields.Char(string='Demo Field')