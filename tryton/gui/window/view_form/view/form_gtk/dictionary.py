# This file is part of Tryton.  The COPYRIGHT file at the top level of this
# repository contains the full copyright notices and license terms.

import operator
import gobject
import gtk
import locale
import decimal
import gettext
from decimal import Decimal

from .widget import Widget
from .integer import IntegerMixin
from .float import FloatMixin

from tryton.gui.window.win_search import WinSearch
from tryton.common import Tooltips, timezoned_date, untimezoned_date, \
        IconFactory
from tryton.common.selection import selection_shortcuts
from tryton.common.completion import get_completion, update_completion
from tryton.common.datetime_ import Date, DateTime
from tryton.common.domain_parser import quote
from tryton.common.entry_position import reset_position
from tryton.common.underline import set_underline
from tryton.common.domain_inversion import eval_domain
from tryton.common.widget_style import widget_class
from tryton.pyson import PYSONDecoder

_ = gettext.gettext


class DictEntry(object):
    expand = True
    fill = True

    def __init__(self, name, parent_widget):
        self.name = name
        self.definition = parent_widget.field.keys[name]
        self.parent_widget = parent_widget
        self.widget = self.create_widget()

    def create_widget(self):
        widget = gtk.Entry()
        widget.connect('key-press-event', self.parent_widget.send_modified)
        widget.connect('focus-out-event',
            lambda w, e: self.parent_widget._focus_out())
        widget.props.activates_default = True
        widget.connect('activate', self.parent_widget.sig_activate)
        return widget

    def modified(self, value):
        return self.get_value() != value.get(self.name)

    def get_value(self):
        return self.widget.get_text()

    def set_value(self, value):
        self.widget.set_text(value or '')
        reset_position(self.widget)

    def set_readonly(self, readonly):
        self.widget.set_editable(not readonly)


class DictBooleanEntry(DictEntry):

    def create_widget(self):
        widget = gtk.CheckButton()
        widget.connect('toggled', self.parent_widget.sig_activate)
        widget.connect('focus-out-event', lambda w, e:
            self.parent_widget._focus_out())
        return widget

    def get_value(self):
        return self.widget.props.active

    def set_value(self, value):
        self.widget.handler_block_by_func(self.parent_widget.sig_activate)
        try:
            self.widget.props.active = bool(value)
        finally:
            self.widget.handler_unblock_by_func(
                self.parent_widget.sig_activate)

    def set_readonly(self, readonly):
        self.widget.set_sensitive(not readonly)


class DictSelectionEntry(DictEntry):
    expand = False
    fill = False

    def create_widget(self):
        widget = gtk.ComboBoxEntry()

        # customizing entry
        child = widget.get_child()
        child.props.activates_default = True
        child.connect('changed', self.parent_widget.send_modified)
        child.connect('focus-out-event',
            lambda w, e: self.parent_widget._focus_out())
        child.connect('activate',
            lambda w: self.parent_widget._focus_out())
        widget.connect('notify::active',
            lambda w, e: self.parent_widget._focus_out())
        widget.connect(
            'scroll-event', lambda c, e: c.emit_stop_by_name('scroll-event'))
        selection_shortcuts(widget)

        # setting completion and selection
        model = gtk.ListStore(gobject.TYPE_STRING)
        model.append(('',))
        self._selection = {'': None}
        width = 10
        selection = self.definition['selection']
        if self.definition.get('sorted', True):
            selection.sort(key=operator.itemgetter(1))
        for value, name in selection:
            name = str(name)
            self._selection[name] = value
            model.append((name,))
            width = max(width, len(name))
        widget.set_model(model)
        widget.set_text_column(0)
        child.set_width_chars(width)
        completion = gtk.EntryCompletion()
        completion.set_inline_selection(True)
        completion.set_model(model)
        child.set_completion(completion)
        completion.set_text_column(0)
        return widget

    def get_value(self):
        child = self.widget.get_child()
        if not child:  # widget is destroyed
            return
        text = child.get_text()
        value = None
        if text:
            for txt, val in list(self._selection.items()):
                if not val:
                    continue
                if txt[:len(text)].lower() == text.lower():
                    value = val
                    if len(txt) == len(text):
                        break
        return value

    def set_value(self, value):
        values = dict(self.definition['selection'])
        child = self.widget.get_child()
        child.set_text(values.get(value, ''))
        reset_position(child)

    def set_readonly(self, readonly):
        self.widget.set_sensitive(not readonly)


class DictIntegerEntry(IntegerMixin, DictEntry):
    expand = False
    fill = False

    def create_widget(self):
        widget = super(DictIntegerEntry, self).create_widget()
        self._prepare_entry(widget)
        return widget

    def get_value(self):
        txt_value = self.widget.get_text()
        if txt_value:
            try:
                return locale.atoi(txt_value)
            except ValueError:
                pass
        return None

    def set_value(self, value):
        if value is not None:
            txt_val = locale.format('%d', value, True)
        else:
            txt_val = ''
        self.widget.set_text(txt_val)
        reset_position(self.widget)


class DictFloatEntry(FloatMixin, DictIntegerEntry):

    @property
    def digits(self):
        record = self.parent_widget.record
        if record:
            digits = record.expr_eval(self.definition.get('digits'))
            if not digits or any(d is None for d in digits):
                return
            return digits

    def get_value(self):
        txt_value = self.widget.get_text()
        if txt_value:
            try:
                return locale.atof(txt_value)
            except ValueError:
                pass
        return None

    def set_value(self, value):
        digits = self.digits
        if value is not None:
            txt_val = locale.format('%.*f', (digits[1], value), True)
        else:
            txt_val = ''
        self.widget.set_text(txt_val)
        reset_position(self.widget)
        self._set_entry_width(self.widget)


class DictNumericEntry(DictFloatEntry):

    def get_value(self):
        txt_value = self.widget.get_text()
        if txt_value:
            try:
                return locale.atof(txt_value, Decimal)
            except decimal.InvalidOperation:
                pass
        return None


class DictDateTimeEntry(DictEntry):
    expand = False
    fill = False

    def create_widget(self):
        widget = DateTime()
        record = self.parent_widget.record
        field = self.parent_widget.field
        if record and field:
            format_ = field.time_format(record)
            widget.props.format = format_
        widget.connect('key_press_event', self.parent_widget.send_modified)
        widget.connect('focus-out-event', lambda w, e:
            self.parent_widget._focus_out())
        return widget

    def get_value(self):
        return untimezoned_date(self.widget.props.value)

    def set_value(self, value):
        self.widget.props.value = timezoned_date(value)


class DictDateEntry(DictEntry):
    expand = False
    fill = False

    def create_widget(self):
        widget = Date()
        record = self.parent_widget.record
        field = self.parent_widget.field
        if record and field:
            format_ = field.date_format(record)
            widget.props.format = format_
        widget.connect('key_press_event', self.parent_widget.send_modified)
        widget.connect('focus-out-event', lambda w, e:
            self.parent_widget._focus_out())
        return widget

    def get_value(self):
        return self.widget.props.value

    def set_value(self, value):
        self.widget.props.value = value


DICT_ENTRIES = {
    'char': DictEntry,
    'boolean': DictBooleanEntry,
    'selection': DictSelectionEntry,
    'datetime': DictDateTimeEntry,
    'date': DictDateEntry,
    'integer': DictIntegerEntry,
    'float': DictFloatEntry,
    'numeric': DictNumericEntry,
    }


class DictWidget(Widget):

    def __init__(self, view, attrs):
        super(DictWidget, self).__init__(view, attrs)
        self.schema_model = attrs['schema_model']
        self.fields = {}
        self.buttons = {}
        self.rows = {}

        self.widget = gtk.Frame()
        label = gtk.Label(set_underline(attrs.get('string', '')))
        label.set_use_underline(True)
        self.widget.set_label_widget(label)
        self.widget.set_shadow_type(gtk.SHADOW_OUT)

        vbox = gtk.VBox()
        self.widget.add(vbox)

        self.table = gtk.Table(1, 3, homogeneous=False)
        self.table.set_col_spacings(0)
        self.table.set_row_spacings(0)
        self.table.set_border_width(0)
        vbox.pack_start(self.table, expand=True, fill=True)

        hbox = gtk.HBox()
        hbox.set_border_width(2)
        self.wid_text = gtk.Entry()
        self.wid_text.set_placeholder_text(_('Search'))
        self.wid_text.props.width_chars = 13
        self.wid_text.connect('activate', self._sig_activate)
        hbox.pack_start(self.wid_text, expand=True, fill=True)
        label.set_mnemonic_widget(self.wid_text)

        if int(self.attrs.get('completion', 1)):
            self.wid_completion = get_completion(search=False, create=False)
            self.wid_completion.connect('match-selected',
                self._completion_match_selected)
            self.wid_text.set_completion(self.wid_completion)
            self.wid_text.connect('changed', self._update_completion)
        else:
            self.wid_completion = None

        self.but_add = gtk.Button()
        self.but_add.connect('clicked', self._sig_add)
        self.but_add.add(IconFactory.get_image(
                'tryton-add', gtk.ICON_SIZE_SMALL_TOOLBAR))
        self.but_add.set_relief(gtk.RELIEF_NONE)
        hbox.pack_start(self.but_add, expand=False, fill=False)
        hbox.set_focus_chain([self.wid_text])
        vbox.pack_start(hbox, expand=True, fill=True)

        self.tooltips = Tooltips()
        self.tooltips.set_tip(self.but_add, _('Add value'))
        self.tooltips.enable()

        self._readonly = False
        self._record_id = None

    @property
    def _invalid_widget(self):
        return self.wid_text

    def _new_remove_btn(self):
        but_remove = gtk.Button()
        but_remove.add(IconFactory.get_image(
                'tryton-remove', gtk.ICON_SIZE_SMALL_TOOLBAR))
        but_remove.set_relief(gtk.RELIEF_NONE)
        return but_remove

    def _sig_activate(self, *args):
        if self.wid_text.get_editable():
            self._sig_add()

    def _sig_add(self, *args):
        context = self.field.get_context(self.record)
        value = self.wid_text.get_text()
        domain = self.field.domain_get(self.record)

        def callback(result):
            if result:
                self.add_new_keys([r[0] for r in result])
            self.wid_text.set_text('')

        win = WinSearch(self.schema_model, callback, sel_multi=True,
            context=context, domain=domain, new=False)
        win.screen.search_filter(quote(value))
        win.show()

    def add_new_keys(self, ids):
        new_keys = self.field.add_new_keys(ids, self.record)
        self.send_modified()
        focus = False
        for key_name in new_keys:
            if key_name not in self.fields:
                self.add_line(key_name)
                if not focus:
                    # Use idle add because it can be called from the callback
                    # of WinSearch while the popup is still there
                    gobject.idle_add(self.fields[key_name].widget.grab_focus)
                    focus = True

    def _sig_remove(self, button, key, modified=True):
        del self.fields[key]
        del self.buttons[key]
        for widget in self.rows[key]:
            self.table.remove(widget)
            widget.destroy()
        del self.rows[key]
        if modified:
            self.send_modified()
            self.set_value()

    def set_value(self):
        self.field.set_client(self.record, self.get_value())

    def get_value(self):
        return dict((key, widget.get_value())
            for key, widget in list(self.fields.items()))

    @property
    def modified(self):
        if self.record and self.field:
            value = self.field.get_client(self.record)
            return any(widget.modified(value)
                for widget in self.fields.values())
        return False

    def _readonly_set(self, readonly):
        self._readonly = readonly
        self._set_button_sensitive()
        for widget in list(self.fields.values()):
            widget.set_readonly(readonly)
        self.wid_text.set_sensitive(not readonly)
        self.wid_text.set_editable(not readonly)

    def _set_button_sensitive(self):
        self.but_add.set_sensitive(bool(
                not self._readonly
                and self.attrs.get('create', True)))
        for button in self.buttons.values():
            button.set_sensitive(bool(
                    not self._readonly
                    and self.attrs.get('delete', True)))

    def add_line(self, key):
        key_schema = self.field.keys[key]
        self.fields[key] = DICT_ENTRIES[key_schema['type_']](key, self)
        field = self.fields[key]
        alignment = gtk.Alignment(
            float(self.attrs.get('xalign', 0.0)),
            float(self.attrs.get('yalign', 0.5)),
            float(self.attrs.get('xexpand', 1.0)),
            float(self.attrs.get('yexpand', 1.0)))
        hbox = gtk.HBox()
        hbox.pack_start(field.widget, expand=field.expand, fill=field.fill)
        alignment.add(hbox)
        n_rows = self.table.props.n_rows
        self.table.resize(n_rows + 1, 3)
        text = key_schema['string'] + _(':')
        label = gtk.Label(set_underline(text))
        label.set_use_underline(True)
        label.set_alignment(1., .5)
        self.table.attach(label, 0, 1, n_rows - 1, n_rows,
            xoptions=gtk.FILL, yoptions=False, xpadding=2)
        label.set_mnemonic_widget(field.widget)
        label.show()
        self.table.attach(alignment, 1, 2, n_rows - 1, n_rows,
            xoptions=gtk.FILL | gtk.EXPAND, yoptions=False, xpadding=2)
        alignment.show_all()
        remove_but = self._new_remove_btn()
        self.tooltips.set_tip(remove_but, _('Remove "%s"') %
            key_schema['string'])
        self.table.attach(remove_but, 2, 3, n_rows - 1, n_rows,
            xoptions=gtk.FILL, yoptions=False, xpadding=2)
        remove_but.connect('clicked', self._sig_remove, key)
        remove_but.show_all()
        self.rows[key] = [label, alignment, remove_but]
        self.buttons[key] = remove_but

    def display(self):
        super(DictWidget, self).display()

        if self.field is None:
            return

        record_id = self.record.id if self.record else None
        if record_id != self._record_id:
            for key in list(self.fields.keys()):
                self._sig_remove(None, key, modified=False)
            self._record_id = record_id

        value = self.field.get_client(self.record) if self.field else {}
        new_key_names = set(value.keys()) - set(self.field.keys)
        if new_key_names:
            self.field.add_keys(list(new_key_names), self.record)
        decoder = PYSONDecoder()
        for key, val in sorted(value.items()):
            if key not in self.field.keys:
                continue
            if key not in self.fields:
                self.add_line(key)
            widget = self.fields[key]
            widget.set_value(val)
            widget.set_readonly(self._readonly)
            key_domain = decoder.decode(
                self.field.keys[key].get('domain') or '[]')
            widget_class(
                widget.widget, 'invalid', not eval_domain(key_domain, value))
        for key in set(self.fields.keys()) - set(value.keys()):
            self._sig_remove(None, key, modified=False)

        self._set_button_sensitive()

    def _completion_match_selected(self, completion, model, iter_):
        record_id, = model.get(iter_, 1)
        self.add_new_keys([record_id])
        self.wid_text.set_text('')

        completion_model = self.wid_completion.get_model()
        completion_model.clear()
        completion_model.search_text = self.wid_text.get_text()
        return True

    def _update_completion(self, widget):
        if not self.wid_text.get_editable():
            return
        if not self.record:
            return
        update_completion(self.wid_text, self.record, self.field,
            self.schema_model)
