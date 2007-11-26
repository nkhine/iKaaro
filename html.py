# -*- coding: UTF-8 -*-
# Copyright (C) 2006-2007 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2006-2007 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2007 Nicolas Deram <nicolas@itaapy.com>
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
from datetime import datetime
from HTMLParser import HTMLParseError

# Import from itools
from itools.datatypes import DateTime
from itools.html import XHTMLFile, sanitize_stream, HTMLParser
from itools.stl import stl
from itools.xml import TEXT, START_ELEMENT

# Import from ikaaro
from messages import *
from text import Text
from registry import register_object_class


class EpozEditable(object):
    """A mixin class for handlers implementing HTML editing.
    """

    #######################################################################
    # API
    #######################################################################
    def get_epoz_document(self):
        # Implement it in your editable handler
        raise NotImplementedError


    def get_epoz_data(self):
        document = self.get_epoz_document()
        body = document.get_body()
        if body is None:
            return None
        return body.get_content_elements()


    #######################################################################
    # User Interface
    #######################################################################
    edit_form__access__ = 'is_allowed_to_edit'
    edit_form__label__ = u'Edit'
    edit_form__sublabel__ = u'Inline'
    def edit_form(self, context):
        """WYSIWYG editor for HTML documents.
        """
        data = self.get_epoz_data()
        # If the document has not a body (e.g. a frameset), edit as plain text
        if data is None:
            return Text.edit_form(self, context)

        # Edit with a rich text editor
        namespace = {}
        namespace['timestamp'] = DateTime.encode(datetime.now())
        namespace['rte'] = self.get_rte(context, 'data', data)

        handler = self.get_object('/ui/html/edit.xml')
        return stl(handler, namespace)


    edit__access__ = 'is_allowed_to_edit'
    def edit(self, context, sanitize=False):
        timestamp = context.get_form_value('timestamp', type=DateTime)
        if timestamp is None:
            return context.come_back(MSG_EDIT_CONFLICT)
        document = self.get_epoz_document()
        if document.timestamp is not None and timestamp < document.timestamp:
            return context.come_back(MSG_EDIT_CONFLICT)

        # Sanitize
        new_body = context.get_form_value('data')
        try:
            new_body = HTMLParser(new_body)
        except HTMLParseError:
            return context.come_back(u'Invalid HTML code.')
        if sanitize:
            new_body = sanitize_stream(new_body)
        # "get_epoz_document" is to set in your editable handler
        old_body = document.get_body()
        events = (document.events[:old_body.start+1] + new_body
                  + document.events[old_body.end:])
        # Change
        document.set_events(events)
        context.server.change_object(self)

        return context.come_back(MSG_CHANGES_SAVED)



class WebPage(EpozEditable, Text):

    class_id = 'application/xhtml+xml'
    class_title = u'Web Page'
    class_description = u'Create and publish a Web Page.'
    class_icon16 = 'images/HTML16.png'
    class_icon48 = 'images/HTML48.png'
    class_views = [['view'],
                   ['edit_form', 'externaledit', 'upload_form'],
                   ['edit_metadata_form'],
                   ['state_form'],
                   ['history_form']]
    class_handler = XHTMLFile


    def __init__(self, metadata):
        self.metadata = metadata
        self.handlers = {}
        # The tree
        self.name = ''
        self.parent = None


    def get_handler(self, language=None):
        # Content language
        if language is None:
            language = self.get_content_language()
        # Hit
        if language in self.handlers:
            return self.handlers[language]
        # Miss
        cls = self.class_handler
        database = self.metadata.database
        uri = self.metadata.uri.resolve('%s.%s' % (self.name, language))
        if database.has_handler(uri):
            handler = database.get_handler(uri, cls=cls)
        else:
            handler = cls()
            handler.database = database
            handler.uri = uri
            handler.timestamp = None
            handler.dirty = True
            database.cache[uri] = handler

        self.handlers[language] = handler
        return handler

    handler = property(get_handler, None, None, '')


    def get_all_handlers(self):
        site_root = self.get_site_root()
        languages = site_root.get_property('ikaaro:website_languages')
        return [ self.get_handler(language=x) for x in languages ]


    #######################################################################
    # API
    #######################################################################
    def to_text(self):
        text = [ x.to_text() for x in self.get_all_handlers() ]
        return ' '.join(text)


    GET__mtime__ = None
    def GET(self, context):
        method = self.get_firstview()
        # Check access
        if method is None:
            raise Forbidden
        # Redirect
        return context.uri.resolve2(';%s' % method)


    def is_empty(self):
        """Test if XML doc is empty
        """
        body = self.get_body()
        if body is None:
            return True
        for type, value, line in body.events:
            if type == TEXT:
                if value.replace('&nbsp;', '').strip():
                    return False
            elif type == START_ELEMENT:
                tag_uri, tag_name, attributes = value
                if tag_name == 'img':
                    return False
        return True


    #######################################################################
    # UI / View
    #######################################################################
    view__access__ = 'is_allowed_to_view'
    view__label__ = u'View'
    view__title__ = u'View'
    def view(self, context):
        namespace = {}
        body = self.handler.get_body()
        if body is None:
            namespace['text'] = None
        else:
            namespace['text'] = body.get_content_elements()

        handler = self.get_object('/ui/html/view.xml')
        return stl(handler, namespace)


    #######################################################################
    # UI / Edit / Inline
    #######################################################################
    def get_epoz_document(self):
        return self.handler



class HTMLFile(WebPage):

    class_id = 'text/html'



###########################################################################
# Register
###########################################################################
register_object_class(WebPage)
register_object_class(HTMLFile)
