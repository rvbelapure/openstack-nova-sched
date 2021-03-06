# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack, LLC
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import base64

from tempest import exceptions
from tempest.test import attr
from tempest.tests.compute import base


class ServerPersonalityTestJSON(base.BaseComputeTest):
    _interface = 'json'

    @classmethod
    def setUpClass(cls):
        super(ServerPersonalityTestJSON, cls).setUpClass()
        cls.client = cls.servers_client
        cls.user_client = cls.limits_client

    def test_personality_files_exceed_limit(self):
        # Server creation should fail if greater than the maximum allowed
        # number of files are injected into the server.
        file_contents = 'This is a test file.'
        personality = []
        max_file_limit = \
            self.user_client.get_specific_absolute_limit("maxPersonality")
        for i in range(0, int(max_file_limit) + 1):
            path = 'etc/test' + str(i) + '.txt'
            personality.append({'path': path,
                                'contents': base64.b64encode(file_contents)})
        self.assertRaises(exceptions.OverLimit, self.create_server,
                          personality=personality)

    @attr(type='positive')
    def test_can_create_server_with_max_number_personality_files(self):
        # Server should be created successfully if maximum allowed number of
        # files is injected into the server during creation.
        file_contents = 'This is a test file.'
        max_file_limit = \
            self.user_client.get_specific_absolute_limit("maxPersonality")
        person = []
        for i in range(0, int(max_file_limit)):
            path = 'etc/test' + str(i) + '.txt'
            person.append({
                'path': path,
                'contents': base64.b64encode(file_contents),
            })
        resp, server = self.create_server(personality=person)
        self.addCleanup(self.client.delete_server, server['id'])
        self.assertEqual('202', resp['status'])


class ServerPersonalityTestXML(ServerPersonalityTestJSON):
    _interface = "xml"
