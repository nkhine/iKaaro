# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2007 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2006-2007 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2006-2007 Nicolas Deram <nicolas@itaapy.com>
# Copyright (C) 2007 Henry Obein <henry@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
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
from marshal import dumps, loads
from string import Template
from urllib import quote, quote_plus, unquote
from zlib import compress, decompress

# Import from itools
from itools.catalog import EqQuery, AndQuery, OrQuery, PhraseQuery
from itools.datatypes import Boolean, DataType, Unicode
from itools.handlers import Folder as FolderHandler, checkid
from itools.stl import stl
from itools.uri import Path, get_reference
from itools import vfs
from itools.web import get_context

# Import from ikaaro
from base import DBObject
from binary import Image
from exceptions import ConsistencyError
from messages import *
from registry import register_object_class, get_object_class
from utils import generate_name, reduce_string
import widgets
from workflow import WorkflowAware



class CopyCookie(DataType):

    default = None, []

    @staticmethod
    def encode(value):
        return quote(compress(dumps(value), 9))


    @staticmethod
    def decode(str):
        return loads(decompress(unquote(str)))



class Folder(DBObject):

    class_id = 'folder'
    class_version = '20071215'
    class_layout = {}
    class_title = u'Folder'
    class_description = u'Organize your files and documents with folders.'
    class_icon16 = 'icons/16x16/folder.png'
    class_icon48 = 'icons/48x48/folder.png'
    class_views = [
        ['browse_content?mode=list',
         'browse_content?mode=image'],
        ['new_resource_form'],
        ['edit_metadata_form']]
    class_handler = FolderHandler


    search_criteria =  [
        {'id': 'title', 'title': u"Title"},
        {'id': 'text', 'title': u"Text"},
        {'id': 'name', 'title': u"Name"},
    ]


    #########################################################################
    # Aggregation relationship (what a generic folder can contain)
    class_document_types = []

    __fixed_handlers__ = []


    @classmethod
    def register_document_type(cls, handler_class):
        cls.class_document_types.append(handler_class)


    def get_document_types(self):
        return self.class_document_types


    #######################################################################
    # Traverse
    #######################################################################
    GET__access__ = True
    def GET(self, context):
        # Try index
        try:
            self.get_object('index')
        except LookupError:
            return DBObject.GET(self, context)

        return context.uri.resolve2('index')


    #######################################################################
    # API
    #######################################################################
    def _has_object(self, name):
        folder = self.handler
        return folder.has_handler('%s.metadata' % name)


    def _get_names(self):
        folder = self.handler
        return [ x[:-9] for x in folder.get_handler_names()
                 if x[-9:] == '.metadata' ]


    def _get_object(self, name):
        folder = self.handler
        metadata = folder.get_handler('%s.metadata' % name)
        format = metadata.format

        uri = folder.uri.resolve2(name)
        if vfs.exists(uri):
            is_file = vfs.is_file(uri)
        else:
            # FIXME This is just a guess, it may fail.
            is_file = '/' in format

        cls = get_object_class(format, is_file=is_file)
        return cls(metadata)


    def del_object(self, name):
        object = self.get_object(name)

        # Check referencial-integrity
        # FIXME Check sub-objects too
        path = str(object.abspath)
        root = self.get_root()
        results = root.search(links=path)
        n = results.get_n_documents()
        if n:
            message = 'cannot delete, object "%s" is referenced' % path
            raise ConsistencyError, message

        # Events, remove
        get_context().server.remove_object(object)
        # Remove
        folder = self.handler
        folder.del_handler('%s.metadata' % name)
        for handler in object.get_handlers():
            if folder.has_handler(handler.uri):
                folder.del_handler(handler.uri)


    def _resolve_source_target(self, source, target):
        # Find out the source and target absolute URIs
        folder = self.handler
        if source[0] == '/':
            source_uri = self.get_root().handler.uri.resolve2(source[1:])
        else:
            source_uri = folder.uri.resolve2(source)
        if target[0] == '/':
            target_uri = self.get_root().handler.uri.resolve2(target[1:])
        else:
            target_uri = folder.uri.resolve2(target)

        # Load the handlers so they are of the right class, for resources
        # like that define explicitly the handler class.  This fixes for
        # instance copy&cut&paste of a tracker in a just started server.
        # TODO this is a work-around, there should be another way to define
        # explicitly the handler class.
        resource = self.get_object(source)
        if isinstance(resource, Folder):
            for resource in resource.traverse_objects():
                for handler in resource.get_handlers():
                    pass
        else:
            for handler in resource.get_handlers():
                pass

        return source_uri, target_uri


    def copy_object(self, source, target):
        server = get_context().server

        # Find out the source and target absolute URIs
        source_uri, target_uri = self._resolve_source_target(source, target)
        new_name = target_uri.path[-1]

        # Get the source resource
        object = self.get_object(source)

        # Copy the metadata
        folder = self.handler
        folder.copy_handler('%s.metadata' % source_uri,
                            '%s.metadata' % target_uri)
        # Copy the content
        for old_name, new_name in object.rename_handlers(new_name):
            if old_name is None:
                continue
            src_uri = source_uri.resolve(old_name)
            dst_uri = target_uri.resolve(new_name)
            if folder.has_handler(src_uri):
                folder.copy_handler(src_uri, dst_uri)

        # Events, add
        object = self.get_object(target)
        server.add_object(object)


    def move_object(self, source, target):
        server = get_context().server

        # Find out the source and target absolute URIs
        source_uri, target_uri = self._resolve_source_target(source, target)
        new_name = target_uri.path[-1]

        # Events, remove
        object = self.get_object(source)
        server.remove_object(object)

        # Move the metadata
        folder = self.handler
        folder.move_handler('%s.metadata' % source_uri,
                            '%s.metadata' % target_uri)
        # Move the content
        for old_name, new_name in object.rename_handlers(new_name):
            if old_name is None:
                continue
            src_uri = source_uri.resolve(old_name)
            dst_uri = target_uri.resolve(new_name)
            if folder.has_handler(src_uri):
                folder.move_handler(src_uri, dst_uri)

        # Events, add
        object = self.get_object(target)
        server.add_object(object)


    def traverse_objects(self):
        yield self
        for name in self._get_names():
            object = self.get_object(name)
            if isinstance(object, Folder):
                for x in object.traverse_objects():
                    yield x
            else:
                yield object


    def search_objects(self, path='.', format=None, state=None,
                       object_class=None):
        for object in self.get_objects(path):
            if not isinstance(object, DBObject):
                continue
            # Filter by base class
            cls = object_class
            if cls is not None and not isinstance(object, cls):
                continue
            # Filter by class_id
            if format is not None and object.metadata.format != format:
                continue
            # Filter by workflow state
            if state is not None and object.get_workflow_state() != state:
                continue
            # All filters passed
            yield object


    #######################################################################
    # User interface
    #######################################################################
    def get_subviews(self, name):
        if name == 'new_resource_form':
            subviews = []
            for cls in self.get_document_types():
                id = cls.class_id
                ref = 'new_resource_form?type=%s' % quote_plus(id)
                subviews.append(ref)
            return subviews
        return DBObject.get_subviews(self, name)


    def new_resource_form__sublabel__(self, **kw):
        type = kw.get('type')
        for cls in self.get_document_types():
            if cls.class_id == type:
                return cls.class_title
        return u'New Resource'


    def new_resource_form__icon__(self, **kw):
        type = kw.get('type')
        for cls in self.get_document_types():
            if cls.class_id == type:
                return cls.get_class_icon()
        return '/ui/icons/16x16/new.png'


    def get_context_menu_base(self):
        return self


    #######################################################################
    # Browse
    def get_human_size(self):
        names = self.get_names()
        size = len(names)

        str = self.gettext('$n obs')
        return Template(str).substitute(n=size)


    def browse_list(self, context, sortby=['title'], sortorder='up',
            batchsize=20, search_subfolders=False,
            action=';browse_content?mode=list', *args):
        # Get the form values
        get_form_value = context.get_form_value
        term = get_form_value('search_term', type=Unicode)
        term = term.strip()
        field = get_form_value('search_field')
        if field:
            search_subfolders = get_form_value('search_subfolders',
                                               type=Boolean, default=False)

        sortby = context.get_form_values('sortby', default=sortby)
        sortorder = get_form_value('sortorder', default=sortorder)

        # Build the query
        args = list(args)
        abspath = str(self.get_canonical_path())
        if search_subfolders is True:
            args.append(EqQuery('paths', abspath))
        else:
            args.append(EqQuery('parent_path', abspath))

        if term:
            args.append(PhraseQuery(field, term))

        if len(args) == 1:
            query = args[0]
        else:
            query = AndQuery(*args)

        # Build the namespace
        namespace = self.browse_namespace(16, sortby, sortorder, batchsize,
                                          query=query)
        namespace['action'] = action
        namespace['search_term'] = term
        namespace['search_subfolders'] = search_subfolders
        namespace['search_fields'] = [
            {'id': x['id'], 'title': self.gettext(x['title']),
             'selected': x['id'] == field or None}
            for x in self.get_search_criteria() ]

        # The column headers
        columns = [
            ('name', u'Name'), ('title', u'Title'), ('format', u'Type'),
            ('mtime', u'Last Modified'), ('last_author', u'Last Author'),
            ('size', u'Size'), ('workflow_state', u'State')]

        # Actions
        user = context.user
        ac = self.get_access_control()
        actions = []
        message = self.gettext(MSG_DELETE_SELECTION)
        if namespace['total']:
            actions = [
                ('remove', u'Remove', 'button_delete',
                 'return confirmation("%s");' % message.encode('utf_8')),
                ('rename_form', u'Rename', 'button_rename', None),
                ('copy', u'Copy', 'button_copy', None),
                ('cut', u'Cut', 'button_cut', None)]
            actions = [(x[0], self.gettext(x[1]), x[2], x[3])
                    for x in actions if ac.is_access_allowed(user, self, x[0])]
        if context.has_cookie('ikaaro_cp'):
            if ac.is_access_allowed(user, self, 'paste'):
                actions.append(('paste', self.gettext(u'Paste'),
                                'button_paste', None))

        # Go!
        namespace['table'] = widgets.table(
            columns, namespace['objects'], sortby, sortorder, actions,
            self.gettext)

        handler = self.get_object('/ui/folder/browse_list.xml')
        return stl(handler, namespace)


    def browse_image(self, context):
        selected_image = context.get_form_value('selected_image')
        selected_index = None

        # check selected image
        if selected_image is not None:
            path = Path(selected_image)
            selected_image = path[-1]
            if not selected_image in self.get_names():
                selected_image = None

        # look up available images
        query = EqQuery('parent_path', str(self.get_canonical_path()))
        namespace = self.browse_namespace(48, query=query, batchsize=0)
        objects = []
        offset = 0
        for index, image in enumerate(namespace['objects']):
            name = image['name']
            if isinstance(name, tuple):
                name = name[0]
            object = self.get_object(name)
            if not isinstance(object, Image):
                offset = offset + 1
                continue
            if selected_image is None:
                selected_image = name
            if selected_image == name:
                selected_index = index - offset
            image['name'] = name
            objects.append(image)

        namespace['objects'] = objects

        # selected image namespace
        if selected_image is None:
            namespace['selected'] = None
        else:
            image = self.get_object(selected_image)
            selected = {}
            selected['title_or_name'] = image.get_title()
            selected['description'] = image.get_property('description')
            selected['url'] = '%s/;%s' % (image.name, image.get_firstview())
            selected['preview'] = '%s/;icon48?height=320&width=320' \
                                  % image.name
            size = image.handler.get_size()
            if size is None:
                # PIL not installed
                width, height = 0, 0
            else:
                width, height = size
            selected['width'] = width
            selected['height'] = height
            selected['format'] = image.metadata.format
            pattern = ';browse_content?mode=image&selected_image=%s'
            if selected_index == 0:
                selected['previous'] = None
            else:
                previous = objects[selected_index - 1]['name']
                selected['previous'] = pattern % previous
            if selected_index == (len(objects) - 1):
                selected['next'] = None
            else:
                next = objects[selected_index + 1]['name']
                selected['next'] = pattern % next
            namespace['selected'] = selected

        # Append gallery style
        context.styles.append('/ui/gallery.css')

        handler = self.get_object('/ui/folder/browse_image.xml')
        return stl(handler, namespace)


    remove__access__ = 'is_allowed_to_remove'
    def remove(self, context):
        # Check input
        ids = context.get_form_values('ids')
        if not ids:
            return context.come_back(u'No objects selected.')

        # Clean the copy cookie if needed
        cut, paths = context.get_cookie('ikaaro_cp', type=CopyCookie)

        # Remove objects
        removed = []
        not_removed = []
        user = context.user
        abspath = self.get_abspath()

        # We sort and reverse ids in order to
        # remove the childs then their parents
        ids.sort()
        ids.reverse()
        for name in ids:
            object = self.get_object(name)
            ac = object.get_access_control()
            if ac.is_allowed_to_remove(user, object):
                # Remove object
                try:
                    self.del_object(name)
                except ConsistencyError:
                    not_removed.append(name)
                    continue
                removed.append(name)
                # Clean cookie
                if str(abspath.resolve2(name)) in paths:
                    context.del_cookie('ikaaro_cp')
                    paths = []
            else:
                not_removed.append(name)

        if not removed:
            return context.come_back(MSG_NONE_REMOVED)

        objects = ', '.join(removed)
        return context.come_back(MSG_OBJECTS_REMOVED, objects=objects)


    rename_form__access__ = 'is_allowed_to_move'
    def rename_form(self, context):
        # Filter names which the authenticated user is not allowed to move
        ac = self.get_access_control()
        paths = [
            x for x in context.get_form_values('ids')
            if ac.is_allowed_to_move(context.user, self.get_object(x)) ]

        # Check input data
        if not paths:
            return context.come_back(u'No objects selected.')

        # FIXME Hack to get rename working. The current user interface forces
        # the rename_form to be called as a form action, hence with the POST
        # method, but it should be a GET method. Maybe it will be solved after
        # the needed folder browse overhaul.
        if context.request.method == 'POST':
            ids_list = '&'.join([ 'ids=%s' % x for x in paths ])
            return get_reference(';rename_form?%s' % ids_list)

        # Build the namespace
        paths.sort()
        paths.reverse()
        namespace = {}
        namespace['objects'] = []
        for path in paths:
            if '/' in path:
                parent_path, name = path.rsplit('/', 1)
                parent_path += '/'
            else:
                parent_path = ''
                name = path
            namespace['objects'].append({
                'path': path, 'parent_path': parent_path, 'name': name})

        handler = self.get_object('/ui/folder/rename.xml')
        return stl(handler, namespace)


    rename__access__ = 'is_allowed_to_move'
    def rename(self, context):
        paths = context.get_form_values('paths')
        paths.sort()
        paths.reverse()
        new_names = context.get_form_values('new_names')
        # Clean the copy cookie if needed
        cut, cp_paths = context.get_cookie('ikaaro_cp', type=CopyCookie)

        # Process input data
        abspath = self.get_abspath()
        for i, path in enumerate(paths):
            new_name = new_names[i]
            new_name = checkid(new_name)
            if new_name is None:
                return context.come_back(MSG_BAD_NAME)
            # Split the path
            if '/' in path:
                parent_path, old_name = path.rsplit('/', 1)
                container = self.get_object(parent_path)
            else:
                old_name = path
                container = self
            # Check the name really changed
            if new_name == old_name:
                continue
            # Check there is not another resource with the same name
            if container.has_object(new_name):
                return context.come_back(MSG_EXISTANT_FILENAME)
            # Clean cookie (FIXME Do not clean the cookie, update it)
            if cp_paths and str(abspath.resolve2(path)) in cp_paths:
                context.del_cookie('ikaaro_cp')
                cp_paths = []
            # Rename
            container.move_object(old_name, new_name)

        message = u'Objects renamed.'
        return context.come_back(message, goto=';browse_content')


    copy__access__ = 'is_allowed_to_copy'
    def copy(self, context):
        # Filter names which the authenticated user is not allowed to copy
        ac = self.get_access_control()
        names = [
            x for x in context.get_form_values('ids')
            if ac.is_allowed_to_copy(context.user, self.get_object(x)) ]

        # Check input data
        if not names:
            return context.come_back(u'No objects selected.')

        abspath = self.get_abspath()
        cp = (False, [ str(abspath.resolve2(x)) for x in names ])
        cp = CopyCookie.encode(cp)
        context.set_cookie('ikaaro_cp', cp, path='/')

        return context.come_back(u'Objects copied.')


    cut__access__ = 'is_allowed_to_move'
    def cut(self, context):
        # Filter names which the authenticated user is not allowed to move
        ac = self.get_access_control()
        names = [
            x for x in context.get_form_values('ids')
            if ac.is_allowed_to_move(context.user, self.get_object(x)) ]

        # Check input data
        if not names:
            return context.come_back(u'No objects selected.')

        abspath = self.get_abspath()
        cp = (True, [ str(abspath.resolve2(x)) for x in names ])
        cp = CopyCookie.encode(cp)
        context.set_cookie('ikaaro_cp', cp, path='/')

        return context.come_back(u'Objects cut.')


    paste__access__ = 'is_allowed_to_add'
    def paste(self, context):
        cut, paths = context.get_cookie('ikaaro_cp', type=CopyCookie)
        if len(paths) == 0:
            return context.come_back(u'Nothing to paste.')

        root = context.root
        allowed_types = tuple(self.get_document_types())
        for path in paths:
            try:
                object = root.get_object(path)
            except LookupError:
                continue
            if not isinstance(object, allowed_types):
                continue

            # Cut&Paste in the same place (do nothing)
            if cut is True:
                parent = object.parent
                if self.get_canonical_path() == parent.get_canonical_path():
                    continue

            name = generate_name(object.name, self.get_names(), '_copy_')
            if cut is True:
                # Cut&Paste
                self.move_object(path, name)
            else:
                # Copy&Paste
                self.copy_object(path, name)
                # Fix state
                object = self.get_object(name)
                if isinstance(object, WorkflowAware):
                    metadata = object.metadata
                    metadata.set_property('state', object.workflow.initstate)
        # Cut, clean cookie
        if cut is True:
            context.del_cookie('ikaaro_cp')

        return context.come_back(u'Objects pasted.')


    browse_content__access__ = 'is_allowed_to_view'
    browse_content__label__ = u'Contents'
    browse_content__title__ = u"Browse Content"

    def browse_content__sublabel__(self, **kw):
        mode = kw.get('mode', 'list')
        return {'list': u'Browse Content',
                'image': u'Preview Content'}[mode]

    def browse_content__icon__(self, **kw):
        mode = kw.get('mode', 'list')
        return {'list': '/ui/icons/16x16/folder.png',
                'image': '/ui/icons/16x16/image.png'}[mode]

    def browse_content(self, context):
        mode = context.get_form_value('mode', default='list')
        try:
            method = getattr(self, 'browse_%s' % mode)
        except AttributeError:
            method = self.browse_list

        return method(context)


    #######################################################################
    # Add / New Resource
    new_resource_form__access__ = 'is_allowed_to_add'
    new_resource_form__label__ = u'Add'
    def new_resource_form(self, context):
        type = context.get_form_value('type')
        # Type choosen
        if type is not None:
            cls = get_object_class(type)
            return cls.new_instance_form(cls, context)

        # Choose a type
        namespace = {}
        namespace['title'] = self.gettext(u'Add new content')
        namespace['batch'] = None
        namespace['items'] = []

        for cls in self.get_document_types():
            namespace['items'].append({
                'icon': '/ui/' + cls.class_icon48,
                'title': cls.gettext(cls.class_title),
                'description': cls.gettext(cls.class_description),
                'url': ';new_resource_form?type=%s' % quote(cls.class_id)})

        handler = self.get_object('/ui/folder/new_resource.xml')
        return stl(handler, namespace)


    new_resource__access__ = 'is_allowed_to_add'
    def new_resource(self, context):
        class_id = context.get_form_value('class_id')
        cls = get_object_class(class_id)
        return cls.new_instance(cls, self, context)


    #######################################################################
    # Search
    def get_search_criteria(self):
        """Return the criteria as a list of dictionnary
        like [{'id': criteria_id, 'title' : criteria_title},...]
        """
        return self.search_criteria


    #######################################################################
    # Last Changes
    last_changes__access__ = 'is_allowed_to_view'
    last_changes__label__ = u"Last Changes"
    last_changes__title__ = u"Last Changes"
    last_changes__icon__ = 'icalendar.png'
    def last_changes(self, context, sortby=['mtime'], sortorder='down',
                     batchsize=20, action=';last_changes'):
        query = EqQuery('is_version_aware', '1')
        return self.browse_list(context, sortby, sortorder, batchsize, True,
                                action, query)


    #######################################################################
    # Orphans
    #######################################################################
    orphans__access__ = 'is_allowed_to_view'
    orphans__label__ = u"Orphans"
    orphans__sublabel__ = u"Orphans"
    orphans__title__ = u"Orphans"
    orphans__description__ = u"Show objects not linked from anywhere."
    orphans__icon__ = 'orphans.png'
    def orphans(self, context, sortby=['title'], sortorder='up',
                batchsize=20):
        """Orphans are files not referenced in another object of the database.
        It extends the concept of "orphans pages" from the wiki to all
        file-like objects.

        Orphans folders generally don't make sense because they serve as
        containers. TODO or list empty folders?
        """
        root = context.root
        get_form_value = context.get_form_value

        parent_path = str(self.get_canonical_path())
        search_subfolders = get_form_value('search_subfolders', type=Boolean,
                                           default=False)
        if search_subfolders is True:
            base_query = EqQuery('paths', parent_path)
            objects = self.traverse_objects()
        else:
            base_query = EqQuery('parent_path', parent_path)
            objects = self.get_objects()

        orphans = []
        for object in objects:
            if isinstance(object, Folder):
                # TODO consider empty folders?
                continue
            abspath = str(object.get_abspath())
            query = AndQuery(base_query, EqQuery('links', abspath))
            results = root.search(query)
            if not results.get_n_documents():
                orphans.append(abspath)

        if not orphans:
            return self.gettext(u"There is no orphan.")

        args = [EqQuery('abspath', abspath) for abspath in orphans]
        query = OrQuery(*args)

        return self.browse_list(context, sortby, sortorder, batchsize, False,
                                ';orphans', query)


    #######################################################################
    # Update
    #######################################################################
    def update_20071215(self, **kw):
        """Remove empty folders.
        """
        DBObject.update_20071215(self, **kw)
        # Remove empty folders
        if self.parent is None:
            return
        if vfs.exists(self.handler.uri):
            folder = self.parent.handler
            if not folder.get_handler_names(self.name):
                folder.del_handler(self.name)


###########################################################################
# Register
###########################################################################
register_object_class(Folder)
register_object_class(Folder, format="application/x-not-regular-file")
