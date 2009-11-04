# -*- coding: UTF-8 -*-
# Copyright (C) 2007 Henry Obein <henry@itaapy.com>
# Copyright (C) 2007-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2007-2008 Nicolas Deram <nicolas@itaapy.com>
# Copyright (C) 2008 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2008 Sylvain Taverne <sylvain@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from itools
from itools.core import thingy_lazy_property
from itools.datatypes import Date, Enumerate, Boolean
from itools.gettext import MSG
from itools.http import get_context
from itools.web import STLForm

# Import from ikaaro
from forms import DateField, FormField, RadioField, SelectField, TextField
from forms import make_stl_template



def get_default_field(datatype):
    if issubclass(datatype, Boolean):
        return RadioField
    elif issubclass(datatype, Date):
        return DateField
    elif issubclass(datatype, Enumerate):
        return SelectField

    return TextField



class ReadOnlyWidget(object):

    template = list(XMLParser(
        """<input type="hidden" id="${id}" name="${name}" value="${value}" />
           ${displayed}""", stl_namespaces))


    def get_namespace(self, datatype, value):
        displayed = getattr(self, 'displayed', None)

        if issubclass(datatype, Enumerate) and isinstance(value, list):
            for option in value:
                if not option['selected']:
                    continue
                value = option['name']
                if displayed is None:
                    displayed = option['value']
                break
            else:
                value = datatype.default
                if displayed is None:
                    displayed = datatype.get_value(value)

        if displayed is None:
            displayed = value

        return {
            'name': self.name,
            'id': self.id,
            'value': value,
            'displayed': displayed}



class CheckboxWidget(object):

    template = make_stl_template("""
    <stl:block stl:repeat="option options">
      <input type="checkbox" id="${id}-${option/name}" name="${name}"
        value="${option/name}" checked="${option/selected}" />
      <label for="${id}-${option/name}">${option/value}</label>
      <br stl:if="not oneline" />
    </stl:block>""")


class BooleanRadio(Widget):

    template = list(XMLParser("""
        <label for="${id}-yes">${labels/yes}</label>
        <input id="${id}-yes" name="${name}" type="radio" value="1"
          checked="checked" stl:if="is_yes"/>
        <input id="${id}-yes" name="${name}" type="radio" value="1"
          stl:if="not is_yes"/>

        <label for="${id}-no">${labels/no}</label>
        <input id="${id}-no" name="${name}" type="radio" value="0"
          checked="checked" stl:if="not is_yes"/>
        <input id="${id}-no" name="${name}" type="radio" value="0"
          stl:if="is_yes"/>
        """, stl_namespaces))


    def get_namespace(self, datatype, value):
        default_labels = {'yes': MSG(u'Yes'), 'no': MSG(u'No')}
        labels = getattr(self, 'labels', default_labels)
        return {
            'name': self.name,
            'id': self.id,
            'is_yes': value in [True, 1, '1'],
            'labels': labels}



class PathSelectorWidget(object):

    action = 'add_link'
    display_workflow = True

    template = list(XMLParser(
    """
    <input type="text" id="selector-${id}" size="${size}" name="${name}"
      value="${value}" />
    <input id="selector-button-${id}" type="button" value="..."
      name="selector_button_${name}"
      onclick="popup(';${action}?target_id=selector-${id}&amp;mode=input', 620, 300);"/>
    ${workflow_state}
    """, stl_namespaces))


    def workflow_state(self):
        from ikaaro.workflow import get_workflow_preview

        workflow_state = None
        if self.display_workflow:
            context = get_context()
            if type(value) is not str:
                value = datatype.encode(value)
            if value:
                resource = context.resource.get_resource(value, soft=True)
                if resource:
                    workflow_state = get_workflow_preview(resource, context)

        return {
            'type': self.type,
            'name': self.name,
            'id': self.id,
            'value': value,
            'size': self.size,
            'action': self.action,
            'workflow_state': workflow_state}



class ImageSelectorWidget(PathSelectorWidget):

    action = 'add_image'
    width = 128
    height = 128

    template = list(XMLParser(
    """
    <input type="text" id="selector-${id}" size="${size}" name="${name}"
      value="${value}" />
    <input id="selector-button-${id}" type="button" value="..."
      name="selector_button_${name}"
      onclick="popup(';${action}?target_id=selector-${id}&amp;mode=input', 620, 300);" />
    ${workflow_state}
    <br/>
    <img src="${value}/;thumb?width=${width}&amp;height=${height}" stl:if="value"/>
    """, stl_namespaces))


    def get_namespace(self, datatype, value):
        return merge_dicts(PathSelectorWidget.get_namespace(self, datatype, value),
                           width=self.width, height=self.height)



###########################################################################
# Generate Form
###########################################################################
class AutoForm(STLForm):
    """Fields is a dictionnary:

      {'firstname': Unicode(mandatory=True),
       'lastname': Unicode(mandatory=True)}

    Widgets is a list:

      [TextInput('firstname', title=MSG(u'Firstname')),
       TextInput('lastname', title=MSG(u'Lastname'))]
    """

    template = 'auto_form.xml'
    submit_value = MSG(u'Save')
    submit_class = 'button-ok'
    view_description = None


    def fields(self):
        return [ x for x in self.get_fields() if issubclass(x, FormField) ]


    def first_field(self):
        return self.field_names[0]


    def form_action(self):
        return self.context.uri

