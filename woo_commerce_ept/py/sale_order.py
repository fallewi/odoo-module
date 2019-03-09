from openerp import models,fields,api,_
import openerp.addons.decimal_precision  as dp
from .. import woocommerce
from openerp.exceptions import Warning
import time
from datetime import timedelta,datetime
import requests

import logging

_logger = logging.getLogger(__name__)

class sale_order(models.Model):
	_inherit="sale.order"

	@api.multi
	def delivery_set(self):
		if self.woo_order_id:
			raise Warning(_('You are not allow to change manually shipping charge in WooCommerce order.'))
		else:
			super(sale_order,self).delivery_set()    
	@api.one
	def _get_woo_order_status(self):
		for order in self:
			flag=False
			for picking in order.picking_ids:
				if picking.state!='cancel':
					flag=True
					break   
			if not flag:
				continue
			if order.picking_ids:
				order.updated_in_woo=True
			else:
				order.updated_in_woo=False
			for picking in order.picking_ids:
				if picking.state =='cancel':
					continue
				if picking.picking_type_id.code!='outgoing':
					continue
				if not picking.updated_in_woo:
					order.updated_in_woo=False
					break

	def _search_woo_order_ids(self,operator,value):
		query="""
					select sale_order.id from stock_picking
					inner join sale_order on sale_order.procurement_group_id=stock_picking.group_id                    
					inner join stock_picking_type on stock_picking.picking_type_id=stock_picking_type.id
					inner join stock_location on stock_location.id=stock_picking_type.default_location_dest_id and stock_location.usage='customer'
					where stock_picking.updated_in_woo=False and stock_picking.state='done'"""
		self._cr.execute(query)
		results = self._cr.fetchall()
		order_ids=[]
		for result_tuple in results:
			order_ids.append(result_tuple[0])
		order_ids = list(set(order_ids))
		return [('id','in',order_ids)]

	
	woo_order_id=fields.Char("woo Order Ref")
	woo_order_number=fields.Char("woo Order Number")
	auto_workflow_process_id=fields.Many2one("sale.workflow.process.ept","Auto Workflow")           
	updated_in_woo=fields.Boolean("Updated In woo",compute=_get_woo_order_status,search='_search_woo_order_ids')
	woo_instance_id=fields.Many2one("woo.instance.ept","Instance")
	woo_closed_at_ept=fields.Datetime("Closed At")    
	
	@api.multi
	def create_or_update_woo_customer(self,woo_cust_id,vals,is_company=False,parent_id=False,type=False,instance=False):
		country_obj=self.env['res.country']
		state_obj=self.env['res.country.state']
		partner_obj=self.env['res.partner']
		
		first_name=vals.get('first_name')
		last_name=vals.get('last_name')
		
		if not first_name and not last_name:
			return False
		
		city=vals.get('city')
		
		name = "%s %s"%(first_name,last_name)
		
		
		company_name=vals.get("company")
		email=vals.get('email')                      
		phone=vals.get("phone")                                  
		zip=vals.get('postcode')            
		
		
		address1=vals.get('address_1')
		address2=vals.get('address_2')
		country_name=vals.get('country')
		state_name = vals.get('state')
		
		woo_customer_id = woo_cust_id
							 
		country=country_obj.search([('code','=',country_name)])
		if not country:
			country=country_obj.search([('name','=',country_name)])
			
		if not country:
			state=state_obj.search([('name','=',state_name)])            
		else:
			state=state_obj.search([('name','=',state_name),('country_id','=',country.id)])           
						

		partner=partner_obj.search([('name','=',name),('city','=',city),('street','=',address1),('street2','=',address2),('email','=',email),('phone','=',phone),('zip','=',zip),('country_id','=',country.id),('state_id','=',state.id)])
		if not partner:
			partner=partner_obj.search([('name','=',name),('city','=',city),('street','=',address1),('street2','=',address2),('zip','=',zip),('country_id','=',country.id)])
			
		if partner:
			partner.write({'state_id':state and state.id or False,'is_company':True,'woo_company_name_ept':company_name,'phone':phone or '','woo_customer_id':woo_customer_id or ''})
		else:
			partner=partner_obj.create({'type':type,'parent_id':parent_id,'woo_customer_id':woo_customer_id or '','name':name,'state_id':state and state.id or False,'city':city,'street':address1,'street2':address2,'country_id':country and country.id or False,'is_company':True,'property_product_pricelist':instance.pricelist_id.id,'property_account_position_id':instance.fiscal_position_id and instance.fiscal_position_id.id or False,'zip':zip,'email':email,'woo_company_name_ept':company_name,'phone':phone})
		return partner        
			

	@api.model
	def createWooAccountTax(self,value,price_included,company,title):
		accounttax_obj = self.env['account.tax']
		
		if price_included:
			name='%s_(%s %s included %s)_%s'%(title,str(value),'%',price_included and 'T' or 'F',company.name)
		else:
			name='%s_(%s %s excluded %s)_%s'%(title,str(value),'%',price_included and 'F' or 'T',company.name)            

		accounttax_id = accounttax_obj.create({'name':name,'amount':float(value),'type_tax_use':'sale','price_include':price_included,'company_id':company.id})
		
		return accounttax_id

	@api.model
	def get_woo_tax_id_ept(self,instance,tax_datas,tax_included):
		tax_id=[]        
		taxes=[]
		for tax in tax_datas:
			rate=float(tax.get('rate',0.0))
			if rate!=0.0:
				rate = rate / 100.0 if rate >= 1 else rate
				acctax_id = self.env['account.tax'].search([('price_include','=',tax_included),('type_tax_use', '=', 'sale'), ('amount', '=', rate),('company_id','=',instance.warehouse_id.company_id.id)])
				if not acctax_id:
					acctax_id = self.createWooAccountTax(rate,tax_included,instance.warehouse_id.company_id,tax.get('name'))
					if acctax_id:
						transaction_log_obj=self.env["woo.transaction.log"]
						message="""Tax was not found in ERP ||
						Automatic Created Tax,%s ||
						tax rate  %s ||
						Company %s"""%(acctax_id.name,rate,instance.company_id.name)                                                                                                                                                                                                                                 
						transaction_log_obj.create(
													{'message':message,
													 'mismatch_details':True,
													 'type':'sales',
													 'woo_instance_id':instance.id
													})                    
				if acctax_id:
					taxes.append(acctax_id.id)
		if taxes:
			tax_id = [(6, 0, taxes)]

		return tax_id

	
	@api.model
	def check_woo_mismatch_details(self,lines,instance,order_number):
		transaction_log_obj=self.env["woo.transaction.log"]
		odoo_product_obj=self.env['product.product']
		woo_product_obj=self.env['woo.product.product.ept']
		mismatch=False
		for line in lines:
			barcode=0
			odoo_product=False
			woo_variant=False
			if line.get('product_id',None):
				woo_variant=woo_product_obj.search([('variant_id','=',line.get('product_id')),('woo_instance_id','=',instance.id)])                
				if woo_variant:
					continue
				try:
					if line.get('product_id'):
						wcapi = instance.connect_in_woo()
						res=wcapi.get('products/%s'%line.get('product_id'))
						if not isinstance(res,requests.models.Response):
							transaction_log_obj.create(
														{'message':"Response is not in proper format,Please Check Details",
														 'mismatch_details':True,
														 'type':'product',
														 'woo_instance_id':instance.id
														})
							continue
						woo_variant =res.json()
						if not isinstance(woo_variant, dict):
							transaction_log_obj.create(
														{'message':"Response is not in proper format,Please Check Details",
														 'mismatch_details':True,
														 'type':'product',
														 'woo_instance_id':instance.id
														})
							continue
						errors = woo_variant.get('errors','')
						if errors:
							message = errors[0].get('message')
							transaction_log_obj.create(
														{'message':"Product Removed from WooCommerce site,  %s"%(message),
														 'mismatch_details':True,
														 'type':'product',
														 'woo_instance_id':instance.id
														})
					else:
						woo_variant = False
				except:
					woo_variant=False
					message="Variant Id %s not found in woo || default_code %s || order ref %s"%(line.get('product_id',None),line.get('sku'),order_number)
					log=transaction_log_obj.search([('woo_instance_id','=',instance.id),('message','=',message)])
					if not log:
						transaction_log_obj.create(
													{'message':message,
													 'mismatch_details':True,
													 'type':'sales',
													 'woo_instance_id':instance.id
													})

				if woo_variant:                    
					barcode=woo_variant.get('product').get('sku')
				else:
					barcode=0
			sku=line.get('sku')
			woo_variant=barcode and woo_product_obj.search([('product_id.default_code','=',barcode),('woo_instance_id','=',instance.id)])
			if not woo_variant:
				odoo_product=barcode and odoo_product_obj.search([('default_code','=',barcode)]) or False
			if not odoo_product and not woo_variant:
				woo_variant=sku and woo_product_obj.search([('default_code','=',sku),('woo_instance_id','=',instance.id)])
				if not woo_variant:
					odoo_product=sku and odoo_product_obj.search([('default_code','=',sku)])

			if not woo_variant and not odoo_product:
				message="%s Product Code Not found for order %s"%(sku,order_number)
				log=transaction_log_obj.search([('woo_instance_id','=',instance.id),('message','=',message)])
				if not log:
					transaction_log_obj.create(
												{'message':message,
												 'mismatch_details':True,
												 'type':'sales',
												 'woo_instance_id':instance.id
												})
				mismatch=True
				break
		return mismatch

	@api.model
	def create_woo_sale_order_line(self,line,tax_ids,product,quantity,fiscal_position,partner,pricelist_id,name,order,price,is_shipping=False):
		sale_order_line_obj=self.env['sale.order.line']
		uom_id=product and product.uom_id and product.uom_id.id or False

		product_data={
					  'product_id':product and product.ids[0] or False,
					  'order_id':order.id,
					  'company_id':order.company_id.id,
					  'product_uom':uom_id,
					  'name':name
					}                                    
								
		
		tmp_rec = sale_order_line_obj.new(product_data)
		tmp_rec.product_id_change()
		so_line_vals=sale_order_line_obj._convert_to_write(tmp_rec._cache)
		
		so_line_vals.update(
							{
							'order_id':order.id,
							'product_uom_qty':quantity,
							'price_unit':price,
							'woo_line_id':line.get('id'),
							'tax_id':tax_ids,
							'is_delivery':is_shipping
							}                                    
							)
		
		line=sale_order_line_obj.create(so_line_vals)        
		return line

	@api.model
	def create_or_update_woo_product(self,line,instance,wcapi):
		woo_product_tmpl_obj=self.env['woo.product.template.ept']
		woo_product_obj=self.env['woo.product.product.ept']        
		variant_id=line.get('product_id')
		woo_product=False
		if variant_id:
			woo_product=woo_product_obj.search([('woo_instance_id','=',instance.id),('variant_id','=',variant_id)],limit=1)
			if woo_product:
				return woo_product
			woo_product=woo_product_obj.search([('woo_instance_id','=',instance.id),('default_code','=',line.get('sku'))],limit=1)
			woo_product and woo_product.write({'variant_id':variant_id})
			if woo_product:
				return woo_product
			response=wcapi.get('products/%s'%(variant_id))
			if not isinstance(response,requests.models.Response):                
				return False
			res = response.json()
			if not isinstance(res, dict):                    
				return False
			result = res.get('product')
			parent_id = result.get('parent_id',False)
			if not parent_id:
				parent_id = variant_id
			woo_product_tmpl_obj.sync_products(instance,parent_id,update_templates=True)
			woo_product=woo_product_obj.search([('woo_instance_id','=',instance.id),('variant_id','=',variant_id)],limit=1)
		else:
			woo_product=woo_product_obj.search([('woo_instance_id','=',instance.id),('default_code','=',line.get('sku'))],limit=1)
			if woo_product:
				return woo_product
		return woo_product

	@api.model
	def get_woo_order_vals(self,result,invoice_address,instance,partner,shipping_address,pricelist_id,fiscal_position,payment_term):
			ordervals={}
			financial_status = 'paid'
			if result.get('payment_details').get('paid'):
				financial_status = 'paid'
			else:
				financial_status = 'not_paid'
			workflow_config=self.env['woo.sale.auto.workflow.configuration'].search([('woo_instance_id','=',instance.id),('financial_status','=',financial_status)])
			workflow=workflow_config and workflow_config.auto_workflow_id or False

			if not workflow:
				transaction_log_obj=self.env["woo.transaction.log"]
				message="Workflow Configuration not found for this order %s and financial status is %s"%(result.get('order_number'),financial_status)
				log=transaction_log_obj.search([('woo_instance_id','=',instance.id),('message','=',message)])
				if not log:
					transaction_log_obj.create(
										{'message':message,
										 'mismatch_details':True,
										 'type':'sales','woo_instance_id':instance.id
										})                    
				return False
			if instance.order_prefix:
				name="%s%s"%(instance.order_prefix,result.get('order_number'))
			else:
				name=result.get('order_number')
			ordervals = {
				'name' :name,                
				'picking_policy' : workflow.picking_policy,                      
				'partner_invoice_id' : invoice_address.ids[0],
				'date_order' :result.get('created_at'),
				'warehouse_id' : instance.warehouse_id.id,
				'partner_id' : partner.ids[0],
				'partner_shipping_id' : shipping_address.ids[0],
				'state' : 'draft',
				'pricelist_id' : pricelist_id or instance.pricelist_id.id or False,
				'fiscal_position_id': fiscal_position and fiscal_position.id  or False,
				'payment_term_id':payment_term or False, 
				'note':result.get('note'),       
				'woo_order_id':result.get('id'),
				'woo_order_number':result.get('order_number'),
				'auto_workflow_process_id':workflow.id,
				'invoice_policy':workflow.invoice_policy,
				'woo_instance_id':instance.id,
				'team_id':instance.section_id and instance.section_id.id or False,
				'company_id':instance.company_id.id,                
			}            
			return ordervals

	def import_all_woo_orders(self,wcapi,instance,transaction_log_obj,page):
		res=wcapi.get('orders?status=%s&page=%s'%(instance.import_order_status or 'on-hold',page))
		response = res.json()
		errors = response.get('errors','')
		if errors:
			message = errors[0].get('message')
			transaction_log_obj.create(
										{'message':message,
										 'mismatch_details':True,
										 'type':'sales',
										 'woo_instance_id':instance.id
										})
			return []
		return response.get('orders')
	
	@api.model
	def auto_import_woo_sale_order_ept(self):
		woo_instance_obj=self.env['woo.instance.ept']
		ctx = dict(self._context) or {}
		woo_instance_id = ctx.get('woo_instance_id',False)
		if woo_instance_id:
			instance=woo_instance_obj.search([('id','=',woo_instance_id)])
			self.import_woo_orders(instance)
		return True

	@api.model
	def import_woo_orders(self,instance=False):        
		instances=[]
		transaction_log_obj=self.env["woo.transaction.log"]
		if not instance:
			instances=self.env['woo.instance.ept'].search([('order_auto_import','=',True),('state','=','confirmed')])
		else:
			instances.append(instance)
		for instance in instances:

			wcapi = instance.connect_in_woo()
			tax_included  = wcapi.get('').json().get('store').get('meta').get('tax_included') or False             
			response = wcapi.get('orders?status=%s'%(instance.import_order_status or 'on-hold'))
			res = response.json()
			order_ids = res.get('orders')                
			total_pages = response.headers.get('X-WC-TotalPages')
			if total_pages >=2:
				for page in range(2,int(total_pages)+1):            
					order_ids = order_ids + self.import_all_woo_orders(wcapi,instance,transaction_log_obj,page)            
			
			import_order_ids=[]
			
			for order in order_ids:  
				if self.search([('woo_instance_id','=',instance.id),('woo_order_id','=',order.get('id')),('woo_order_number','=',order.get('order_number'))]):
					continue
				lines=order.get('line_items')
				if self.check_woo_mismatch_details(lines,instance,order.get('order_number')):
					continue
				woo_customer_id = order.get('customer',{}).get('id',False)    
				partner=order.get('billing_address',False) and self.create_or_update_woo_customer(woo_customer_id,order.get('billing_address'), False, False,False,instance)
				if not partner:                    
					message="Customer Not Available In %s Order"%(order.get('order_number'))
					log=transaction_log_obj.search([('woo_instance_id','=',instance.id),('message','=',message)])
					if not log:
						transaction_log_obj.create(
													{'message':message,
													 'mismatch_details':True,
													 'type':'sales',
													 'woo_instance_id':instance.id
													})
					continue
				shipping_address=order.get('shipping_address',False) and self.create_or_update_woo_customer(woo_customer_id,order.get('shipping_address'), False,partner.id,'delivery',instance) or partner                
	
				new_record = self.new({'partner_id':partner.id})
				new_record.onchange_partner_id()
				retval = self._convert_to_write(new_record._cache)
				
				fiscal_position=partner.property_account_position_id 
				pricelist_id=retval.get('pricelist_id',False)
				payment_term=retval.get('payment_term_id')
				
				woo_order_vals = self.get_woo_order_vals(order, partner, instance, partner, shipping_address, pricelist_id, fiscal_position, payment_term)
				sale_order = self.create(woo_order_vals) if woo_order_vals else False
				
				if not sale_order:
					continue

				def calclulate_line_discount(line):
					return (float(line.get('subtotal')) - float(line.get('total'))) + (float(line.get('subtotal_tax')) - float(line.get('total_tax')))
				
				order_discount = False
				discount_value = 0.0
				total_discount=float(order.get('total_discount',0.0))
				if float(total_discount)>0.0:
					order_discount = True
					if not tax_included:
						discount_value = float(total_discount)
													   
				
				import_order_ids.append(sale_order.id)                
				shipping_taxable = False
				tax_datas = []
				tax_ids = []
				for tax_line in order.get('tax_lines'):
					tax_data = {}
					rate_id = tax_line.get('rate_id')
					if rate_id:
						res_rate = wcapi.get('taxes/%s'%(rate_id))
						rate = res_rate.json()
						tax_data = rate.get('tax',{})
						tax_datas.append(tax_data)
						shipping_taxable = tax_data.get('shipping')                       
				tax_ids = self.get_woo_tax_id_ept(instance,tax_datas,tax_included)
				for line in lines:                    
					woo_product=self.create_or_update_woo_product(line,instance,wcapi)
					if not woo_product:
						continue
					product=woo_product.product_id
					actual_unit_price = 0.0                    
					if tax_included:
						actual_unit_price=(float(line.get('subtotal_tax')) + float(line.get('subtotal'))) / float(line.get('quantity'))                            
					else:
						actual_unit_price = float(line.get('subtotal')) / float(line.get('quantity'))
					if tax_included and float(total_discount)>0.0:
						discount_value += calclulate_line_discount(line) if order_discount else 0.0                                                                            
					self.create_woo_sale_order_line(line,tax_ids,product,line.get('quantity'),fiscal_position,partner,pricelist_id,product.name,sale_order,actual_unit_price,False)                   
	
				shipping_product=instance.shipment_charge_product_id 
				product_id=shipping_product and shipping_product.ids[0] or False
				shipping_tax_ids = []                     
				for line in order.get('shipping_lines',[]):
					if shipping_taxable and float(order.get('shipping_tax')) > 0.0:                        
						shipping_tax_ids =  self.get_woo_tax_id_ept(instance,tax_datas,False)
					else:
						shipping_tax_ids = []
						
					delivery_method=line.get('method_title')
					if delivery_method:
						carrier=self.env['delivery.carrier'].search([('woo_code','=',delivery_method)],limit=1)
						if not carrier:
							carrier=self.env['delivery.carrier'].search([('name','=',delivery_method)],limit=1)
						if not carrier:
							carrier=self.env['delivery.carrier'].search(['|',('name','ilike',delivery_method),('woo_code','ilike',delivery_method)],limit=1)
						if not carrier:
							carrier=self.env['delivery.carrier'].create({'name':delivery_method,'woo_code':delivery_method,'partner_id':self.env.user.company_id.partner_id.id,'product_id':shipping_product.id,'normal_price':line.get('total')})
						sale_order.write({'carrier_id':carrier.id})
						if carrier.product_id:
							shipping_product=carrier.product_id
					line=self.create_woo_sale_order_line(line,shipping_tax_ids,shipping_product,1,fiscal_position,partner,pricelist_id,shipping_product and shipping_product.name or line.get('method_title'),sale_order,line.get('total'),True)
				if order_discount and discount_value:                                                                                                                            
					self.create_woo_sale_order_line({},tax_ids,instance.discount_product_id,1,fiscal_position,partner,pricelist_id,instance.discount_product_id.name,sale_order,discount_value*-1,False)
			if import_order_ids:
				self.env['sale.workflow.process.ept'].auto_workflow_process(ids=import_order_ids)
				odoo_orders=self.browse(import_order_ids)
				for order in odoo_orders:
					order.invoice_shipping_on_delivery=False
		return True
	@api.model
	def woo_closed_at(self,instances):
		for instance in instances:
			if not instance.auto_closed_order: 
				continue
			sales_orders = self.search([('warehouse_id','=',instance.warehouse_id.id),
														 ('woo_order_id','!=',False),
														 ('woo_instance_id','=',instance.id),                                                    
														 ('state','=','done'),('woo_closed_at_ept','=',False)],order='date_order')           
																	   
			sales_orders and sales_orders.write({'woo_closed_at_ept':datetime.now()})
		return True

	@api.model
	def auto_update_woo_order_status_ept(self):
		woo_instance_obj=self.env['woo.instance.ept']
		ctx = dict(self._context) or {}
		woo_instance_id = ctx.get('woo_instance_id',False)
		if woo_instance_id:
			instance=woo_instance_obj.search([('id','=',woo_instance_id)])
			self.update_woo_order_status(instance)
		return True
	
	@api.model
	def update_woo_order_status(self,instance):
		transaction_log_obj=self.env["woo.transaction.log"]
		instances=[]
		if not instance:
			instances=self.env['woo.instance.ept'].search([('order_auto_import','=',True),('state','=','confirmed')])
		else:
			instances.append(instance)
		for instance in instances:
			wcapi = instance.connect_in_woo()    
			sales_orders = self.search([('warehouse_id','=',instance.warehouse_id.id),
														 ('woo_order_id','!=',False),
														 ('woo_instance_id','=',instance.id),                                                     
														 ('updated_in_woo','=',False)],order='date_order')
			
			for sale_order in sales_orders:                
				for picking in sale_order.picking_ids:
					"""Here We Take only done picking and  updated in woo false"""
					if picking.updated_in_woo or picking.state!='done':
						continue                    
					data = {"order": {"status": "completed"}}
					response = wcapi.put('orders/%s'%(sale_order.woo_order_id),data)
					result = response.json()
					errors = result.get('errors','')
					if errors:
						message = errors[0].get('message')
						transaction_log_obj.create(
													{'message':"Error in update order status,  %s"%(message),
													 'mismatch_details':True,
													 'type':'sales',
													 'woo_instance_id':instance.id
													})
					else:
						picking.write({'updated_in_woo':True})
		self.woo_closed_at(instances)
		return True
	
	@api.multi
	@api.onchange('partner_id')
	def onchange_partner_id(self):
		result=super(sale_order,self).onchange_partner_id()
		return result
		
				

class sale_order_line(models.Model):
	_inherit="sale.order.line"
	
	woo_line_id=fields.Char("woo Line")