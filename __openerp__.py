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

{
    "name": "NF-e",
    "version": "0.1",
    "author": "PROGE",
    "category": "Localization",
    "website": "http://proge.com.br",
    "description": """
    Module to support SPED NF-e.
    """,
    'depends': [
        'l10n_br_data_account',
        'l10n_br_data_base',
        'l10n_br_delivery',
        'l10n_br_sale',
        ],
    'data': [
        'account_invoice_view.xml',
        'wizard/manage_nfe_view.xml',
        ],
    'demo': [],
    'test': [],
    'installable': True,
}
