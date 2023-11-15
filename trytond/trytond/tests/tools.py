# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

import unittest

from proteus import Model, Wizard
from proteus import config as pconfig
from trytond.server_context import ServerContext, TEST_CONTEXT

from .test_tryton import backup_db_cache, drop_create, restore_db_cache

__all__ = ['activate_modules', 'set_user']


# PKU add cache_file_name
def activate_modules(modules, *, setup_function=None, cache_file_name=None):
    if isinstance(modules, str):
        modules = [modules]
    cache_name = cache_file_name or '-'.join(modules)
    assert setup_function is None or callable(setup_function)
    if callable(setup_function):
        cache_name += f'-{setup_function.__qualname__}'
    if restore_db_cache(cache_name):
        return _get_config()
    drop_create()

    cfg = _get_config()
    Module = Model.get('ir.module')
    records = Module.find([
            ('name', 'in', modules),
            ])
    assert len(records) == len(modules)
    Module.click(records, 'activate')
    with ServerContext().set_context(**TEST_CONTEXT):
        Wizard('ir.module.activate_upgrade').execute('upgrade')

    if callable(setup_function):
        setup_function(cfg)
    backup_db_cache(cache_name)
    return cfg


def _get_config():
    return pconfig.set_trytond()


def set_user(user, config=None):
    if not config:
        config = pconfig.get_config()
    User = Model.get('res.user', config=config)
    config.user = int(user)
    config._context = User.get_preferences(True, {})


_dummy_test_case = unittest.TestCase()
_dummy_test_case.maxDiff = None


def __getattr__(name):
    return getattr(_dummy_test_case, name)
