# -*- coding: UTF-8 -*-
# Copyright (C) 2016 Sylvain Taverne <taverne.sylvain@gmail.com>
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
from unittest import TestCase, main

# Import from itools
from itools.core import get_abspath
from itools.database import AndQuery, PhraseQuery
from itools.fs import lfs

# Import from ikaaro
from ikaaro.database import get_database
from ikaaro.server import Server, get_fake_context, create_server
from ikaaro.text import Text


class FreeTestCase(TestCase):

    def setUp(self):
        self.tearDown()
        create_server('test_database', 'test@hforge.org',
            'password', 'ikaaro', website_languages=['en', 'fr'])


    def tearDown(self):
        paths = ['test_database']
        for path in paths:
            if lfs.exists(path):
                lfs.remove(path)


    def get_database(self):
        size_min, size_max = 19500, 20500
        path = get_abspath('test_database')
        database = get_database(path, size_min, size_max)
        context = get_fake_context(database)
        context.set_mtime = True
        root = database.get_resource('/')
        return root, context, database


    def test_create_text(self):
        root, context, database = self.get_database()
        # Create 1 resource
        resource = root.make_resource(None, Text)
        self.assertEqual(str(resource.abspath), '/0')
        metadata = resource.metadata
        self.assertEqual(metadata.format, 'text')
        database.save_changes()
        # Check if resource exists
        resource = root.get_resource('0')
        self.assertEqual(resource.name, '0')
        search = context.database.search(abspath='/0')
        self.assertEqual(len(search), 1)
        # Del resource
        root.del_resource('0')
        context.database.save_changes()
        # Check if has been removed
        resource = root.get_resource('0', soft=True)
        self.assertEqual(resource, None)
        search = context.database.search(abspath='/1')
        self.assertEqual(len(search), 0)
        # Close database
        database.close()


    def test_create_user(self):
        root, context, database = self.get_database()
        # Create a new user
        email = 'admin@hforge.org'
        password = 'password'
        user = root.make_user(email, password)
        self.assertEqual(user.name, '1')
        user.set_value('groups', ['/config/groups/admins'])
        database.save_changes()
        # Try to get user
        user = root.get_resource('/users/1', soft=True)
        self.assertEqual(user.name, '1')
        self.assertEqual(user.get_value('email'), 'admin@hforge.org')
        self.assertEqual(user.authenticate(password), True)
        self.assertEqual(user.authenticate('badpassword'), False)
        # Cannot create 2 users with the same email address
        user = root.make_user(email, password)
        self.assertEqual(user, None)


    def test_multilingual_search(self):
        root, context, database = self.get_database()
        # Create N resources
        for i in range(0, 20):
            kw =  {'title':   {'fr': u'Bonjour', 'en': u'Hello'}}
            root.make_resource(str(i), Text, **kw)
        database.save_changes()
        # Check if resource exists
        query = PhraseQuery('format', 'text')
        search = context.database.search(query)
        self.assertEqual(len(search), 20)
        # Check if resource exists
        query = AndQuery(
            PhraseQuery('format', 'text'),
            PhraseQuery('title', u'Hello'))
        search = context.database.search(query)
        self.assertEqual(len(search), 20)
        query = AndQuery(
            PhraseQuery('format', 'text'),
            PhraseQuery('title_en', u'Hello'))
        search = context.database.search(query)
        self.assertEqual(len(search), 20)
        query = AndQuery(
            PhraseQuery('format', 'text'),
            PhraseQuery('title_fr', u'Bonjour'))
        search = context.database.search(query)
        self.assertEqual(len(search), 20)
        query = AndQuery(
            PhraseQuery('format', 'text'),
            PhraseQuery('title_es', u'Hola'))
        search = context.database.search(query)
        self.assertEqual(len(search), 0)
        # Close database
        database.close()


    def test_move_file(self):
        root, context, database = self.get_database()
        kw =  {'title': {'fr': u'Bonjour', 'en': u'Hello'},
               'data': 'this is text'}
        resource = root.make_resource(None, Text, **kw)
        self.assertEqual(str(resource.abspath), '/0')
        database.save_changes()
        # Move '/0' to '/1'
        root.move_resource('0', '1')
        self.assertEqual(root.get_resource('0', soft=True), None)
        self.assertEqual(root.get_resource('1').name, '1')
        # Move '/1' to '/1'
        root.move_resource('1', '1')
        self.assertEqual(root.get_resource('1').name, '1')
        # Check text
        r1 = root.get_resource('1')
        data = r1.get_value('data').to_str()
        self.assertEqual(data, 'this is text')
        database.close()


    def test_abort_transaction(self):
        root, context, database = self.get_database()
        kw =  {'title': {'fr': u'Bonjour', 'en': u'Hello'},
               'data': 'this is text'}
        resource = root.make_resource(None, Text, **kw)
        self.assertEqual(str(resource.abspath), '/0')
        self.assertNotEqual(root.get_resource('/0'), None)
        database.save_changes()
        resource = root.make_resource(None, Text, **kw)
        self.assertEqual(str(resource.abspath), '/1')
        database.catalog.index_document({'abspath': '/2'})
        database.abort_changes()
        self.assertNotEqual(root.get_resource('/0'), None)
        self.assertEqual(root.get_resource('/1', soft=True), None)
        database.close()


    def test_close_transaction(self):
        """
        Test if flush is done when we close database
        """
        root, context, database = self.get_database()
        kw =  {'title': {'fr': u'Bonjour', 'en': u'Hello'},
               'data': 'this is text'}
        resource = root.make_resource(None, Text, **kw)
        self.assertEqual(str(resource.abspath), '/0')
        database.save_changes()
        query = PhraseQuery('format', 'text')
        search = context.database.search(query)
        self.assertEqual(len(search), 1)
        resource = root.make_resource(None, Text)
        database.close()
        root, context, database = self.get_database()
        query = PhraseQuery('format', 'text')
        search = context.database.search(query)
        self.assertEqual(len(search), 1)
        self.assertEqual(root.get_resource('/1', soft=True), None)



    def test_server(self):
        server = Server('test_database')
        root = server.database.get_resource('/')
        self.assertEqual(root.metadata.format, 'iKaaro')


if __name__ == '__main__':
    main()
