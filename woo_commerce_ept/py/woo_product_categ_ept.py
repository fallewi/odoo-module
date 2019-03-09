from openerp import models,fields,api
from .. img_upload import img_file_upload
import base64
import requests

class woo_product_categ_ept(models.Model):
    _name='woo.product.categ.ept'
    
    @api.one
    def set_image(self):
        for categ_image in self:
            if categ_image.woo_instance_id.is_image_url:
                if categ_image.response_url:          
                    try:                     
                        img = requests.get(categ_image.response_url,stream=True,verify=False,timeout=10)
                        if img.status_code == 200:
                            categ_image.url_image_id=base64.b64encode(img.content)
                        else:
                            img = requests.get(categ_image.url,stream=True,verify=False,timeout=10)
                            if img.status_code == 200:
                                categ_image.url_image_id=base64.b64encode(img.content)
                    except Exception:
                        try:                     
                            img = requests.get(categ_image.url,stream=True,verify=False,timeout=10)
                            if img.status_code == 200:
                                categ_image.url_image_id=base64.b64encode(img.content)
                        except Exception:
                            pass
                elif categ_image.url:
                    try:                     
                        img = requests.get(categ_image.url,stream=True,verify=False,timeout=10)
                        if img.status_code == 200:
                            categ_image.url_image_id=base64.b64encode(img.content)
                    except Exception:
                        pass            
    
    name=fields.Char('Name', required="1")
    parent_id=fields.Many2one('woo.product.categ.ept', string='Parent')
    description=fields.Html('Description')
    display=fields.Selection([('default','Default'),
                                ('products','Products'),
                                ('subcategories','Sub Categories'),
                                ('both','Both') 
                                ],default='default')
    is_image_url=fields.Boolean("Is Image Url ?",related="woo_instance_id.is_image_url")
    image=fields.Binary('Image')
    url = fields.Char(size=600, string='Image URL')
    response_url = fields.Char(size=600, string='Response URL',help="URL from WooCommerce")
    url_image_id=fields.Binary("Image",compute=set_image,store=False)    
    woo_categ_id=fields.Integer('Woo Category Id', readonly=True)
    woo_instance_id=fields.Many2one("woo.instance.ept","Instance",required=1)
    exported_in_woo=fields.Boolean('Exported In Woo', default=False, readonly=True)
    
    #Constraint for unique category name per instance
    _sql_constraints=[('unique_tag_name_instance_combination','unique(name,woo_instance_id)',"Product Category Name Must Be Unique Per Instance.")]
    
    @api.multi
    def export_product_categs(self,instance,woo_product_categs):
        transaction_log_obj=self.env['woo.transaction.log']
        wcapi = instance.connect_in_woo()        
        for woo_product_categ in woo_product_categs:
            if woo_product_categ.woo_categ_id:
                res = wcapi.get("products/categories/%s"%(woo_product_categ.woo_categ_id))
                if not isinstance(res,requests.models.Response):
                    transaction_log_obj.create(
                                                {'message':"Response is not in proper format,Please Check Details",
                                                 'mismatch_details':True,
                                                 'type':'category',
                                                 'woo_instance_id':instance.id
                                                })
                    continue
                if res.status_code != 404:
                    continue
            product_categs=[]
            product_categs.append(woo_product_categ)
            for categ in product_categs:
                if categ.parent_id and categ.parent_id not in product_categs and not categ.parent_id.woo_categ_id:
                    product_categs.append(categ.parent_id)
                    
            product_categs.reverse()
            for woo_product_categ in product_categs:                
                img_url = ''
                if instance.is_image_url:
                    if woo_product_categ.response_url:
                        try:
                            img = requests.get(woo_product_categ.response_url,stream=True,verify=False,timeout=10)
                            if img.status_code == 200:                                
                                img_url = woo_product_categ.response_url
                            elif woo_product_categ.url:
                                img_url = woo_product_categ.url
                        except Exception:
                            img_url = woo_product_categ.url or ''
                    elif woo_product_categ.url:
                        img_url = woo_product_categ.url
                else:
                    res = {}            
                    if woo_product_categ.image:
                        res = img_file_upload.upload_image(instance,woo_product_categ.image,"%s_%s"%(woo_product_categ.name,woo_product_categ.id))
                    img_url = res and res.get('url',False) or ''                
                data = {'product_category':{'name': woo_product_categ.name,
                                       'description':woo_product_categ.description or '',
                                       'parent':woo_product_categ.parent_id.woo_categ_id or False,
                                       'display':woo_product_categ.display,
                                       'image' :img_url,
                                       }}
                res=wcapi.post("products/categories", data)
                if not isinstance(res,requests.models.Response):
                    transaction_log_obj.create(
                                                {'message':"Response is not in proper format,Please Check Details",
                                                 'mismatch_details':True,
                                                 'type':'category',
                                                 'woo_instance_id':instance.id
                                                })
                    continue
                response = res.json()
                if not isinstance(response, dict):
                    transaction_log_obj.create(
                                                {'message':"Response is not in proper format,Please Check Details",
                                                 'mismatch_details':True,
                                                 'type':'category',
                                                 'woo_instance_id':instance.id
                                                })
                    continue
                errors = response.get('errors','')
                if errors:
                    message = errors[0].get('message')
                    transaction_log_obj.create(
                                                {'message':message,
                                                 'mismatch_details':True,
                                                 'type':'category',
                                                 'woo_instance_id':instance.id
                                                })
                    continue
                product_categ=response.get('product_category',False)
                product_categ_id = product_categ and product_categ.get('id',False)
                response_data = {}
                if instance.is_image_url:
                    response_url = product_categ and product_categ.get('image','')
                    response_data.update({'response_url':response_url})                 
                if product_categ_id:
                    response_data.update({'woo_categ_id':product_categ_id,'exported_in_woo':True})
                    woo_product_categ.write(response_data)
        return True
    
    @api.multi
    def update_product_categs_in_woo(self,instance,woo_product_categs):
        transaction_log_obj=self.env['woo.transaction.log']
        wcapi = instance.connect_in_woo()
        updated_categs=[]
        for woo_categ in woo_product_categs:
            if woo_categ in updated_categs :
                continue
            product_categs=[]
            product_categs.append(woo_categ)
            for categ in product_categs:
                if categ.parent_id and categ.parent_id not in product_categs and categ.parent_id not in updated_categs:
                    self.sync_product_category(instance, woo_product_categ=categ.parent_id)
                    product_categs.append(categ.parent_id)
                    
            product_categs.reverse()
            for woo_categ in product_categs:                
                img_url = ''
                if instance.is_image_url:                
                    if woo_categ.response_url:
                        try:
                            img = requests.get(woo_categ.response_url,stream=True,verify=False,timeout=10)
                            if img.status_code == 200:
                                img_url = woo_categ.response_url
                            elif woo_categ.url:
                                img_url = woo_categ.url
                        except Exception:
                            img_url = woo_categ.url or ''
                    elif woo_categ.url:
                        img_url = woo_categ.url
                else:
                    res = {}            
                    if woo_categ.image:
                        res = img_file_upload.upload_image(instance,woo_categ.image,"%s_%s"%(woo_categ.name,woo_categ.id))
                    img_url = res and res.get('url',False) or ''
                                                                
                data = {
                        "product_category": {
                                        'parent':woo_categ.parent_id.woo_categ_id or False,
                                        'display':woo_categ.display,
                                        'image' :img_url,
                                        'description':woo_categ.description
                                        }}
                
                res =wcapi.put('products/categories/%s'%(woo_categ.woo_categ_id),data)
                if not isinstance(res,requests.models.Response):
                    transaction_log_obj.create(
                                                {'message':"Response is not in proper format,Please Check Details",
                                                 'mismatch_details':True,
                                                 'type':'category',
                                                 'woo_instance_id':instance.id
                                                })
                    continue
                response = res.json()
                if not isinstance(response, dict):
                    transaction_log_obj.create(
                                                {'message':"Response is not in proper format,Please Check Details",
                                                 'mismatch_details':True,
                                                 'type':'category',
                                                 'woo_instance_id':instance.id
                                                })
                    continue                
                errors = response.get('errors','')
                if errors:
                    message = errors[0].get('message')
                    transaction_log_obj.create(
                                                {'message':message,
                                                 'mismatch_details':True,
                                                 'type':'category',
                                                 'woo_instance_id':instance.id
                                                })
                    continue                
                else:
                    if instance.is_image_url:
                        updateed_product_category = response.get('product_category')
                        res_image = updateed_product_category.get('image','')                
                        res_image and woo_categ.write({'response_url':res_image})
                    updated_categs.append(woo_categ.id)
        return True

    def import_all_categories(self,wcapi,instance,transaction_log_obj,page):
        res=wcapi.get('products/categories?page=%s'%(page))
        response = res.json()
        errors = response.get('errors','')
        if errors:
            message = errors[0].get('message')
            transaction_log_obj.create(
                                        {'message':message,
                                         'mismatch_details':True,
                                         'type':'category',
                                         'woo_instance_id':instance.id
                                        })
            return []
        return response.get('product_categories')
    
    @api.multi
    def create_or_update_woo_categ(self,wcapi,instance,woo_product_categ_name):
        woo_categ = False
        categ_name_list=[]
        product_categ_ids=[]
        wcapi = instance.connect_in_woo()
        categ_res=wcapi.get("products/categories?fields=id,name,parent")
        categ_response = categ_res.json()
        product_categories = categ_response.get('product_categories')
        categ=filter(lambda categ: categ['name'].lower() == woo_product_categ_name.lower(), product_categories)
        if categ:
            categ=categ[0]
            product_categ_ids.append(categ.get('id'))
            categ_name_list.append(woo_product_categ_name.lower())
        for product_categ_id in product_categ_ids:
            tmp_categ=filter(lambda categ1: categ1['id'] == product_categ_id, product_categories)
            if tmp_categ:
                tmp_categ=tmp_categ[0]
                if tmp_categ.get('parent') and tmp_categ.get('parent') not in product_categ_ids:
                    product_categ_ids.append(tmp_categ.get('parent'))
                    tmp_parent_categ=filter(lambda categ2: categ2['id'] == tmp_categ.get('parent'), product_categories)[0]
                    categ_name_list.append(tmp_parent_categ.get('name').lower())
                    
        product_categ_ids.reverse()
        for product_categ_id in product_categ_ids:
            response=wcapi.get("products/categories/%s"%(product_categ_id)).json()
            categ=response.get('product_category')
            product_category={'id':categ.get('id'),'name':categ.get('name')}
            categ_name = product_category.get('name')
            if categ_name.lower() in categ_name_list:                
                single_catg_res = wcapi.get("products/categories/%s"%(product_category.get('id')))
                single_catg_response = single_catg_res.json()
                single_catg = single_catg_response.get('product_category')
                parent_woo_id = single_catg.get('parent')
                parent_id=False
                binary_img_data = False
                if parent_woo_id:
                    parent_id=self.search([('woo_categ_id','=',parent_woo_id),('woo_instance_id','=',instance.id)]).id
                vals= {'name':categ_name,'woo_instance_id':instance.id,'parent_id':parent_id,'woo_categ_id':product_category.get('id'),'display':single_catg.get('display'),'exported_in_woo':True,'description':single_catg.get('description','')}
                res_image = single_catg.get('image','')
                if instance.is_image_url:                                    
                    res_image and vals.update({'response_url':res_image})
                else:
                    if res_image:
                        try:
                            res_img = requests.get(res_image,stream=True,verify=False,timeout=10)
                            if res_img.status_code == 200:
                                binary_img_data = base64.b64encode(res_img.content)                                                                                       
                        except Exception:
                            pass
                    binary_img_data and vals.update({'image':binary_img_data})
                ctg = categ_name.lower().replace('\'','\'\'')                     
                self._cr.execute("select id from woo_product_categ_ept where LOWER(name) = '%s' and woo_instance_id = %s limit 1"%(ctg,instance.id))
                woo_product_categ_id = self._cr.dictfetchall()            
                if woo_product_categ_id:
                    woo_categ = self.browse(woo_product_categ_id[0].get('id'))                    
                    woo_categ.write(vals)                    
                else:                    
                    woo_categ = self.create(vals)                
        return woo_categ
    
    @api.multi
    def sync_product_category(self,instance,woo_product_categ=False,woo_product_categ_name=False):
        transaction_log_obj=self.env["woo.transaction.log"]
        wcapi = instance.connect_in_woo()
        if woo_product_categ and woo_product_categ.exported_in_woo:
            res = wcapi.get("products/categories/%s"%(woo_product_categ.woo_categ_id))
            if res.status_code == 404:
                self.export_product_categs(instance, [woo_product_categ])
                return True
        elif woo_product_categ and not woo_product_categ.exported_in_woo:
            woo_categ= self.create_or_update_woo_categ(wcapi,instance,woo_product_categ.name)
            if woo_categ:
                return woo_categ
            else:
                self.export_product_categs(instance, [woo_product_categ])
                return True
        elif not woo_product_categ and woo_product_categ_name:
            woo_categ= self.create_or_update_woo_categ(wcapi,instance,woo_product_categ_name)
            return woo_categ                                  
        else:
            res = wcapi.get("products/categories")
            
        total_pages = res and res.headers.get('X-WC-TotalPages') or 1
        res = res.json()
        errors = res.get('errors','')
        if errors:
            message = errors[0].get('message')
            transaction_log_obj.create(
                                        {'message':message,
                                         'mismatch_details':True,
                                         'type':'category',
                                         'woo_instance_id':instance.id
                                        })
            return True
        if woo_product_categ:
            response =  res.get('product_category')
            results = [response]
        else:
            results = res.get('product_categories')    
        if total_pages >=2:
            for page in range(2,int(total_pages)+1):            
                results = results + self.import_all_categories(wcapi,instance,transaction_log_obj,page)

        processed_categs=[]
        for res in results:
            if not isinstance(res, dict):
                continue 
            if res.get('id',False) in processed_categs:
                continue
            
            categ_results=[]
            categ_results.append(res)
            for categ_result in categ_results:
                if not isinstance(categ_result, dict):
                    continue
                if categ_result.get('parent'):
                    parent_categ=filter(lambda categ: categ['id'] == categ_result.get('parent'), results)
                    if parent_categ:
                        parent_categ=parent_categ[0]
                    else:
                        response=wcapi.get("products/categories/%s"%(categ_result.get('parent'))).json()
                        parent_categ=response.get('product_category')
                    if parent_categ not in categ_results:
                        categ_results.append(parent_categ)
                    
            categ_results.reverse()
            for result in categ_results:
                if not isinstance(result, dict):
                    continue
                if result.get('id') in processed_categs:
                    continue
                
                woo_categ_id = result.get('id')
                woo_categ_name = result.get('name')
                display = result.get('display')
                parent_woo_id=result.get('parent')
                parent_id=False
                binary_img_data = False
                if parent_woo_id:
                    parent_id=self.search([('woo_categ_id','=',parent_woo_id),('woo_instance_id','=',instance.id)]).id
                vals= {'name':woo_categ_name,'woo_instance_id':instance.id,'display':display,'exported_in_woo':True,'parent_id':parent_id,'description':result.get('description','')}
                res_image = result.get('image','')
                if instance.is_image_url:                                    
                    res_image and vals.update({'response_url':res_image})
                else:
                    if res_image:
                        try:
                            res_img = requests.get(res_image,stream=True,verify=False,timeout=10)
                            if res_img.status_code == 200:
                                binary_img_data = base64.b64encode(res_img.content)                                                                                       
                        except Exception:
                            pass
                    binary_img_data and vals.update({'image':binary_img_data})                                               
                woo_product_categ = self.search([('woo_categ_id','=',woo_categ_id),('woo_instance_id','=',instance.id)])
                if not woo_product_categ:
                    ctg = woo_categ_name.lower().replace('\'','\'\'')                                                           
                    self._cr.execute("select id from woo_product_categ_ept where LOWER(name) = '%s' and woo_instance_id = %s limit 1"%(ctg,instance.id))
                    woo_product_categ_id = self._cr.dictfetchall()
                    if woo_product_categ_id:
                        woo_product_categ = self.browse(woo_product_categ_id[0].get('id'))
                        vals.update({'woo_categ_id':woo_categ_id})
                                    
                if woo_product_categ:                                                     
                    woo_product_categ.write(vals)
                else:
                    vals.update({'woo_categ_id':woo_categ_id})
                    self.create(vals)
                    
                processed_categs.append(result.get('id',False))
        return True            