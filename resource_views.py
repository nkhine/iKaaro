# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2006-2008 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
# Copyright (C) 2007-2008 Henry Obein <henry@itaapy.com>
# Copyright (C) 2008 Matthieu France <matthieu@itaapy.com>
# Copyright (C) 2008 Nicolas Deram <nicolas@itaapy.com>
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

# Import from the Standard Library
from operator import itemgetter

# Import from itools
from itools.core import merge_dicts, thingy_lazy_property
from itools.datatypes import String
from itools.gettext import MSG
from itools.handlers import checkid
from itools.i18n import get_language_name
from itools.stl import stl
from itools.uri import Path, get_reference
from itools.vfs import FileName
from itools.web import view, stl_view, INFO, ERROR, FormError
from itools.web import file_field, input_field, password_field

# Import from ikaaro
from autoform import AutoForm
from fields import description_field, subject_field, title_field
from fields import TimestampField
from folder_views import Folder_Table
import messages
from registry import get_resource_class
from utils import reduce_string
from views import ContextMenu



class EditLanguageMenu(ContextMenu):

    title = MSG(u'Edit Language')

    def get_items(self):
        content_language = self.content_language

        site_root = self.resource.get_site_root()
        languages = site_root.get_value('website_languages')
        uri = get_reference(self.context.uri)
        return [
            {'title': get_language_name(x),
             'href': uri.replace(content_language=x),
             'class': 'nav-active' if (x == content_language) else None}
            for x in languages ]



class DBResource_Edit(AutoForm):

    access = 'is_allowed_to_edit'
    view_title = MSG(u'Edit')
    icon = 'metadata.png'
    context_menus = [EditLanguageMenu()]

    title = title_field()
    description = description_field()
    subject = subject_field()
    timestamp = TimestampField()


    field_names = ['timestamp', 'title', 'description', 'subject']


    @thingy_lazy_property
    def edit_conflict(self):
        context = self.context

        timestamp = self.timestamp.value
        if timestamp is None:
            context.message = messages.MSG_EDIT_CONFLICT
            return True

        mtime = self.resource.get_mtime()
        if mtime is not None and timestamp < mtime:
            # Conlicft unless we are overwriting our own work
            last_author = self.resource.get_last_author()
            if last_author != context.user.get_name():
                user = context.get_user_title(last_author)
                context.message = messages.MSG_EDIT_CONFLICT2(user=user)
                return True

        return False


    def set_value(self, name, value):
        language = self.content_language
        self.resource.set_property(name, value, language=language)


    def action(self):
        context = self.context

        # Check edit conflict
        if self.edit_conflict:
            return context.redirect()

        # Save changes
        for field in self.get_fields():
            if not field.readonly and field.value is not None:
                self.set_value(field.name, field.value)

        # Ok
        context.change_resource(self.resource)
        context.message = messages.MSG_CHANGES_SAVED
        context.redirect()



class DBResource_Backlinks(Folder_Table):
    """Backlinks are the list of resources pointing to this resource.  This
    view answers the question "where is this resource used?" You'll see all
    WebPages and WikiPages (for example) referencing it.  If the list is
    empty, you can consider it is "orphan".
    """

    access = 'is_allowed_to_view'
    view_title = MSG(u"Backlinks")
    icon = 'rename.png'

    search_template = None

    def get_table_columns(self):
        cols = super(DBResource_Backlinks, self).get_table_columns()
        return [ col for col in cols if col[0] != 'checkbox' ]


    def get_items(self, resource, context):
        path = str(resource.physical_path)
        return context.search(links=path)


    table_actions = []



###########################################################################
# Interface to add images from the TinyMCE editor
###########################################################################

class DBResource_AddBase(stl_view):
    """Base class for 'DBResource_AddImage' and 'DBResource_AddLink' (used
    by the Web Page editor).
    """

    access = 'is_allowed_to_edit'

    element_to_add = None
    item_classes = ()
    folder_classes = ()

    # Fields
    target_path = input_field(required=True)
    target_id = input_field()
    mode = input_field(required=True)
    file = file_field(required=True)


    def http_get(self):
        # FIXME Override stl_view.http_get to use 'ok' instead of 'ok_wrap'
        context.add_query_schema(self.get_query_schema())
        # STL
        namespace = self.get_namespace(resource, context)
        template = self.get_template(resource, context)
        body = stl(template, namespace, mode='html')
        # Ok
        context.ok('text/html', body)


    def get_item_classes(self):
        from resource_ import DBResource
        return self.item_classes if self.item_classes else (DBResource,)


    def get_folder_classes(self):
        from folder import Folder
        return self.folder_classes if self.folder_classes else (Folder,)


    def get_configuration(self):
        return {}


    def get_root(self, context):
        return context.resource.get_site_root()


    def get_start(self, resource):
        from file import File
        if issubclass(resource, File):
            return resource.get_parent()
        return resource


    def is_folder(self, resource):
        bases = self.get_folder_classes()
        return issubclass(resource, bases)


    def is_item(self, resource):
        bases = self.get_item_classes()
        return issubclass(resource, bases)


    def can_upload(self, cls):
        bases = self.get_item_classes()
        return issubclass(cls, bases)


    def get_namespace(self, resource, context):
        from file import Image
        from folder import Folder

        # For the breadcrumb
        start = self.get_start(resource)

        # Default parameter values
        root = self.get_root(context)
        root_parent = root.get_parent()

        # Get the query parameters
        target_path = context.get_form_value('target')
        # Get the target folder
        if target_path is None:
            if issubclass(start, Folder):
                target = start
            else:
                target = start.get_parent()
        else:
            target = root.get_resource(target_path)

        # The breadcrumb
        breadcrumb = []
        node = target
        uri = get_reference(context.uri)
        while node is not root_parent:
            url = uri.replace(target=str(root.get_pathto(node)))
            title = node.get_title()
            short_title = reduce_string(title, 12, 40)
            quoted_title = short_title.replace("'", "\\'")
            breadcrumb.insert(0, {'name': node.get_name(),
                                  'title': title,
                                  'short_title': short_title,
                                  'quoted_title': quoted_title,
                                  'url': url})
            node = node.get_parent()

        # Content
        folders = []
        items = []
        user = context.user
        for resource in target.search_resources():
            is_folder = self.is_folder(resource)
            is_item = self.is_item(resource)
            if not is_folder and not is_item:
                continue

            ac = resource.access_control
            if not ac.is_allowed_to_view(user, resource):
                continue
            path = context.resource.get_pathto(resource)
            url = uri.replace(target=str(root.get_pathto(resource)))

            # Calculate path
            if issubclass(resource, Image):
                path_to_icon = ";thumb?width48=&height=48"
            else:
                path_to_icon = resource.get_resource_icon(48)
            if path:
                path_to_resource = Path(str(path) + '/')
                path_to_icon = path_to_resource.resolve(path_to_icon)
            title = resource.get_title()
            short_title = reduce_string(title, 12, 40)
            quoted_title = short_title.replace("'", "\\'")
            item = {
                'title': title,
                'short_title': short_title,
                'quoted_title': quoted_title,
                'path': path,
                'url': url,
                'icon': path_to_icon,
                'item_type': resource.handler.get_mimetype()}
            if is_folder:
                folders.append(item)
            if is_item:
                items.append(item)

        # Sort
        items.sort(key=itemgetter('short_title'))
        folders.sort(key=itemgetter('short_title'))

        # Avoid general template
        context.set_header('Content-Type', 'text/html; charset=UTF-8')

        # Build and return the namespace
        mode = context.get_query_value('mode')
        namespace = self.get_configuration()
        additional_javascript = self.get_additional_javascript(context)
        namespace['additional_javascript'] = additional_javascript
        namespace['target_path'] = str(target.get_abspath())
        namespace['breadcrumb'] = breadcrumb
        namespace['folders'] = folders
        namespace['items'] = items
        namespace['element_to_add'] = self.element_to_add
        namespace['target_id'] = context.get_form_value('target_id')
        namespace['message'] = context.message
        namespace['mode'] = mode
        namespace['resource_action'] = self.get_resource_action(context)
        namespace['scripts'] = self.get_scripts(mode)
        return namespace


    def get_scripts(self, mode):
        if mode == 'wiki':
            return ['/ui/wiki/javascript.js']
        elif mode == 'tiny_mce':
            return ['/ui/tiny_mce/javascript.js',
                    '/ui/tiny_mce/tiny_mce_src.js',
                    '/ui/tiny_mce/tiny_mce_popup.js']
        return []


    def get_additional_javascript(self, context):
        mode = context.get_query_value('mode')
        if mode != 'input':
            return ''

        additional_javascript = """
            function select_element(type, value, caption) {
                window.opener.$("#%s").val(value);
                window.close();
            }
            """

        target_id = context.get_form_value('target_id')
        return additional_javascript % target_id


    def action_upload(self, resource, context, form):
        filename, mimetype, body = form['file']
        name, type, language = FileName.decode(filename)

        # Check the filename is good
        name = checkid(name)
        if name is None:
            context.message = messages.MSG_BAD_NAME
            return

        # Get the container
        container = context.get_resource(form['target_path'])

        # Check the name is free
        if container.get_resource(name, soft=True) is not None:
            context.message = messages.MSG_NAME_CLASH
            return

        # Check it is of the expected type
        cls = get_resource_class(mimetype)
        if not self.can_upload(cls):
            error = u'The given file is not of the expected type.'
            context.message = ERROR(error)
            return

        # Add the image to the resource
        child = container.make_resource(name, cls, body=body, format=mimetype,
                                        filename=filename, extension=type)
        # Get the path
        path = resource.get_pathto(child)
        action = self.get_resource_action(context)
        if action:
            path = path.resolve_name('.%s' % action)
        # Return javascript
        mode = form['mode']
        scripts = self.get_scripts(mode)
        context.add_script(*scripts)
        return self.get_javascript_return(context, path)


    def get_javascript_return(self, context, path):
        return """
            <script type="text/javascript">
              %s
              select_element('%s', '%s', '');
            </script>""" % (self.get_additional_javascript(context),
                            self.element_to_add, path)


    def get_resource_action(self, context):
        return ''



class DBResource_AddImage(DBResource_AddBase):

    template = 'html/addimage.xml'
    element_to_add = 'image'


    def get_item_classes(self):
        from file import Image
        return self.item_classes if self.item_classes else (Image,)


    def get_configuration(self):
        return {
            'show_browse': True,
            'show_external': False,
            'show_insert': False,
            'show_upload': True}


    def get_resource_action(self, context):
        mode = context.get_query_value('mode')
        if mode == 'tiny_mce':
            return '/;download'
        return DBResource_AddBase.get_resource_action(self, context)



class DBResource_AddLink(DBResource_AddBase):

    template = 'html/addlink.xml'
    element_to_add = 'link'

    title = input_field(required=True)

    def get_configuration(self):
        return {
            'show_browse': True,
            'show_external': True,
            'show_insert': True,
            'show_upload': True}


    def action_add_resource(self, resource, context, form):
        mode = form['mode']
        name = checkid(form['title'])
        # Check name validity
        if name is None:
            context.message = MSG(u"Invalid title.")
            return
        # Get the container
        container = context.get_resource(context.get_form_value('target_path'))
        # Check the name is free
        if container.get_resource(name, soft=True) is not None:
            context.message = messages.MSG_NAME_CLASH
            return
        # Get the type of resource to add
        cls = self.get_page_type(mode)
        # Create the resource
        child = container.make_resource(name, cls)
        path = context.resource.get_pathto(child)
        scripts = self.get_scripts(mode)
        context.add_script(*scripts)
        return self.get_javascript_return(context, path)


    def get_page_type(self, mode):
        """Return the type of page to add corresponding to the mode
        """
        if mode == 'tiny_mce':
            from webpage import WebPage
            return WebPage
        elif mode == 'wiki':
            from wiki import WikiPage
            return WikiPage
        else:
            raise ValueError, 'Incorrect mode %s' % mode



class DBResource_AddMedia(DBResource_AddImage):

    element_to_add = 'media'

    def get_item_classes(self):
        from file import Flash, Video
        return self.item_classes if self.item_classes else (Flash, Video)


    def get_configuration(self):
        return {
            'show_browse': True,
            'show_external': True,
            'show_insert': False,
            'show_upload': True}



###########################################################################
# Views / Login, Logout
###########################################################################

class LoginView(stl_view):

    access = True
    view_title = MSG(u'Login')
    template = 'base/login.xml'


    username = input_field(required=True, title=MSG(u'E-mail Address'))
    password = password_field(required=True, title=MSG(u'Password'))


    def cook(self, method):
        super(LoginView, self).cook(method)

        if method == 'get':
            return

        # Check the user exists
        user = self.user
        if user is None:
            field = self.username
            error = MSG(u'The user "{username}" does not exist.')
            field.error = error.gettext(username=field.value)
            raise FormError

        # Check the password is right
        field = self.password
        if not user.authenticate(field.value):
            field.error = MSG(u'The password is wrong.')
            raise FormError


    @thingy_lazy_property
    def user(self):
        username = self.username.value
        return self.context.get_user_by_login(username)


    def action(self):
        context = self.context

        # Set cookie
        user = self.user
        password = self.password.value
        user.set_auth_cookie(context, password)

        # Internal redirect
        context.user = user
        context.message = INFO(u'Welcome!')
        context.redirect(view=None)



class LogoutView(view):
    """Logs out of the application.
    """

    access = True


    def http_get(self):
        # Log-out
        context = self.context
        context.del_cookie('__ac')
        context.user = None

        context.message = INFO(u'You Are Now Logged out.')
        context.redirect(view=None)

