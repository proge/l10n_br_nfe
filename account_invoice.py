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

class account_invoice(osv.osv):
    _inherit = 'account.invoice'
    _columns = {
        'nfe_retorno': fields.char(
            u'Retorno da NF-e', size=256, readonly=True
            ),
        'nfe_danfe': fields.binary(u'DANFE', readonly=True),
        'nfe_danfe_name': fields.char(u'Nome do Arquivo', 128, readonly=True),
        'nfe_sent_xml': fields.binary(u'XML de Envio', readonly=True),
        'nfe_sent_xml_name': fields.char(u'Nome do Arquivo', 128,
                                         readonly=True),
        }


account_invoice()
