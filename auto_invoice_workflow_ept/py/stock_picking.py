from openerp import models,api

class stock_picking(models.Model):    
    _inherit="stock.picking"    
    
    def do_transfer(self, cr, uid, ids, context=None):
        super(stock_picking,self).do_transfer(cr,uid,ids,context=context)
        pickings=self.browse(cr,uid,ids,context)
        account_payment_obj=self.pool.get('account.payment')
        for picking in pickings:
            if picking.sale_id.invoice_status=='invoiced':
                continue
            work_flow_process_record=picking.sale_id and picking.sale_id.auto_workflow_process_id
            if work_flow_process_record and work_flow_process_record.invoice_policy=='delivery' and work_flow_process_record.create_invoice and picking.picking_type_id.code=='outgoing':   
                if work_flow_process_record.create_invoice:
                    picking.sale_id.action_invoice_create()                                                                                        
                if work_flow_process_record.validate_invoice:
                    for invoice in picking.sale_id.invoice_ids:
                        if invoice.state=='draft' and invoice.type=='out_invoice':
                            invoice.signal_workflow('invoice_open')
                            if work_flow_process_record.register_payment:
                                if invoice.residual:
                                    vals={
                                        'journal_id':work_flow_process_record.journal_id.id,
                                        'invoice_ids':[(6,0,[invoice.id])],
                                        'communication':invoice.reference,
                                        'currency_id':invoice.currency_id.id,
                                        'payment_type':'inbound',
                                        'partner_id':invoice.commercial_partner_id.id,
                                        'amount':invoice.residual,
                                        'payment_method_id':work_flow_process_record.journal_id.inbound_payment_method_ids.id,
                                        'partner_type':'customer'
                                        }
                                    new_rec=account_payment_obj.create(vals)
                                    new_rec.post()

        return True