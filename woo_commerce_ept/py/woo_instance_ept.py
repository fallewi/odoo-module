from openerp import models,fields,api,_
from openerp.exceptions import Warning
from .. import woocommerce
import requests
class woo_instance_ept(models.Model):
    _name="woo.instance.ept"
    
    @api.model
    def _default_stock_field(self):
        qty_available = self.env['ir.model.fields'].search([('model_id.model','=','product.product'),('name','=','qty_available')],limit=1)
        return qty_available and qty_available.id
    
    name = fields.Char(size=120, string='Name', required=True)
    company_id = fields.Many2one('res.company',string='Company', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    lang_id = fields.Many2one('res.lang', string='Language')
    order_prefix = fields.Char(size=10, string='Order Prefix')
    import_order_status = fields.Selection([('pending','Pending Payment'),('processing','Processing'),('on-hold','On Hold'),('completed','Completed')],default='on-hold')
    order_auto_import = fields.Boolean(string='Auto Order Import?')
    order_auto_update=fields.Boolean(string="Auto Order Update ?")
    stock_auto_export=fields.Boolean(string="Stock Auto Export?")    
    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiscal Position')
    stock_field = fields.Many2one('ir.model.fields', string='Stock Field', default=_default_stock_field)
    country_id=fields.Many2one("res.country","Country")
    host=fields.Char("Host",required=True)    
    consumer_key=fields.Char("Consumer Key",required=True)
    consumer_secret=fields.Char("Consumer Secret",required=True)
    verify_ssl=fields.Boolean("Verify SSL",default=False,help="Check this if your WooCommerce site is using SSL certificate")      
    shipment_charge_product_id=fields.Many2one("product.product","Shipment Fee",domain=[('type','=','service')])
    section_id=fields.Many2one('crm.team', 'Sales Team')
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term')    
    discount_product_id=fields.Many2one("product.product","Discount",domain=[('type','=','service')])    
    last_inventory_update_time=fields.Datetime("Last Inventory Update Time")
    auto_closed_order=fields.Boolean("Auto Closed Order",default=False)
    state=fields.Selection([('not_confirmed','Not Confirmed'),('confirmed','Confirmed')],default='not_confirmed')
    is_image_url = fields.Boolean("Is Image URL?",help="Check this if you use Images from URL\nKepp as it is if you use Product images")
    admin_username=fields.Char("Username", help="Used to Export/Import Image Files.")
    admin_password=fields.Char("Password", help="Used to Export/Import Image Files.")        

    @api.multi
    def test_woo_connection(self):              
        wcapi = self.connect_in_woo()
        r = wcapi.get("products")
        if not isinstance(r,requests.models.Response):
            raise Warning(_("Response is not in proper format"))                           
        if r.status_code == 404:
            raise Warning(_("Enter Valid url"))
        val = r.json()
        if not isinstance(val, dict):
            raise Warning(_("Please check details"))
        msg = ''
        if 'errors' in r.json():
            msg = val['errors'][0]['message'] + '\n' + val['errors'][0]['code']
            raise Warning(_(msg))
        else:
            raise Warning('Service working properly')
        return True            
                
        
        
    @api.multi
    def reset_to_confirm(self):
        self.write({'state':'not_confirmed'})
        return True
    @api.multi
    def confirm(self):        
        wcapi = self.connect_in_woo()
        r = wcapi.get("products")
        if not isinstance(r,requests.models.Response):
            raise Warning(_("Response is not in proper format"))
        if r.status_code == 404:
            raise Warning(_("Enter Valid url"))
        val = r.json()
        if not isinstance(val, dict):
            raise Warning(_("Please check details"))
        msg = ''
        if 'errors' in r.json():
            msg = val['errors'][0]['message'] + '\n' + val['errors'][0]['code']
            raise Warning(_(msg))
        else:            
            self.write({'state':'confirmed'})
        return True              
        
    @api.model
    def connect_in_woo(self):
        host = self.host
        consumer_key = self.consumer_key
        consumer_secret = self.consumer_secret        
        wcapi = woocommerce.api.API(url=host, consumer_key=consumer_key,
                    consumer_secret=consumer_secret,verify_ssl=self.verify_ssl)
        return wcapi                 