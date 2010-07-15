#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Not, Eval, Bool, Or
from trytond.backend import TableHandler


class Category(ModelSQL, ModelView):
    _name = 'product.category'

    account_expense = fields.Property(fields.Many2One('account.account',
        'Account Expense', domain=[
            ('kind', '=', 'expense'),
            ('company', '=', Eval('company')),
        ],
        states={
            'invisible': Not(Bool(Eval('company'))),
        }))
    account_revenue = fields.Property(fields.Many2One( 'account.account',
        'Account Revenue', domain=[
            ('kind', '=', 'revenue'),
            ('company', '=', Eval('company')),
        ],
        states={
            'invisible': Not(Bool(Eval('company'))),
        }))
    customer_taxes = fields.Many2Many('product.category-customer-account.tax',
            'category', 'tax', 'Customer Taxes', domain=[('parent', '=', False)])
    supplier_taxes = fields.Many2Many('product.category-supplier-account.tax',
            'category', 'tax', 'Supplier Taxes', domain=[('parent', '=', False)])

Category()


class CategoryCustomerTax(ModelSQL):
    'Category - Customer Tax'
    _name = 'product.category-customer-account.tax'
    _table = 'product_category_customer_taxes_rel'
    _description = __doc__
    category = fields.Many2One('product.category', 'Category',
            ondelete='CASCADE', select=1, required=True)
    tax = fields.Many2One('account.tax', 'Tax', ondelete='RESTRICT',
            required=True)

    def init(self, cursor, module_name):
        # Migration from 1.6 product renamed into category
        table = TableHandler(cursor, self)
        if table.column_exist('product'):
            table.index_action('product', action='remove')
            table.drop_fk('product')
            table.column_rename('product', 'category')
        super(CategoryCustomerTax, self).init(cursor, module_name)

CategoryCustomerTax()


class CategorySupplierTax(ModelSQL):
    'Category - Supplier Tax'
    _name = 'product.category-supplier-account.tax'
    _table = 'product_category_supplier_taxes_rel'
    _description = __doc__
    category = fields.Many2One('product.category', 'Category',
            ondelete='CASCADE', select=1, required=True)
    tax = fields.Many2One('account.tax', 'Tax', ondelete='RESTRICT',
            required=True)

    def init(self, cursor, module_name):
        # Migration from 1.6 product renamed into category
        table = TableHandler(cursor, self)
        if table.column_exist('product'):
            table.index_action('product', action='remove')
            table.drop_fk('product')
            table.column_rename('product', 'category')
        super(CategorySupplierTax, self).init(cursor, module_name)

CategorySupplierTax()


class Template(ModelSQL, ModelView):
    _name = 'product.template'

    account_category = fields.Boolean('Use Category\'s accounts',
            help='Use the accounts defined on the category')
    account_expense = fields.Property(fields.Many2One('account.account',
        'Account Expense', domain=[
            ('kind', '=', 'expense'),
            ('company', '=', Eval('company')),
        ],
        states={
            'invisible': Or(Not(Bool(Eval('company'))),
                Bool(Eval('account_category'))),
        }, help='This account will be used instead of the one defined ' \
                'on the category.', depends=['account_category']))
    account_revenue = fields.Property(fields.Many2One('account.account',
        'Account Revenue', domain=[
            ('kind', '=', 'revenue'),
            ('company', '=', Eval('company')),
        ],
        states={
            'invisible': Or(Not(Bool(Eval('company'))),
                Bool(Eval('account_category'))),
        }, help='This account will be used instead of the one defined ' \
                'on the category.', depends=['account_category']))
    account_expense_used = fields.Function(fields.Many2One('account.account',
        'Account Expense Used'), 'get_account')
    account_revenue_used = fields.Function(fields.Many2One('account.account',
        'Account Revenue Used'), 'get_account')
    taxes_category = fields.Boolean('Use Category\'s Taxes', help='Use the taxes ' \
            'defined on the category')
    customer_taxes = fields.Many2Many('product.template-customer-account.tax',
            'product', 'tax', 'Customer Taxes', domain=[('parent', '=', False)],
            states={
                'invisible': Or(Not(Bool(Eval('company'))),
                    Bool(Eval('taxes_category'))),
            }, depends=['taxes_category'])
    supplier_taxes = fields.Many2Many('product.template-supplier-account.tax',
            'product', 'tax', 'Supplier Taxes', domain=[('parent', '=', False)],
            states={
                'invisible': Or(Not(Bool(Eval('company'))),
                    Bool(Eval('taxes_category'))),
            }, depends=['taxes_category'])
    customer_taxes_used = fields.Function(fields.One2Many('account.tax', None,
        'Customer Taxes Used'), 'get_taxes')
    supplier_taxes_used = fields.Function(fields.One2Many('account.tax', None,
        'Customer Taxes Used'), 'get_taxes')

    def __init__(self):
        super(Template, self).__init__()
        self._error_messages.update({
            'missing_account': 'There is no account ' \
                    'expense/revenue defined on the product ' \
                    '%s (%d)',
            })

    def default_taxes_category(self, cursor, user, context=None):
        return False

    def get_account(self, cursor, user, ids, name, context=None):
        account_obj = self.pool.get('account.account')
        res = {}
        name = name[:-5]
        for product in self.browse(cursor, user, ids, context=context):
            if product[name]:
                res[product.id] = product[name].id
            else:
                if product.category[name]:
                    res[product.id] = product.category[name].id
                else:
                    self.raise_user_error(cursor, 'missing_account',
                            (product.name, product.id), context=context)
        return res

    def get_taxes(self, cursor, user, ids, name, context=None):
        res = {}
        name = name[:-5]
        for product in self.browse(cursor, user, ids, context=context):
            if product.taxes_category:
                res[product.id] = [x.id for x in product.category[name]]
            else:
                res[product.id] = [x.id for x in product[name]]
        return res

Template()


class TemplateCustomerTax(ModelSQL):
    'Product Template - Customer Tax'
    _name = 'product.template-customer-account.tax'
    _table = 'product_customer_taxes_rel'
    _description = __doc__
    product = fields.Many2One('product.template', 'Product Template',
            ondelete='CASCADE', select=1, required=True)
    tax = fields.Many2One('account.tax', 'Tax', ondelete='RESTRICT',
            required=True)

TemplateCustomerTax()


class TemplateSupplierTax(ModelSQL):
    'Product Template - Supplier Tax'
    _name = 'product.template-supplier-account.tax'
    _table = 'product_supplier_taxes_rel'
    _description = __doc__
    product = fields.Many2One('product.template', 'Product Template',
            ondelete='CASCADE', select=1, required=True)
    tax = fields.Many2One('account.tax', 'Tax', ondelete='RESTRICT',
            required=True)

TemplateSupplierTax()
