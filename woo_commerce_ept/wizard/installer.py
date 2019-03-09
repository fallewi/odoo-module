import logging
from .. import woocommerce

from openerp.exceptions import Warning
_logger = logging.getLogger(__name__)

from openerp import models,fields,api,_

from datetime import datetime
from dateutil.relativedelta import relativedelta

# mapping invoice type to journal type
TYPE2JOURNAL = {
    'out_invoice': 'sale',
    'in_invoice': 'purchase',
    'out_refund': 'sale_refund',
    'in_refund': 'purchase_refund',
}

_intervalTypes = {
    'work_days': lambda interval: relativedelta(days=interval),
    'days': lambda interval: relativedelta(days=interval),
    'hours': lambda interval: relativedelta(hours=interval),
    'weeks': lambda interval: relativedelta(days=7*interval),
    'months': lambda interval: relativedelta(months=interval),
    'minutes': lambda interval: relativedelta(minutes=interval),
}

class woo_instance_config_installer(models.TransientModel):
    _name = 'woo.instance.config.installer'
    _inherit = 'res.config.installer'

    name = fields.Char("Instance Name")
    consumer_key=fields.Char("Consumer Key",required=True)
    consumer_secret=fields.Char("Consumer Secret",required=True)    
    host=fields.Char("Host",required=True)
    verify_ssl=fields.Boolean("Verify SSL",default=False,help="Check this if your WooCommerce site is using SSL certificate")
    country_id = fields.Many2one('res.country',string = "Country",required=True)
    is_image_url = fields.Boolean("Is Image URL?",help="Check this if you use Images from URL\nKepp as it is if you use Product images")
    admin_username=fields.Char("Username", help="Used to Export/Import Image Files.")
    admin_password=fields.Char("Password", help="Used to Export/Import Image Files.")    
    
    @api.multi
    def execute(self):
        host = self.host
        consumer_key = self.consumer_key
        consumer_secret = self.consumer_secret        
        wcapi = woocommerce.api.API(url=host, consumer_key=consumer_key,
                    consumer_secret=consumer_secret,verify_ssl=self.verify_ssl)        
        r = wcapi.get("products")
        if r.status_code == 404:
            raise Warning(_("Enter Valid url"))
        val = r.json()
        msg = ''
        if 'errors' in r.json():
            msg = val['errors'][0]['message'] + '\n' + val['errors'][0]['code']
            raise Warning(_(msg))
        else:    
            self.env['woo.instance.ept'].create({'name':self.name,
                                                 'consumer_key':self.consumer_key,                                                 
                                                 'consumer_secret':self.consumer_secret,                                                 
                                                 'host':self.host,
                                                 'verify_ssl':self.verify_ssl,
                                                 'country_id':self.country_id.id,
                                                 'company_id':self.env.user.company_id.id,
                                                 'is_image_url':self.is_image_url,
                                                 'admin_username':self.admin_username,
                                                 'admin_password':self.admin_password                                                                                                                                                
                                                 })
        return super(woo_instance_config_installer, self).execute()
    
class sale_workflow_process_config_installer(models.TransientModel):
    _name = 'sale.workflow.process.config.installer'
    _inherit = 'res.config.installer'
    
    
    @api.model
    def default_get(self,fields):
        result = super(sale_workflow_process_config_installer,self).default_get(fields)
        workflow= self.env['sale.workflow.process.ept'].search([],limit=1)
        workflow and result.update({'name':workflow.name,
                                    'validate_order':workflow.validate_order,
                                    'create_invoice':workflow.create_invoice,
                                    'validate_invoice':workflow.validate_invoice,
                                    'register_payment':workflow.register_payment,
                                    'invoice_date_is_order_date':workflow.invoice_date_is_order_date,
                                    'journal_id':workflow.journal_id.id,
                                    'sale_journal_id':workflow.sale_journal_id.id,
                                    'picking_policy':workflow.picking_policy,
                                    'auto_check_availability':workflow.auto_check_availability,
                                    'invoice_policy':workflow.invoice_policy})        
        return result
    
    @api.multi
    def modules_to_install(self):
        modules = super(sale_workflow_process_config_installer, self).modules_to_install()
        return set([])
    
    @api.model
    def _default_journal(self):
        inv_type = self._context.get('type', 'out_invoice')
        inv_types = inv_type if isinstance(inv_type, list) else [inv_type]
        company_id = self._context.get('company_id', self.env.user.company_id.id)
        domain = [
            ('type', 'in', filter(None, map(TYPE2JOURNAL.get, inv_types))),
            ('company_id', '=', company_id),
        ]
        return self.env['account.journal'].search(domain, limit=1)
        
    name = fields.Char(string='Name', size=64)
    validate_order = fields.Boolean("Validate Order",default=False)
    create_invoice = fields.Boolean('Create Invoice',default=False)
    validate_invoice = fields.Boolean(string='Validate Invoice',default=False)
    register_payment=fields.Boolean(string='Register Payment',default=False)
    invoice_date_is_order_date = fields.Boolean('Force Invoice Date', help="If it's check the invoice date will be the same as the order date")
    journal_id = fields.Many2one('account.journal', string='Payment Journal',domain=[('type','in',['cash','bank'])])
    sale_journal_id = fields.Many2one('account.journal', string='Sales Journal',default=_default_journal,domain=[('type','=','sale')])
    picking_policy =  fields.Selection([('direct', 'Deliver each product when available'), ('one', 'Deliver all products at once')], string='Shipping Policy')
    auto_check_availability=fields.Boolean("Auto Check Availability",default=False)
    invoice_policy = fields.Selection([('order', 'Ordered quantities'),('delivery', 'Delivered quantities'),],string='Invoicing Policy')
    
    @api.onchange("validate_order")
    def onchange_invoice_on(self):
        for record in self:
            if not record.validate_order:
                record.auto_check_availability=False    
    
    @api.multi
    def execute(self):
        workflow= self.env['sale.workflow.process.ept'].search([],limit=1)
        workflow and workflow.write({'name':self.name,
                                    'validate_order':self.validate_order,
                                    'create_invoice':self.create_invoice,
                                    'validate_invoice':self.validate_invoice,
                                    'register_payment':self.register_payment,
                                    'invoice_date_is_order_date':self.invoice_date_is_order_date,
                                    'journal_id':self.journal_id.id,
                                    'sale_journal_id':self.sale_journal_id.id,
                                    'picking_policy':self.picking_policy,
                                    'auto_check_availability':self.auto_check_availability,
                                    'invoice_policy':self.invoice_policy})
        return super(sale_workflow_process_config_installer, self).execute()
    
class woo_instance_financial_status_config_installer(models.TransientModel):
    _name = 'woo.instance.financial.status.config.installer'
    _inherit = 'res.config.installer'
    
    financial_status=fields.Selection([('paid','The finances have been paid'),
                                        ('not_paid','The finances have been not paid'),                                        
                                        ],default="paid",required=1)
    auto_workflow_id=fields.Many2one("sale.workflow.process.ept","Auto Workflow Id",required=1)
    
    woo_instance_id=fields.Many2one("woo.instance.ept","Instance",required=1)    
    
    @api.multi
    def modules_to_install(self):
        modules = super(woo_instance_financial_status_config_installer, self).modules_to_install()
        return set([])

    @api.multi
    def execute(self):
        self.env['woo.sale.auto.workflow.configuration'].create({'woo_instance_id':self.woo_instance_id.id,
                                                 'auto_workflow_id':self.auto_workflow_id.id,                                                 
                                                 'financial_status':self.financial_status                                                                                                                                                                                                                                                
                                                 })
        return super(woo_instance_financial_status_config_installer, self).execute()            
    
class woo_instance_general_config_installer(models.TransientModel):
    _name = 'woo.instance.general.config.installer'
    _inherit = 'res.config.installer'
    
    @api.multi
    def modules_to_install(self):
        modules = super(woo_instance_general_config_installer, self).modules_to_install()
        return set([])    
        
    @api.model
    def _default_instance(self):
        instances = self.env['woo.instance.ept'].search([])
        return instances and instances[0].id or False
    
   
    @api.model
    def _get_default_company(self):
        company_id = self.env.user._get_company()
        if not company_id:
            raise Warning(_('There is no default company for the current user!'))
        return company_id
        
    woo_instance_id = fields.Many2one('woo.instance.ept', 'Instance', default=_default_instance)
    warehouse_id = fields.Many2one('stock.warehouse',string = "Warehouse")
    company_id = fields.Many2one('res.company',string='Company')
    country_id = fields.Many2one('res.country',string = "Country")
    lang_id = fields.Many2one('res.lang', string='Language')
    order_prefix = fields.Char(size=10, string='Order Prefix')
    import_order_status = fields.Selection([('pending','Pending Payment'),('processing','Processing'),('on-hold','On Hold'),('completed','Completed')],default='on-hold',help="Selected status orders will be imported from WooCommerce")           

    stock_field = fields.Many2one('ir.model.fields', string='Stock Field')
    
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Term')    
    section_id=fields.Many2one('crm.team', 'Sales Team')
        
    shipment_charge_product_id=fields.Many2one("product.product","Shipment Fee",domain=[('type','=','service')])
    discount_product_id=fields.Many2one("product.product","Discount",domain=[('type','=','service')],required=False)

    fiscal_position_id = fields.Many2one('account.fiscal.position', string='Fiscal Position')                
    auto_closed_order = fields.Boolean("Auto Closed Order",Default=False)        
    
       
    order_auto_import = fields.Boolean(string='Auto Order Import?')
    order_import_interval_number = fields.Integer('Import Order Interval Number',help="Repeat every x.")
    order_import_interval_type = fields.Selection( [('minutes', 'Minutes'),
            ('hours','Hours'), ('work_days','Work Days'), ('days', 'Days'),('weeks', 'Weeks'), ('months', 'Months')], 'Import Order Interval Unit')
    order_import_next_execution = fields.Datetime('Next Execution', help='Next execution time')
    
    
    order_auto_update=fields.Boolean(string="Auto Order Update ?")
    order_update_interval_number = fields.Integer('Update Order Interval Number',help="Repeat every x.")
    order_update_interval_type = fields.Selection( [('minutes', 'Minutes'),
            ('hours','Hours'), ('work_days','Work Days'), ('days', 'Days'),('weeks', 'Weeks'), ('months', 'Months')], 'Update Order Interval Unit')               
    order_update_next_execution = fields.Datetime('Next Execution', help='Next execution time')
    
    stock_auto_export=fields.Boolean('Stock Auto Update.', default=False)
    update_stock_interval_number = fields.Integer('Update Order Interval Number',help="Repeat every x.")
    update_stock_interval_type = fields.Selection( [('minutes', 'Minutes'),
            ('hours','Hours'), ('work_days','Work Days'), ('days', 'Days'),('weeks', 'Weeks'), ('months', 'Months')], 'Update Order Interval Unit')
    update_stock_next_execution = fields.Datetime('Next Execution', help='Next execution time')
        
    
    @api.onchange('woo_instance_id')
    def onchange_instance_id(self):        
        instance = self.woo_instance_id or False
        self.company_id=instance and instance.company_id and instance.company_id.id or False
        self.warehouse_id = instance and instance.warehouse_id and instance.warehouse_id.id or False
        self.country_id = instance and instance.country_id and instance.country_id.id or False
        self.lang_id = instance and instance.lang_id and instance.lang_id.id or False
        self.order_prefix = instance and instance.order_prefix or ''
        self.import_order_status = instance and instance.import_order_status or 'on-hold'
        self.stock_field = instance and instance.stock_field and instance.stock_field.id or False
        self.pricelist_id = instance and instance.pricelist_id and instance.pricelist_id.id or False
        self.payment_term_id = instance and instance.payment_term_id and instance.payment_term_id.id or False 
        self.shipment_charge_product_id = instance and instance.shipment_charge_product_id and instance.shipment_charge_product_id.id or False
        self.fiscal_position_id = instance and instance.fiscal_position_id and instance.fiscal_position_id.id or False
        self.discount_product_id=instance and instance.discount_product_id and instance.discount_product_id.id or False        
        self.order_auto_import=instance and instance.order_auto_import
        self.stock_auto_export=instance and instance.stock_auto_export
        self.auto_closed_order=instance and instance.auto_closed_order
        self.order_auto_update=instance and instance.order_auto_update
        self.section_id=instance and instance.section_id and instance.section_id.id or False
        try:
            inventory_cron_exist = instance and self.env.ref('woo_commerce_ept.ir_cron_update_woo_stock_instance_%d'%(instance.id),raise_if_not_found=False)
        except:
            inventory_cron_exist=False
        if inventory_cron_exist:
            self.update_stock_interval_number=inventory_cron_exist.interval_number or False
            self.update_stock_interval_type=inventory_cron_exist.interval_type or False
             
        try:
            order_import_cron_exist = instance and self.env.ref('woo_commerce_ept.ir_cron_import_woo_orders_instance_%d'%(instance.id),raise_if_not_found=False)
        except:
            order_import_cron_exist=False
        if order_import_cron_exist:
            self.order_import_interval_number = order_import_cron_exist.interval_number or False
            self.order_import_interval_type = order_import_cron_exist.interval_type or False
        try:
            order_update_cron_exist = instance and self.env.ref('woo_commerce_ept.ir_cron_update_woo_order_status_instance_%d'%(instance.id),raise_if_not_found=False)
        except:
            order_update_cron_exist=False
        if order_update_cron_exist:
            self.order_update_interval_number= order_update_cron_exist.interval_number or False
            self.order_update_interval_type= order_update_cron_exist.interval_type or False

    @api.multi
    def execute(self):
        instance = self.woo_instance_id
        values = {}
        res = super(woo_instance_general_config_installer,self).execute()
        if instance:
            values['company_id'] = self.company_id and self.company_id.id or False
            values['warehouse_id'] = self.warehouse_id and self.warehouse_id.id or False
            values['country_id'] = self.country_id and self.country_id.id or False
            values['lang_id'] = self.lang_id and self.lang_id.id or False
            values['order_prefix'] = self.order_prefix and self.order_prefix
            values['import_order_status'] = self.import_order_status and self.import_order_status or 'on-hold'           
            values['stock_field'] = self.stock_field and self.stock_field.id or False
            values['pricelist_id'] = self.pricelist_id and self.pricelist_id.id or False
            values['payment_term_id'] = self.payment_term_id and self.payment_term_id.id or False 
            values['shipment_charge_product_id'] = self.shipment_charge_product_id and self.shipment_charge_product_id.id or False
            values['fiscal_position_id'] = self.fiscal_position_id and self.fiscal_position_id.id or False
            values['discount_product_id']=self.discount_product_id.id or False            
            values['order_auto_import']=self.order_auto_import
            values['stock_auto_export']=self.stock_auto_export
            values['auto_closed_order']=self.auto_closed_order
            values['order_auto_update']=self.order_auto_update
            values['section_id']=self.section_id and self.section_id.id or False
            instance.write(values)
            instance.confirm()
            self.setup_order_import_cron(instance)
            self.setup_order_status_update_cron(instance)                             
            self.setup_update_stock_cron(instance)                 

        return res

    @api.multi   
    def setup_order_import_cron(self,instance):
        if self.order_auto_import:
            try:
                cron_exist = self.env.ref('woo_commerce_ept.ir_cron_import_woo_orders_instance_%d'%(instance.id),raise_if_not_found=False)
            except:
                cron_exist=False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.order_import_interval_type](self.order_import_interval_number)
            vals = {
                    'active' : True,
                    'interval_number':self.order_import_interval_number,
                    'interval_type':self.order_import_interval_type,
                    'nextcall':nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                    'args':"([{'woo_instance_id':%d}])"%(instance.id)}
                    
            if cron_exist:
                vals.update({'name' : cron_exist.name})
                cron_exist.write(vals)
            else:
                try:
                    import_order_cron = self.env.ref('woo_commerce_ept.ir_cron_import_woo_orders')
                except:
                    import_order_cron=False
                if not import_order_cron:
                    raise Warning('Core settings of WooCommerce are deleted, please upgrade WooCommerce Connector module to back this settings.')
                
                name = instance.name + ' : ' +import_order_cron.name
                vals.update({'name' : name})
                new_cron = import_order_cron.copy(default=vals)
                self.env['ir.model.data'].create({'module':'woo_commerce_ept',
                                                  'name':'ir_cron_import_woo_orders_instance_%d'%(instance.id),
                                                  'model': 'ir.cron',
                                                  'res_id' : new_cron.id,
                                                  'noupdate' : True
                                                  })
        else:
            try:
                cron_exist = self.env.ref('woo_commerce_ept.ir_cron_import_woo_orders_instance_%d'%(instance.id))
            except:
                cron_exist=False
            
            if cron_exist:
                cron_exist.write({'active':False})
        return True                                                                                                                
        
    
    @api.multi   
    def setup_order_status_update_cron(self,instance):
        if self.order_auto_update:
            try:
                cron_exist = self.env.ref('woo_commerce_ept.ir_cron_update_woo_order_status_instance_%d'%(instance.id))
            except:
                cron_exist=False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.order_update_interval_type](self.order_update_interval_number)
            vals = {'active' : True,
                    'interval_number':self.order_update_interval_number,
                    'interval_type':self.order_update_interval_type,
                    'nextcall':nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                    'args':"([{'woo_instance_id':%d}])"%(instance.id)}
                    
            if cron_exist:
                vals.update({'name' : cron_exist.name})
                cron_exist.write(vals)
            else:
                try:
                    update_order_cron = self.env.ref('woo_commerce_ept.ir_cron_update_woo_order_status')
                except:
                    update_order_cron=False
                if not update_order_cron:
                    raise Warning('Core settings of WooCommerce are deleted, please upgrade WooCommerce Connector module to back this settings.')
                
                name = instance.name + ' : ' +update_order_cron.name
                vals.update({'name' : name}) 
                new_cron = update_order_cron.copy(default=vals)
                self.env['ir.model.data'].create({'module':'woo_commerce_ept',
                                                  'name':'ir_cron_update_woo_order_status_instance_%d'%(instance.id),
                                                  'model': 'ir.cron',
                                                  'res_id' : new_cron.id,
                                                  'noupdate' : True
                                                  })
        else:
            try:
                cron_exist = self.env.ref('woo_commerce_ept.ir_cron_update_woo_order_status_instance_%d'%(instance.id))
            except:
                cron_exist=False
            if cron_exist:
                cron_exist.write({'active':False})
        return True
    
    @api.multi   
    def setup_update_stock_cron(self,instance):
        if self.stock_auto_export:
            try:                
                cron_exist = self.env.ref('woo_commerce_ept.ir_cron_update_woo_stock_instance_%d'%(instance.id))
            except:
                cron_exist=False
            nextcall = datetime.now()
            nextcall += _intervalTypes[self.update_stock_interval_type](self.update_stock_interval_number)
            vals = {'active' : True,
                    'interval_number':self.update_stock_interval_number,
                    'interval_type':self.update_stock_interval_type,
                    'nextcall':nextcall.strftime('%Y-%m-%d %H:%M:%S'),
                    'args':"([{'woo_instance_id':%d}])"%(instance.id)}
            if cron_exist:
                vals.update({'name' : cron_exist.name})
                cron_exist.write(vals)
            else:
                try:                    
                    update_stock_cron = self.env.ref('woo_commerce_ept.ir_cron_update_woo_stock')
                except:
                    update_stock_cron=False
                if not update_stock_cron:
                    raise Warning('Core settings of WooCommerce are deleted, please upgrade WooCommerce Connector module to back this settings.')
                
                name = instance.name + ' : ' +update_stock_cron.name
                vals.update({'name':name})
                new_cron = update_stock_cron.copy(default=vals)
                self.env['ir.model.data'].create({'module':'woo_commerce_ept',
                                                  'name':'ir_cron_update_woo_stock_instance_%d'%(instance.id),
                                                  'model': 'ir.cron',
                                                  'res_id' : new_cron.id,
                                                  'noupdate' : True
                                                  })
        else:
            try:
                cron_exist = self.env.ref('woo_commerce_ept.ir_cron_update_woo_stock_instance_%d'%(instance.id))
            except:
                cron_exist=False
            if cron_exist:
                cron_exist.write({'active':False})        
        return True        