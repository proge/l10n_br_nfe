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
import urllib
import sys

from uuid import uuid4
import datetime

from pysped_nfe import ProcessadorNFe
from pysped_nfe.manual_401 import NFe_200, Det_200
from pysped_nfe.webservices_flags import UF_CODIGO

NFE_STATUS = {
    'send_ok': 'Transmitida',
    'send_failed': 'Falhou ao transmitir',
    'cancel_ok': 'Cancelada',
    'cancel_failed': 'Falhou ao cancelar',
    'destroy_ok': 'Numeração inutilizada',
    'destroy_failed': 'Falhou ao inutilizar numeração',
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
                                   ('nothing', 'nothing'),
                                   ], 'state', readonly=True),
        'invoice_status': fields.many2many('account.invoice',
                                           string='Invoice Status',
                                           ),
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

    def send_nfe(self, cr, uid, ids, context=None):
        """Send one or many NF-e"""

        sent_invoices = []
        unsent_invoices = []

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
            n.infNFe.ide.cUF.valor = UF_CODIGO[u'SP']
            n.infNFe.ide.natOp.valor = u'Venda de produto do estabelecimento'
            n.infNFe.ide.indPag.valor = 2
            n.infNFe.ide.serie.valor = 101
            n.infNFe.ide.nNF.valor = 37
            n.infNFe.ide.dEmi.valor = datetime.datetime(2011, 5, 25)
            n.infNFe.ide.dSaiEnt.valor = datetime.datetime(2011, 5, 25)
            n.infNFe.ide.cMunFG.valor = 3513801
            n.infNFe.ide.tpImp.valor = 1
            n.infNFe.ide.tpEmis.valor = 1
            n.infNFe.ide.indPag.valor = 1
            n.infNFe.ide.finNFe.valor = 1
            n.infNFe.ide.procEmi.valor = 0
            n.infNFe.ide.verProc.valor = u'TaugaRS Haveno 1.0'

            # Emitente
            n.infNFe.emit.CNPJ.valor = u'11111111111111'
            n.infNFe.emit.xNome.valor = u'Razao Social Emitente Ltda. EPP'
            n.infNFe.emit.xFant.valor = u'Bromelia'
            n.infNFe.emit.enderEmit.xLgr.valor = u'R. Ibiuna'
            n.infNFe.emit.enderEmit.nro.valor = u'729'
            n.infNFe.emit.enderEmit.xCpl.valor = u'sala 3'
            n.infNFe.emit.enderEmit.xBairro.valor = u'Jd. Guanabara'
            n.infNFe.emit.enderEmit.cMun.valor = u'3552205'
            n.infNFe.emit.enderEmit.xMun.valor = u'Sorocaba'
            n.infNFe.emit.enderEmit.UF.valor = u'SP'
            n.infNFe.emit.enderEmit.CEP.valor = u'18085520'
            n.infNFe.emit.enderEmit.fone.valor = u'1534110602'
            n.infNFe.emit.IE.valor = u'111111111111'
            
            # Regime tributário
            n.infNFe.emit.CRT.valor = u'1'

            # Destinatário
            n.infNFe.dest.CNPJ.valor = u'11143192000101'
            n.infNFe.dest.xNome.valor = u'Razao Social Destinatario Ltda. EPP'
            n.infNFe.dest.enderDest.xLgr.valor = u'R. Ibiuna'
            n.infNFe.dest.enderDest.nro.valor = u'729'
            n.infNFe.dest.enderDest.xCpl.valor = u'sala 3'
            n.infNFe.dest.enderDest.xBairro.valor = u'Jd. Morumbi'
            n.infNFe.dest.enderDest.cMun.valor = u'3552205'
            n.infNFe.dest.enderDest.xMun.valor = u'Sorocaba'
            n.infNFe.dest.enderDest.UF.valor = u'SP'
            n.infNFe.dest.enderDest.CEP.valor = u'18085520'
            n.infNFe.dest.enderDest.fone.valor = u'1534110602'
            n.infNFe.dest.IE.valor = u'795009239110'

            n.infNFe.dest.email.valor = u'user@example.com'

            # Detalhe
            d1 = Det_200()

            d1.nItem.valor = 1
            d1.prod.cProd.valor = u'codigo do produto um'
            d1.prod.cEAN.valor = u''
            d1.prod.xProd.valor = u'Descricao do produto'
            d1.prod.NCM.valor = u'94034000'
            d1.prod.EXTIPI.valor = u''
            d1.prod.CFOP.valor = u'5101'
            d1.prod.uCom.valor = u'UND'
            d1.prod.qCom.valor = u'100.00'
            d1.prod.vUnCom.valor = u'10.0000'
            d1.prod.vProd.valor = u'1000.00'
            d1.prod.cEANTrib.valor = u''
            d1.prod.uTrib.valor = d1.prod.uCom.valor
            d1.prod.qTrib.valor = d1.prod.qCom.valor
            d1.prod.vUnTrib.valor = d1.prod.vUnCom.valor
            d1.prod.vFrete.valor = u'0.00'
            d1.prod.vSeg.valor = u'0.00'
            d1.prod.vDesc.valor = u'0.00'
            d1.prod.vOutro.valor = u'0.00'

            # Produto entra no total da NF-e
            d1.prod.indTot.valor = 1

            # Impostos
            d1.imposto.regime_tributario = 1
            d1.imposto.ICMS.CSOSN.valor = u'400'
            d1.imposto.IPI.CST.valor = u'99'
            d1.imposto.PIS.CST.valor = u'06'
            d1.imposto.COFINS.CST.valor = u'06'

            # Detalhe
            d2 = Det_200()

            d2.nItem.valor = 2
            d2.prod.cProd.valor = u'codigo do produto dois'
            d2.prod.cEAN.valor = u''
            d2.prod.xProd.valor = u'Descricao do produto'
            d2.prod.NCM.valor = u'94034000'
            d2.prod.EXTIPI.valor = u''
            d2.prod.CFOP.valor = u'5101'
            d2.prod.uCom.valor = u'UND'
            d2.prod.qCom.valor = u'100.00'
            d2.prod.vUnCom.valor = u'10.0000'
            d2.prod.vProd.valor = u'1000.00'
            d2.prod.cEANTrib.valor = u''
            d2.prod.uTrib.valor = d1.prod.uCom.valor
            d2.prod.qTrib.valor = d1.prod.qCom.valor
            d2.prod.vUnTrib.valor = d1.prod.vUnCom.valor
            d2.prod.vFrete.valor = u'0.00'
            d2.prod.vSeg.valor = u'0.00'
            d2.prod.vDesc.valor = u'0.00'
            d2.prod.vOutro.valor = u'0.00'

            # Produto entra no total da NF-e
            d2.prod.indTot.valor = 1

            # Impostos
            d2.imposto.regime_tributario = 1
            d2.imposto.ICMS.CSOSN.valor = u'400'
            d2.imposto.IPI.CST.valor = u'99'
            d2.imposto.PIS.CST.valor = u'06'
            d2.imposto.COFINS.CST.valor = u'06'

            # Inclui o detalhe na NF-e
            n.infNFe.det.append(d1)

            # Totais
            n.infNFe.total.ICMSTot.vBC.valor = u'0.00'
            n.infNFe.total.ICMSTot.vICMS.valor = u'0.00'
            n.infNFe.total.ICMSTot.vBCST.valor = u'0.00'
            n.infNFe.total.ICMSTot.vST.valor = u'0.00'
            n.infNFe.total.ICMSTot.vProd.valor = u'1000.00'
            n.infNFe.total.ICMSTot.vFrete.valor = u'0.00'
            n.infNFe.total.ICMSTot.vSeg.valor = u'0.00'
            n.infNFe.total.ICMSTot.vDesc.valor = u'0.00'
            n.infNFe.total.ICMSTot.vII.valor = u'0.00'
            n.infNFe.total.ICMSTot.vIPI.valor = u'0.00'
            n.infNFe.total.ICMSTot.vPIS.valor = u'0.00'
            n.infNFe.total.ICMSTot.vCOFINS.valor = u'0.00'
            n.infNFe.total.ICMSTot.vOutro.valor = u'0.00'
            n.infNFe.total.ICMSTot.vNF.valor = u'0.00'

            n.infNFe.infAdic.infCpl.valor = u'Documento emitido por ME ou'\
                u' EPP optante pelo Simples Nacional. ' \
                u'Nao gera direito a credito fiscal de IPI. '
            
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

        conditions = [('id', 'in', active_ids),
                      ('nfe_status', '=', NFE_STATUS['send_ok'])]
        invoices_to_cancel = inv_obj.search(cr, uid, conditions)

        for inv in inv_obj.browse(cr, uid, invoices_to_cancel,
                                  context=context):
            company = self.pool.get('res.company').browse(cr,
                                                          uid,
                                                          [inv.company_id.id]
                                                          )[0]
            server_host = company.nfe_server_host

            if self.check_server(cr, uid, ids, server_host):
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
                process = p.cancelar_nota(
                    chave_nfe=u'35100411111111111111551010000000271123456789',
                    numero_protocolo=u'135100018751878',
                    justificativa=u'Somente um teste de cancelamento'
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
        return True

    def check_nfe_status(self, cr, uid, ids, context=None):
        """Check NF-e status"""
        return True

    def check_service_status(self, cr, uid, ids, context=None):
        """Check service status"""
        return True

manage_nfe()
