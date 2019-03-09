from openerp import models,fields,api
import requests

class woo_tags_ept(models.Model):
    _name="woo.tags.ept"
    
    name=fields.Char("Name",required=1)
    description=fields.Html('Description')       
    woo_tag_id=fields.Integer("Woo Tag Id")    
    exported_in_woo=fields.Boolean("Exported In Woo",default=False)
    woo_instance_id=fields.Many2one("woo.instance.ept","Instance",required=1)
    
    #Constraint for unique tag name per instance
    _sql_constraints=[('unique_tag_name_instance_combination','unique(name,woo_instance_id)',"Product Tag Name Must Be Unique Per Instance.")]

    @api.model
    def export_product_tags(self,instance,woo_product_tags):
        transaction_log_obj=self.env['woo.transaction.log']
        wcapi = instance.connect_in_woo()        
        for woo_product_tag in woo_product_tags:
            data = {'product_tag':{'name': woo_product_tag.name,'description':woo_product_tag.description or ''}}
            
            res=wcapi.post("products/tags", data)
            if not isinstance(res,requests.models.Response):
                transaction_log_obj.create(
                                            {'message':"Response is not in proper format,Please Check Details",
                                             'mismatch_details':True,
                                             'type':'tags',
                                             'woo_instance_id':instance.id
                                            })
                continue
            response = res.json()
            if not isinstance(response, dict):
                transaction_log_obj.create(
                                            {'message':"Response is not in proper format,Please Check Details",
                                             'mismatch_details':True,
                                             'type':'tags',
                                             'woo_instance_id':instance.id
                                            })
                continue
            errors = response.get('errors','')
            if errors:
                message = errors[0].get('message')
                transaction_log_obj.create(
                                            {'message':message,
                                             'mismatch_details':True,
                                             'type':'tags',
                                             'woo_instance_id':instance.id
                                            })
                continue

            product_tag=response.get('product_tag',False)
            product_tag_id= product_tag and product_tag.get('id',False)
            if product_tag_id:
                woo_product_tag.update({'woo_tag_id':product_tag_id,'exported_in_woo':True})
        return True
    
    @api.model
    def update_product_tags_in_woo(self,instance,woo_product_tags):
        transaction_log_obj=self.env['woo.transaction.log']
        wcapi = instance.connect_in_woo()
        for woo_tag in woo_product_tags:                                                               
            data = {
                    "product_tag": {
                                    'name':woo_tag.name,                                    
                                    'description':woo_tag.description
                                    }}
            
            res = wcapi.put('products/tags/%s'%(woo_tag.woo_tag_id),data)
            if not isinstance(res,requests.models.Response):
                transaction_log_obj.create(
                                            {'message':"Response is not in proper format,Please Check Details",
                                             'mismatch_details':True,
                                             'type':'tags',
                                             'woo_instance_id':instance.id
                                            })
                continue
            response =res.json()
            if not isinstance(response, dict):
                transaction_log_obj.create(
                                            {'message':"Response is not in proper format,Please Check Details",
                                             'mismatch_details':True,
                                             'type':'tags',
                                             'woo_instance_id':instance.id
                                            })
                continue
            errors = response.get('errors','')
            if errors:
                message = errors[0].get('message')
                transaction_log_obj.create(
                                            {'message':message,
                                             'mismatch_details':True,
                                             'type':'tags',
                                             'woo_instance_id':instance.id
                                            })
                continue            
        return True 