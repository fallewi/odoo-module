from openerp import models,fields,api

class res_partner(models.Model):
    _inherit="res.partner"
    woo_company_name_ept=fields.Char("Company Name")
    woo_customer_id=fields.Char("Woo Cutstomer Id")