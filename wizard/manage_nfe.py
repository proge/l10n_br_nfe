# -*- coding: utf-8 -*-

##############################################################################
#                                                                            #
#  Copyright (C) 2012 Proge Informática Ltda (<http://www.proge.com.br>).    #
#                                                                            #
#  Author Daniel Hartmann <daniel@proge.com.br>                              #
#                                                                            #
#  This program is free software: you can redistribute it and/or modify      #
#  it under the terms of the GNU Affero General Public License as            #
#  published by the Free Software Foundation, either version 3 of the        #
#  License, or (at your option) any later version.                           #
#                                                                            #
#  This program is distributed in the hope that it will be useful,           #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of            #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the             #
#  GNU Affero General Public License for more details.                       #
#                                                                            #
#  You should have received a copy of the GNU Affero General Public License  #
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.     #
#                                                                            #
##############################################################################

from osv import fields, osv
from tools.translate import _
import base64
from unicodedata import normalize
import re
import string

from uuid import uuid4
import datetime

from pysped_nfe import ProcessadorNFe
from pysped_nfe.manual_401 import NFe_200, Det_200, Vol_200, Dup_200

NFE_STATUS = {
    'send_ok': 'Transmitida',
    'send_failed': 'Falhou ao transmitir',
    'cancel_ok': 'Cancelada',
    'cancel_failed': 'Falhou ao cancelar',
    'destroy_ok': 'Numeração inutilizada',
    'destroy_failed': 'Falhou ao inutilizar numeração',
    'check_nfe_failed': 'Falhou ao obter situação atual',
    }


class manage_nfe(osv.osv_memory):
    """Manage NF-e

    States:
    - init: wizard just opened
    - down: server is down
    - done: nfe was successfully sent
    - failed: some or all operations failed
    - nothing: nothing to do
    """

    _name = "l10n_br_nfe.manage_nfe"
    _description = "Manage NF-e"
    _inherit = "ir.wizard.screen"
    _columns = {
        'company_id': fields.many2one('res.company', 'Company'),
        'state': fields.selection([('init', 'init'),
                                   ('down', 'down'),
                                   ('done', 'done'),
                                   ('failed', 'failed'),
                                   ('justify_cancel', 'justify_cancel'),
                                   ('justify_destroy', 'justify_destroy'),
                                   ('nothing', 'nothing'),
                                   ], 'state', readonly=True),
        'invoice_status': fields.many2many('account.invoice',
                                           string='Invoice Status',
                                           ),
        'justification': fields.text('Justificativa'),
        }
    _defaults = {
        'state': 'init',
        'company_id': lambda self, cr, uid, c: self.pool.get(
            'res.company'
            )._company_default_get(cr, uid, 'account.invoice', context=c),
        }

    def default_get(self, cr, uid, fields, context=None):
        if context is None:
            context = {}

        data = super(manage_nfe, self).default_get(cr, uid, fields, context)
        active_ids = context.get('active_ids', [])

        invoices = self.pool.get('account.invoice').browse(cr, uid, active_ids,
                                                           context=context
                                                           )
        data.update(invoice_status=[i.id for i in invoices])

        return data

    def _unaccent(self, text):
        return normalize('NFKD', unicode(text)).encode('ASCII', 'ignore')

    def justify_back(self, cr, uid, ids, context=None):
        """Justify NF-e back"""
        self.write(cr, uid, ids, {'state': 'init'})

    def justify_cancel(self, cr, uid, ids, context=None):
        """Justify NF-e cancel"""
        self.write(cr, uid, ids, {'state': 'justify_cancel'})

    def justify_destroy(self, cr, uid, ids, context=None):
        """Justify NF-e number destruction"""
        self.write(cr, uid, ids, {'state': 'justify_destroy'})

    def send_nfe(self, cr, uid, ids, context=None):
        """Send one or many NF-e"""

        sent_invoices = []
        unsent_invoices = []

        #nfe_environment = 1 # produção
        nfe_environment = 2 # homologação

        partner_obj = self.pool.get('res.partner')
        inv_obj = self.pool.get('account.invoice')
        active_ids = context.get('active_ids', [])

        conditions = [('id', 'in', active_ids),
                      ('nfe_status', '<>', NFE_STATUS['send_ok'])]
        invoices_to_send = inv_obj.search(cr, uid, conditions)

        for inv in inv_obj.browse(cr, uid, invoices_to_send, context=context):
            company = self.pool.get('res.company').browse(cr,
                                                          uid,
                                                          [inv.company_id.id]
                                                          )[0]

            company_id_list = [inv.company_id.partner_id.id]
            company_addr = partner_obj.address_get(cr, uid, company_id_list,
                                                   ['default'])
            comp_addr_d = self.pool.get('res.partner.address').browse(
                cr,
                uid,
                [company_addr['default']],
                context={'lang': 'pt_BR'}
                )[0]

            cert_file_content = base64.decodestring(company.nfe_cert_file)

            caminho_temporario = u'/tmp/'
            cert_file = caminho_temporario + uuid4().hex
            arq_tmp = open(cert_file, 'w')
            arq_tmp.write(cert_file_content)
            arq_tmp.close()

            cert_password = company.nfe_cert_password

            p = ProcessadorNFe()
            p.versao = u'2.00'
            p.estado = u'SP'
            p.certificado.arquivo = cert_file
            p.certificado.senha = cert_password
            p.salvar_arquivos = True
            p.contingencia_SCAN = False
            p.caminho = u''

            # Instancia uma NF-e
            n = NFe_200()

            # Identificação da NF-e
            n.infNFe.ide.cUF.valor = comp_addr_d.state_id.ibge_code
            if inv.cfop_ids:
                n.infNFe.ide.natOp.valor = self._unaccent(
                    inv.cfop_ids[0].small_name or ''
                    )

            today = datetime.datetime.now()
            ibge_code = ('%s%s') % (
                comp_addr_d.state_id.ibge_code,
                comp_addr_d.l10n_br_city_id.ibge_code
                )

            n.infNFe.ide.indPag.valor = 2
            n.infNFe.ide.mod.valor = inv.fiscal_document_id.code
            n.infNFe.ide.serie.valor = inv.document_serie_id.code
            n.infNFe.ide.nNF.valor = inv.internal_number or ''
            n.infNFe.ide.dEmi.valor = inv.date_invoice or today
            n.infNFe.ide.dSaiEnt.valor = inv.date_invoice or ''
            n.infNFe.ide.hSaiEnt.valor = ''
            n.infNFe.ide.cMunFG.valor = ibge_code
            n.infNFe.ide.tpImp.valor = 1
            n.infNFe.ide.tpEmis.valor = 1
            n.infNFe.ide.tpAmb.valor = nfe_environment
            n.infNFe.ide.finNFe.valor = 1
            n.infNFe.ide.procEmi.valor = 0
            n.infNFe.ide.verProc.valor = u'2.0.9'
            n.infNFe.ide.dhCont.valor = ''
            n.infNFe.ide.xJust = ''

            if inv.cfop_ids and inv.cfop_ids[0].type in ("input"):
                n.infNFe.ide.tpNF.valor = '0'
            else:
                n.infNFe.ide.tpNF.valor = '1'

            # Emitente
            escaped_punctuation = re.escape(string.punctuation)
            if inv.company_id.partner_id.tipo_pessoa == 'J':
                n.infNFe.emit.CNPJ.valor = re.sub('[%s]' %
                                                  escaped_punctuation,
                                                  '',
                                                  inv.partner_id.cnpj_cpf or ''
                                                  )
            else:
                n.infNFe.emit.CPF.valor = re.sub('[%s]' %
                                                 escaped_punctuation,
                                                 '',
                                                 inv.partner_id.cnpj_cpf or ''
                                                 )

            address_company_bc_code = ''
            if comp_addr_d.country_id.bc_code:
                address_company_bc_code = comp_addr_d.country_id.bc_code[1:]

            n.infNFe.emit.xNome.valor = self._unaccent(
                inv.company_id.partner_id.legal_name or ''
                )
            n.infNFe.emit.xFant.valor = self._unaccent(
                inv.company_id.partner_id.name or ''
                )
            n.infNFe.emit.enderEmit.xLgr.valor = self._unaccent(
                comp_addr_d.street or ''
                )
            n.infNFe.emit.enderEmit.nro.valor = comp_addr_d.number or ''
            n.infNFe.emit.enderEmit.xCpl.valor = self._unaccent(
                comp_addr_d.street2 or ''
                )
            n.infNFe.emit.enderEmit.xBairro.valor = self._unaccent(
                comp_addr_d.district or 'Sem Bairro'
                )
            n.infNFe.emit.enderEmit.cMun.valor = '%s%s' % (
                comp_addr_d.state_id.ibge_code,
                comp_addr_d.l10n_br_city_id.ibge_code
                )
            n.infNFe.emit.enderEmit.xMun.valor = self._unaccent(
                comp_addr_d.l10n_br_city_id.name or ''
                )
            n.infNFe.emit.enderEmit.UF.valor = comp_addr_d.state_id.code or ''
            n.infNFe.emit.enderEmit.CEP.valor = re.sub(
                '[%s]' % escaped_punctuation,
                '',
                str(comp_addr_d.zip or '').replace(' ', '')
                )
            n.infNFe.emit.enderEmit.cPais.valor = address_company_bc_code or ''
            n.infNFe.emit.enderEmit.xPais.valor = self._unaccent(
                comp_addr_d.country_id.name or ''
                )
            n.infNFe.emit.enderEmit.fone.valor = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                str(comp_addr_d.phone or '').replace(' ', '')
                )
            n.infNFe.emit.IE.valor = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                inv.company_id.partner_id.inscr_est or ''
                )
            n.infNFe.emit.IEST = ''
            n.infNFe.emit.IM = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                inv.company_id.partner_id.inscr_mun or ''
                )
            n.infNFe.emit.CNAE = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                inv.company_id.cnae_main_id.code or ''
                )

            # Regime tributário
            n.infNFe.emit.CRT = inv.company_id.fiscal_type or ''

            # FIXME: check if it works whithout this stuff
            '''
            TODO: - Verificar, pois quando e informado do CNAE ele exige que
                a inscricao municipal, parece um bug do emissor da NFE
            '''
            #if not inv.company_id.partner_id.inscr_mun:
            #    n.infNFe.emit.CNAE = ''

            # Destinatário
            if nfe_environment == 2:
                n.infNFe.dest.xNome.valor = 'NF-E EMITIDA EM AMBIENTE DE ' + \
                    'HOMOLOGACAO - SEM VALOR FISCAL'
            else:
                n.infNFe.dest.xNome.valor = self._unaccent(
                    inv.partner_id.legal_name or ''
                    )

            if inv.partner_id.tipo_pessoa == 'J':
                n.infNFe.dest.CNPJ.valor = re.sub(
                    '[%s]' % re.escape(string.punctuation),
                    '',
                    inv.partner_id.cnpj_cpf or ''
                    )
            else:
                n.infNFe.dest.CPF.valor = re.sub(
                    '[%s]' % re.escape(string.punctuation),
                    '',
                    inv.partner_id.cnpj_cpf or ''
                    )

            address_invoice_bc_code = ''
            if inv.address_invoice_id.country_id.bc_code:
                address_invoice_bc_code = \
                    inv.address_invoice_id.country_id.bc_code[1:]

            n.infNFe.dest.enderDest.xLgr.valor = self._unaccent(
                inv.address_invoice_id.street or ''
                )
            n.infNFe.dest.enderDest.nro.valor = self._unaccent(
                inv.address_invoice_id.number or ''
                )
            n.infNFe.dest.enderDest.xCpl.valor = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                self._unaccent(inv.address_invoice_id.street2 or '')
                )
            n.infNFe.dest.enderDest.xBairro.valor = self._unaccent(
                inv.address_invoice_id.district or 'Sem Bairro'
                )
            n.infNFe.dest.enderDest.cMun.valor = ('%s%s') % (
                inv.address_invoice_id.state_id.ibge_code,
                inv.address_invoice_id.l10n_br_city_id.ibge_code
                )
            n.infNFe.dest.enderDest.xMun.valor = self._unaccent(
                inv.address_invoice_id.l10n_br_city_id.name or ''
                )
            n.infNFe.dest.enderDest.UF.valor = \
                inv.address_invoice_id.state_id.code
            n.infNFe.dest.enderDest.CEP.valor = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                str(inv.address_invoice_id.zip or '').replace(' ', '')
                )
            n.infNFe.dest.enderDest.cPais.valor = address_invoice_bc_code
            n.infNFe.dest.enderDest.xPais.valor = self._unaccent(
                inv.address_invoice_id.country_id.name or ''
                )
            n.infNFe.dest.enderDest.fone.valor = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                str(inv.address_invoice_id.phone or '').replace(' ', '')
                )
            n.infNFe.dest.IE.valor = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                inv.partner_id.inscr_est or ''
                )
            n.infNFe.dest.email.valor = inv.partner_id.email or ''

            if inv.partner_shipping_id and \
                inv.address_invoice_id != inv.partner_shipping_id:

                n.infNFe.entrega.xLgr = self._unaccent(
                    inv.partner_shipping_id.street or ''
                    )
                n.infNFe.entrega.nro = self._unaccent(
                    inv.partner_shipping_id.number or ''
                    )
                n.infNFe.entrega.xCpl = re.sub(
                    '[%s]' % re.escape(string.punctuation),
                    '',
                    self._unaccent(inv.partner_shipping_id.street2 or '')
                    )
                n.infNFe.entrega.xBairro = re.sub(
                    '[%s]' % re.escape(string.punctuation),
                    '',
                    self._unaccent(inv.partner_shipping_id.district or \
                                   'Sem Bairro')
                    )
                n.infNFe.entrega.cMun = ('%s%s') % (
                    inv.partner_shipping_id.state_id.ibge_code,
                    inv.partner_shipping_id.l10n_br_city_id.ibge_code
                    )
                n.infNFe.entrega.xMun = self._unaccent(
                    inv.partner_shipping_id.l10n_br_city_id.name or ''
                    )
                n.infNFe.entrega.UF = inv.address_invoice_id.state_id.code

                if inv.partner_id.tipo_pessoa == 'J':
                    n.infNFe.entrega.CNPJ.valor = re.sub(
                        '[%s]' % re.escape(string.punctuation),
                        '',
                        inv.partner_id.cnpj_cpf or ''
                        )
                else:
                    n.infNFe.entrega.CPF.valor = re.sub(
                        '[%s]' % re.escape(string.punctuation),
                        '',
                        inv.partner_id.cnpj_cpf or ''
                        )

            i = 0
            for inv_line in inv.invoice_line:
                i += 1

                # Detalhe
                d = Det_200()

                d.nItem.valor = 1

                product_obj = inv_line.product_id

                if inv_line.product_id.code:
                    d.prod.cProd.valor = inv_line.product_id.code
                else:
                    d.prod.cProd.valor = unicode(i).strip().rjust(4, u'0')

                d.prod.cEAN.valor = inv_line.product_id.ean13 or ''
                d.prod.xProd.valor = self._unaccent(
                    inv_line.product_id.name or ''
                    )

                if product_obj.property_fiscal_classification:
                    c_name = product_obj.property_fiscal_classification.name \
                        or ''
                else:
                    c_name = ''

                d.prod.NCM.valor = re.sub(
                    '[%s]' % re.escape(string.punctuation), '', c_name
                    )
                d.prod.EXTIPI.valor = u''
                d.prod.CFOP.valor = inv_line.cfop_id.code
                d.prod.uCom.valor = self._unaccent(inv_line.uos_id.name or '')
                d.prod.qCom.valor = str("%.4f" % inv_line.quantity)
                d.prod.vUnCom.valor = str("%.2f" % (
                    inv_line.price_unit * \
                    (1 - (inv_line.discount or 0.0) / 100.0))
                    )
                d.prod.vProd.valor = str("%.2f" % inv_line.price_total)
                d.prod.cEANTrib.valor = inv_line.product_id.ean13 or ''
                d.prod.uTrib.valor = inv_line.uos_id.name
                d.prod.qTrib.valor = str("%.4f" % inv_line.quantity)
                d.prod.vUnTrib.valor = str("%.2f" % inv_line.price_unit)
                d.prod.vFrete.valor = u'0.00'
                d.prod.vSeg.valor = u'0.00'
                d.prod.vDesc.valor = u'0.00'
                d.prod.vOutro.valor = u'0.00'
                d.prod.indTot.valor = 1
                d.prod.xPed.valor = ''
                d.prod.nItemPed.valor = ''

                # Produto entra no total da NF-e
                d.prod.indTot.valor = 1

                if inv_line.icms_cst in ('00'):
                    d.imposto.ICMS.orig.valor = product_obj.origin or '0'
                    d.imposto.ICMS.CST.valor = inv_line.icms_cst
                    d.imposto.ICMS.modBC.valor = 0
                    d.imposto.ICMS.vBC.valor = str(
                        "%.2f" % inv_line.icms_base
                        )
                    d.imposto.ICMS.pICMS.valor = str(
                        "%.2f" % inv_line.icms_percent
                        )
                    d.imposto.ICMS.vICMS.valor = str(
                        "%.2f" % inv_line.icms_value
                        )

                if inv_line.icms_cst in ('20'):
                    d.imposto.ICMS.orig.valor = product_obj.origin or '0'
                    d.imposto.ICMS.CST.valor = inv_line.icms_cst
                    d.imposto.ICMS.modBC.valor = 0
                    d.imposto.ICMS.pRedBCST.valor = str(
                        "%.2f" % inv_line.icms_percent_reduction
                        )
                    d.imposto.ICMS.vBC.valor = str("%.2f" % inv_line.icms_base)
                    d.imposto.ICMS.pICMS.valor = str(
                        "%.2f" % inv_line.icms_percent
                        )
                    d.imposto.ICMS.vICMS.valor = str(
                        "%.2f" % inv_line.icms_value
                        )

                if inv_line.icms_cst in ('10'):
                    d.imposto.ICMS.orig.valor = product_obj.origin or '0'
                    d.imposto.ICMS.CST.valor = inv_line.icms_cst
                    d.imposto.ICMS.modBC.valor = '0'
                    d.imposto.ICMS.vBC.valor = str("%.2f" % inv_line.icms_base)
                    d.imposto.ICMS.pICMS.valor = str(
                        "%.2f" % inv_line.icms_percent
                        )
                    d.imposto.ICMS.vICMS.valor = str(
                        "%.2f" % inv_line.icms_value
                        )
                    d.imposto.ICMS.modBCST.valor = '4' # TODO
                    d.imposto.ICMS.pMVAST.valor = str(
                        "%.2f" % inv_line.icms_st_mva
                        ) or ''
                    d.imposto.ICMS.pRedBCST.valor = ''
                    d.imposto.ICMS.vBCST.valor = str(
                        "%.2f" % inv_line.icms_st_base
                        )
                    d.imposto.ICMS.pICMSST.valor = str(
                        "%.2f" % inv_line.icms_st_percent
                        )
                    d.imposto.ICMS.vICMSST.valor = str(
                        "%.2f" % inv_line.icms_st_value
                        )

                if inv_line.icms_cst in ('40', '41', '50', '51'):
                    d.imposto.ICMS.orig.valor = product_obj.origin or '0'
                    d.imposto.ICMS.CST.valor = inv_line.icms_cst
                    d.imposto.ICMS.vICMS.valor = str(
                        "%.2f" % inv_line.icms_value
                        )
                    d.imposto.ICMS.motDesICMS.valor = '9' # TODO

                if inv_line.icms_cst in ('60'):
                    d.imposto.ICMS.orig.valor = product_obj.origin or '0'
                    d.imposto.ICMS.CST.valor = inv_line.icms_cst
                    d.imposto.ICMS.vBCST.valor = str("%.2f" % 0.00)
                    d.imposto.ICMS.vICMSST.valor = str("%.2f" % 0.00)

                if inv_line.icms_cst in ('70'):
                    d.imposto.ICMS.orig.valor = product_obj.origin or '0'
                    d.imposto.ICMS.CST.valor = inv_line.icms_cst
                    d.imposto.ICMS.modBC.valor = '0'
                    d.imposto.ICMS.pRedBC.valor = str(
                        "%.2f" % inv_line.icms_percent_reduction
                        )
                    d.imposto.ICMS.vBC.valor = str(
                        "%.2f" % inv_line.icms_base
                        )
                    d.imposto.ICMS.pICMS.valor = str(
                        "%.2f" % inv_line.icms_percent
                        )
                    d.imposto.ICMS.vICMS.valor = str(
                        "%.2f" % inv_line.icms_value
                        )
                    d.imposto.ICMS.modBCST.valor = '4' # TODO
                    d.imposto.ICMS.pMVAST.valor = str(
                        "%.2f" % inv_line.icms_st_mva
                        ) or ''
                    d.imposto.ICMS.pRedBCST.valor = ''
                    d.imposto.ICMS.vBCST.valor = str(
                        "%.2f" % inv_line.icms_st_base
                        )
                    d.imposto.ICMS.pICMSST.valor = str(
                        "%.2f" % inv_line.icms_st_percent
                        )
                    d.imposto.ICMS.vICMSST.valor = str(
                        "%.2f" % inv_line.icms_st_value
                        )

                if inv_line.icms_cst in ('90', '900'):
                    d.imposto.ICMS.orig.valor = product_obj.origin or '0'
                    d.imposto.ICMS.CSOSN.valor = inv_line.icms_cst
                    d.imposto.ICMS.modBC.valor = '0'
                    d.imposto.ICMS.vBC.valor = str("%.2f" % 0.00)
                    d.imposto.ICMS.pRedBC.valor = ''
                    d.imposto.ICMS.pICMS.valor = str("%.2f" % 0.00)
                    d.imposto.ICMS.vICMS.valor = str("%.2f" % 0.00)
                    d.imposto.ICMS.modBCST.valor = ''
                    d.imposto.ICMS.pMVAST.valor = ''
                    d.imposto.ICMS.pRedBCST.valor = ''
                    d.imposto.ICMS.vBCST.valor = ''
                    d.imposto.ICMS.pICMSST.valor = ''
                    d.imposto.ICMS.vICMSST.valor = ''
                    d.imposto.ICMS.pCredSN.valor = str("%.2f" % 0.00)
                    d.imposto.ICMS.vCredICMSSN.valor = str("%.2f" % 0.00)

                d.imposto.IPI.clEnq.valor = ''
                d.imposto.IPI.CNPJProd.valor = ''
                d.imposto.IPI.cSelo.valor = ''
                d.imposto.IPI.qSelo.valor = ''
                d.imposto.IPI.cEnq.valor = '999'

                if inv_line.ipi_cst in ('50', '51', '52') and \
                        inv_line.ipi_percent > 0:

                    d.imposto.IPI.CST.valor = inv_line.ipi_cst
                    d.imposto.IPI.vIPI.valor = str("%.2f" % inv_line.ipi_value)

                    if inv_line.ipi_type == 'percent' or '':
                        d.imposto.IPI.vBC.valor = str(
                            "%.2f" % inv_line.ipi_base
                            )
                        d.imposto.IPI.pIPI.valor = str(
                            "%.2f" % inv_line.ipi_percent
                            )

                    if inv_line.ipi_type == 'quantity':
                        pesol = 0
                        if inv_line.product_id:
                            pesol = inv_line.product_id.weight_net
                        d.imposto.IPI.qUnid.valor = str(
                            "%.4f" % (inv_line.quantity * pesol)
                            )
                        d.imposto.IPI.vUnid.valor = str(
                            "%.4f" % inv_line.ipi_percent
                            )

                if inv_line.ipi_cst in ('99'):
                    d.imposto.IPI.CST.valor = inv_line.ipi_cst
                    d.imposto.IPI.vIPI.valor = str("%.2f" % inv_line.ipi_value)
                    d.imposto.IPI.vBC.valor = str("%.2f" % inv_line.ipi_base)
                    d.imposto.IPI.pIPI.valor = str(
                        "%.2f" % inv_line.ipi_percent
                        )

                if inv_line.pis_cst in ('01') and inv_line.pis_percent > 0:
                    d.imposto.PIS.CST.valor = inv_line.pis_cst
                    d.imposto.PIS.vBC.valor = str("%.2f" % inv_line.pis_base)
                    d.imposto.PIS.vPIS.valor = str("%.2f" % inv_line.pis_value)
                    d.imposto.PIS.pPIS.valor = str(
                        "%.2f" % inv_line.pis_percent
                        )

                if inv_line.pis_cst in ('99'):
                    d.imposto.PIS.CST.valor = inv_line.pis_cst
                    d.imposto.PIS.vPIS.valor = str("%.2f" % inv_line.pis_value)
                    d.imposto.PIS.vBC.valor = str("%.2f" % inv_line.pis_base)
                    d.imposto.PIS.pPIS.valor = str(
                        "%.2f" % inv_line.pis_percent
                        )

                if inv_line.cofins_cst in ('01') and \
                        inv_line.cofins_percent > 0:
                    d.imposto.COFINS.CST.valor = inv_line.cofins_cst
                    d.imposto.COFINS.vBC.valor = str(
                        "%.2f" % inv_line.cofins_base
                        )
                    d.imposto.COFINS.pCOFINS.valor = str(
                        "%.2f" % inv_line.cofins_percent
                        )
                    d.imposto.COFINS.vCOFINS.valor = str(
                        "%.2f" % inv_line.cofins_value
                        )

                if inv_line.cofins_cst in ('99'):
                    d.imposto.COFINS.CST.valor = inv_line.cofins_cst
                    d.imposto.COFINS.vCOFINS.valor = str(
                        "%.2f" % inv_line.cofins_value
                        )
                    d.imposto.COFINS.vBC.valor = str(
                        "%.2f" % inv_line.cofins_base
                        )
                    d.imposto.COFINS.pCOFINS.valor = str(
                        "%.2f" % inv_line.cofins_percent
                        )

                # Inclui o detalhe na NF-e
                n.infNFe.det.append(d)

            # Totais
            n.infNFe.total.ICMSTot.vBC.valor = str("%.2f" % inv.icms_base)
            n.infNFe.total.ICMSTot.vICMS.valor = str("%.2f" % inv.icms_value)
            n.infNFe.total.ICMSTot.vBCST.valor = str("%.2f" % inv.icms_st_base)
            n.infNFe.total.ICMSTot.vST.valor = str("%.2f" % inv.icms_st_value)
            n.infNFe.total.ICMSTot.vProd.valor = str(
                "%.2f" % inv.amount_untaxed
                )
            n.infNFe.total.ICMSTot.vFrete.valor = str(
                "%.2f" % inv.amount_freight
                )
            n.infNFe.total.ICMSTot.vSeg.valor = str(
                "%.2f" % inv.amount_insurance
                )
            n.infNFe.total.ICMSTot.vDesc.valor = '0.00'
            n.infNFe.total.ICMSTot.vII.valor = '0.00'
            n.infNFe.total.ICMSTot.vIPI.valor = str("%.2f" % inv.ipi_value)
            n.infNFe.total.ICMSTot.vPIS.valor = str("%.2f" % inv.pis_value)
            n.infNFe.total.ICMSTot.vCOFINS.valor = str(
                "%.2f" % inv.cofins_value
                )
            n.infNFe.total.ICMSTot.vOutro.valor = str(
                "%.2f" % inv.amount_costs
                )
            n.infNFe.total.ICMSTot.vNF.valor = str("%.2f" % inv.amount_total)

            if inv.carrier_id:

                # Endereço da transportadora
                partner_address_obj = self.pool.get('res.partner.address')

                carrier_addr = partner_obj.address_get(
                    cr, uid, [inv.carrier_id.partner_id.id], ['default']
                    )
                carrier_addr_default = partner_address_obj.browse(
                    cr, uid, [carrier_addr['default']]
                    )[0]

                if inv.carrier_id.partner_id.legal_name:
                    n.infNFe.transp.xNome.valor = self._unaccent(
                        inv.carrier_id.partner_id.legal_name or ''
                        )
                else:
                    n.infNFe.transp.xNome.valor = self._unaccent(
                        inv.carrier_id.partner_id.name or ''
                        )

                n.infNFe.transp.IE.valor = \
                    inv.carrier_id.partner_id.inscr_est or ''
                n.infNFe.transp.xEnder.valor = self._unaccent(
                    carrier_addr_default.street or ''
                    )
                n.infNFe.transp.UF.valor = \
                    carrier_addr_default.state_id.code or ''

                if carrier_addr_default.l10n_br_city_id:
                    n.infNFe.transp.xMun.valor = self._unaccent(
                        carrier_addr_default.l10n_br_city_id.name or ''
                        )

                if inv.carrier_id.partner_id.tipo_pessoa == 'J':
                    n.infNFe.transp.transporta.CNPJ = re.sub(
                        '[%s]' % re.escape(string.punctuation),
                        '',
                        inv.carrier_id.partner_id.cnpj_cpf or ''
                        )
                else:
                    n.infNFe.transp.transporta.CPF = re.sub(
                        '[%s]' % re.escape(string.punctuation),
                        '',
                        inv.carrier_id.partner_id.cnpj_cpf or ''
                        )

            if inv.vehicle_id:
                n.infNFe.transp.veicTransp.placa.valor = \
                    inv.vehicle_id.plate or ''
                n.infNFe.transp.veicTransp.UF.valor = \
                    inv.vehicle_id.plate.state_id.code or ''
                n.infNFe.transp.veicTransp.RNTC.valor = \
                    inv.vehicle_id.rntc_code or ''

            if not inv.number_of_packages:
                vol = Vol_200()
                vol.qVol.valor = inv.number_of_packages
                vol.esp.valor = 'Volume' # TODO
                #n.infNFe.transp.vol.marca.valor # TODO
                #n.infNFe.transp.vol.nVol.valor # TODO
                vol.pesoL.valor = str("%.3f" % inv.weight_net)
                vol.pesoB.valor = str("%.3f" % inv.weight)
                n.infNFe.transp.vol.append(vol)

            if inv.journal_id.revenue_expense:
                for line in inv.move_line_receivable_id:
                    dup = Dup_200()
                    dup.nDup.valor = line.name
                    dup.dVenc.valor = line.date_maturity or inv.date_due or \
                        inv.date_invoice
                    dup.vDup.valor = str("%.2f" % line.debit)

                    n.infNFe.cobr.dup.append(dup)

            n.infNFe.infAdic.infAdFisco.valor = ''
            n.infNFe.infAdic.infCpl.valor = self._unaccent(inv.comment or '')

            # O retorno de cada webservice é um dicionário
            # estruturado da seguinte maneira:
            # { TIPO_DO_WS_EXECUTADO: {
            #       u'envio'   : InstanciaDaMensagemDeEnvio,
            #       u'resposta': InstanciaDaMensagemDeResposta,
            #       }
            # }
            for processo in p.processar_notas([n]):
                #print processo.envio.xml
                #print processo.resposta.xml
                break

            code, title, content = 404, 'Not found', ''

            # FIXME: check result instead of code
            if code == 200:
                sent_invoices.append(inv.id)

                data = {'nfe_status': NFE_STATUS['send_ok']}
            else:
                unsent_invoices.append(inv.id)

                data = {
                    'nfe_status': NFE_STATUS['send_failed'],
                    'nfe_retorno': processo.resposta.reason,
                    }

            self.pool.get('account.invoice').write(cr,
                                                   uid,
                                                   inv.id,
                                                   data,
                                                   context=context
                                                   )

        if len(sent_invoices) == 0 and len(unsent_invoices) == 0:
            result = {'state': 'nothing'}
        elif len(unsent_invoices) > 0:
            result = {'state': 'failed'}
        else:
            result = {'state': 'done'}

        self.write(cr, uid, ids, result)

        return True

    def cancel_nfe(self, cr, uid, ids, context=None):
        """Cancel one or many NF-e"""

        canceled_invoices = []
        failed_invoices = []

        inv_obj = self.pool.get('account.invoice')
        active_ids = context.get('active_ids', [])
        data = self.read(cr, uid, ids, [], context=context)[0]
        justification = data['justification'][:255]

        conditions = [('id', 'in', active_ids),
                      ('nfe_status', '=', NFE_STATUS['send_ok']),
                      ('nfe_access_key', '<>', '')]
        invoices_to_cancel = inv_obj.search(cr, uid, conditions)

        for inv in inv_obj.browse(cr, uid, invoices_to_cancel,
                                  context=context):
            company = self.pool.get('res.company').browse(cr,
                                                          uid,
                                                          [inv.company_id.id]
                                                          )[0]

            cert_file_content = base64.decodestring(company.nfe_cert_file)

            caminho_temporario = u'/tmp/'
            cert_file = caminho_temporario + uuid4().hex
            arq_tmp = open(cert_file, 'w')
            arq_tmp.write(cert_file_content)
            arq_tmp.close()

            cert_password = company.nfe_cert_password

            p = ProcessadorNFe()
            p.versao = u'2.00'
            p.estado = u'SP'
            p.certificado.arquivo = cert_file
            p.certificado.senha = cert_password
            p.salvar_arquivos = True
            p.contingencia_SCAN = False
            p.caminho = u''
            p.ambiente = 2

            partner_obj = self.pool.get('res.partner')
            company_id_list = [inv.company_id.partner_id.id]
            company_addr = partner_obj.address_get(cr, uid, company_id_list,
                                                   ['default'])
            comp_addr_d = self.pool.get('res.partner.address').browse(
                cr,
                uid,
                [company_addr['default']],
                context={'lang': 'pt_BR'}
                )[0]

            today = datetime.datetime.now()

            n = NFe_200()
            n.infNFe.ide.cUF = comp_addr_d.state_id.ibge_code
            n.infNFe.ide.dEmi.valor = inv.date_invoice or today
            n.infNFe.emit.CNPJ.valor = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                inv.company_id.partner_id.cnpj_cpf or ''
                )
            n.infNFe.ide.serie.valor = inv.document_serie_id.code
            n.infNFe.ide.nNF.valor = inv.internal_number or ''
            n.infNFe.ide.tpEmis.valor = 1
            n.monta_chave()

            # O retorno de cada webservice é um dicionário
            # estruturado da seguinte maneira:
            # { TIPO_DO_WS_EXECUTADO: {
            #       u'envio'   : InstanciaDaMensagemDeEnvio,
            #       u'resposta': InstanciaDaMensagemDeResposta,
            #       }
            # }
            process = p.cancelar_nota(
                chave_nfe=n.chave,
                # FIXME: é necessário um número de protocolo?
                #numero_protocolo=u'135100018751878',
                justificativa=justification
                )

            code, title, content = 403, 'Gone', ''

            # FIXME: check result instead of code
            if code == 200:
                canceled_invoices.append(inv.id)

                data = {'nfe_status': NFE_STATUS['cancel_ok']}

            else:
                failed_invoices.append(inv.id)

                data = {'nfe_status': NFE_STATUS['cancel_failed']}

            data['nfe_retorno'] = process.resposta.reason
            self.pool.get('account.invoice').write(cr,
                                                   uid,
                                                   inv.id,
                                                   data,
                                                   context=context
                                                   )

        if len(canceled_invoices) == 0 and len(failed_invoices) == 0:
            result = {'state': 'nothing'}
        elif len(failed_invoices) > 0:
            result = {'state': 'failed'}
        else:
            result = {'state': 'done'}

        self.write(cr, uid, ids, result)

        return True

    def destroy_nfe_number(self, cr, uid, ids, context=None):
        """Destroy NF-e number"""

        destroyed_invoices = []
        failed_invoices = []

        inv_obj = self.pool.get('account.invoice')
        active_ids = context.get('active_ids', [])
        data = self.read(cr, uid, ids, [], context=context)[0]
        justification = data['justification'][:255]

        conditions = [('id', 'in', active_ids),
                      ('nfe_status', '=', NFE_STATUS['send_ok'])]
        invoices_to_cancel = inv_obj.search(cr, uid, conditions)

        for inv in inv_obj.browse(cr, uid, invoices_to_cancel,
                                  context=context):
            company = self.pool.get('res.company').browse(cr,
                                                          uid,
                                                          [inv.company_id.id]
                                                          )[0]

            cert_file_content = base64.decodestring(company.nfe_cert_file)

            caminho_temporario = u'/tmp/'
            cert_file = caminho_temporario + uuid4().hex
            arq_tmp = open(cert_file, 'w')
            arq_tmp.write(cert_file_content)
            arq_tmp.close()

            cert_password = company.nfe_cert_password

            p = ProcessadorNFe()
            p.versao = u'2.00'
            p.estado = u'SP'
            p.certificado.arquivo = cert_file
            p.certificado.senha = cert_password
            p.salvar_arquivos = True
            p.contingencia_SCAN = False
            p.caminho = u''

            #
            # O retorno de cada webservice é um dicionário
            # estruturado da seguinte maneira:
            # { TIPO_DO_WS_EXECUTADO: {
            #       u'envio'   : InstanciaDaMensagemDeEnvio,
            #       u'resposta': InstanciaDaMensagemDeResposta,
            #       }
            # }
            #
            process = p.inutilizar_nota(
                cnpj=re.sub(
                    '[%s]' % re.escape(string.punctuation),
                    '',
                    inv.company_id.partner_id.cnpj_cpf or ''
                    ),
                serie=inv.document_serie_id.code,
                numero_inicial=inv.internal_number,
                justificativa=justification
                )

            code, title, content = 403, 'Gone', ''

            # FIXME: check result instead of code
            if code == 200:
                destroyed_invoices.append(inv.id)

                data = {'nfe_status': NFE_STATUS['destroy_ok']}

            else:
                failed_invoices.append(inv.id)

                data = {'nfe_status': NFE_STATUS['destroy_failed']}

            data['nfe_retorno'] = process.resposta.reason
            self.pool.get('account.invoice').write(cr,
                                                   uid,
                                                   inv.id,
                                                   data,
                                                   context=context
                                                   )

        if len(destroyed_invoices) == 0 and len(failed_invoices) == 0:
            result = {'state': 'nothing'}
        elif len(failed_invoices) > 0:
            result = {'state': 'failed'}
        else:
            result = {'state': 'done'}

        self.write(cr, uid, ids, result)

        return True

    def check_nfe_status(self, cr, uid, ids, context=None):
        """Check NF-e status"""
        inv_obj = self.pool.get('account.invoice')
        active_ids = context.get('active_ids', [])
        failed = False
        today = datetime.datetime.now()

        for inv in inv_obj.browse(cr, uid, active_ids,
                                  context=context):

            company = self.pool.get('res.company'
                                    ).browse(cr,
                                             uid,
                                             [inv.company_id.id]
                                             )[0]

            cert_file_content = base64.decodestring(company.nfe_cert_file)

            caminho_temporario = u'/tmp/'
            cert_file = caminho_temporario + uuid4().hex
            arq_tmp = open(cert_file, 'w')
            arq_tmp.write(cert_file_content)
            arq_tmp.close()

            cert_password = company.nfe_cert_password

            p = ProcessadorNFe()
            p.versao = u'2.00'
            p.estado = u'SP'
            p.certificado.arquivo = cert_file
            p.certificado.senha = cert_password
            p.salvar_arquivos = True
            p.contingencia_SCAN = False
            p.caminho = u''

            partner_obj = self.pool.get('res.partner')
            company_id_list = [inv.company_id.partner_id.id]
            company_addr = partner_obj.address_get(cr, uid, company_id_list,
                                                   ['default'])
            comp_addr_d = self.pool.get('res.partner.address').browse(
                cr,
                uid,
                [company_addr['default']],
                context={'lang': 'pt_BR'}
                )[0]

            n = NFe_200()
            n.infNFe.ide.cUF = comp_addr_d.state_id.ibge_code
            n.infNFe.ide.dEmi.valor = inv.date_invoice or today
            n.infNFe.emit.CNPJ.valor = re.sub(
                '[%s]' % re.escape(string.punctuation),
                '',
                inv.company_id.partner_id.cnpj_cpf or ''
                )
            n.infNFe.ide.serie.valor = inv.document_serie_id.code
            n.infNFe.ide.nNF.valor = inv.internal_number or ''
            n.infNFe.ide.tpEmis.valor = 1
            n.monta_chave()

            # O retorno de cada webservice é um dicionário
            # estruturado da seguinte maneira:
            # { TIPO_DO_WS_EXECUTADO: {
            #       u'envio'   : InstanciaDaMensagemDeEnvio,
            #       u'resposta': InstanciaDaMensagemDeResposta,
            #       }
            # }
            process = p.consultar_nota(chave_nfe=n.chave)

            code, title, content = 403, 'Gone', ''

            # FIXME: check result instead of code
            if code != 200:
                failed = True
                data = {
                    'nfe_retorno': NFE_STATUS['check_nfe_failed'] + ' - ' +
                        str(process.resposta.reason),
                    }

            else:
                # TODO: use server result for nfe_status
                data = {
                    #'nfe_status': process.resposta.xml,
                    'nfe_retorno': process.resposta.reason,
                    }

            self.pool.get('account.invoice').write(cr,
                                                   uid,
                                                   inv.id,
                                                   data,
                                                   context=context
                                                   )

        if failed:
            result = {'state': 'failed'}
        else:
            result = {'state': 'done'}

        self.write(cr, uid, ids, result)

        return True

    def check_service_status(self, cr, uid, ids, context=None):
        """Check service status"""
        company_services_up = []
        company_services_down = []

        inv_obj = self.pool.get('account.invoice')
        active_ids = context.get('active_ids', [])

        for inv in inv_obj.browse(cr, uid, active_ids,
                                  context=context):

            if inv.company_id.id not in company_services_up and \
                inv.company_id.id not in company_services_down:

                company = self.pool.get('res.company'
                                        ).browse(cr,
                                                 uid,
                                                 [inv.company_id.id]
                                                 )[0]

                cert_file_content = base64.decodestring(company.nfe_cert_file)

                caminho_temporario = u'/tmp/'
                cert_file = caminho_temporario + uuid4().hex
                arq_tmp = open(cert_file, 'w')
                arq_tmp.write(cert_file_content)
                arq_tmp.close()

                cert_password = company.nfe_cert_password

                p = ProcessadorNFe()
                p.versao = u'2.00'
                p.estado = u'SP'
                p.certificado.arquivo = cert_file
                p.certificado.senha = cert_password
                p.salvar_arquivos = True
                p.contingencia_SCAN = False
                p.caminho = u''

                # O retorno de cada webservice é um dicionário
                # estruturado da seguinte maneira:
                # { TIPO_DO_WS_EXECUTADO: {
                #       u'envio'   : InstanciaDaMensagemDeEnvio,
                #       u'resposta': InstanciaDaMensagemDeResposta,
                #       }
                # }
                process = p.consultar_servico()

                code, title, content = 403, 'Gone', ''

                # FIXME: check result instead of code
                if code == 200:
                    company_services_up.append(inv.company_id.id)
                else:
                    company_services_down.append(inv.company_id.id)

                data = {'nfe_retorno': process.resposta.reason}
                self.pool.get('account.invoice').write(cr,
                                                       uid,
                                                       inv.id,
                                                       data,
                                                       context=context
                                                       )

        if len(company_services_up) == 0 and len(company_services_down) == 0:
            result = {'state': 'nothing'}
        elif len(company_services_down) > 0:
            result = {'state': 'failed'}
        else:
            result = {'state': 'done'}

        self.write(cr, uid, ids, result)

        return True

manage_nfe()
