# vim: tabstop=4 shiftwidth=4 softtabstop=4
# coding=utf-8

# Copyright 2012 Hewlett-Packard Development Company, L.P.
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

"""Tests for baremetal virtual power driver."""

import mox
from oslo.config import cfg

from nova import exception
from nova.tests.baremetal.db import base as bm_db_base
from nova.tests.baremetal.db import utils as bm_db_utils
from nova.tests.image import fake as fake_image
from nova.tests import utils
from nova import utils as nutils
from nova.virt.baremetal import db
from nova.virt.baremetal import virtual_power_driver
import nova.virt.powervm.common as connection

CONF = cfg.CONF

COMMON_FLAGS = dict(
    firewall_driver='nova.virt.baremetal.fake.FakeFirewallDriver',
    host='test_host',
)

BAREMETAL_FLAGS = dict(
    driver='nova.virt.baremetal.pxe.PXE',
    instance_type_extra_specs=['cpu_arch:test', 'test_spec:test_value'],
    power_manager=
        'nova.virt.baremetal.virtual_power_driver.VirtualPowerManager',
    vif_driver='nova.virt.baremetal.fake.FakeVifDriver',
    volume_driver='nova.virt.baremetal.fake.FakeVolumeDriver',
    virtual_power_ssh_host=None,
    virtual_power_type='vbox',
    virtual_power_host_user=None,
    virtual_power_host_pass=None,
    virtual_power_host_key=None,
    group='baremetal',
)


class BareMetalVPDTestCase(bm_db_base.BMDBTestCase):

    def setUp(self):
        super(BareMetalVPDTestCase, self).setUp()
        self.flags(**COMMON_FLAGS)
        self.flags(**BAREMETAL_FLAGS)

        fake_image.stub_out_image_service(self.stubs)
        self.context = utils.get_test_admin_context()
        self.test_block_device_info = None,
        self.instance = utils.get_test_instance()
        self.test_network_info = utils.get_test_network_info(),
        self.node_info = bm_db_utils.new_bm_node(
                id=123,
                service_host='test_host',
                cpus=2,
                memory_mb=2048,
                prov_mac_address='11:11:11:11:11:11',
            )
        self.nic_info = [
                {'address': '22:22:22:22:22:22', 'datapath_id': '0x1',
                    'port_no': 1},
                {'address': '33:33:33:33:33:33', 'datapath_id': '0x2',
                    'port_no': 2},
            ]
        self.addCleanup(fake_image.FakeImageService_reset)

    def _create_node(self):
        self.node = db.bm_node_create(self.context, self.node_info)
        for nic in self.nic_info:
            db.bm_interface_create(
                                    self.context,
                                    self.node['id'],
                                    nic['address'],
                                    nic['datapath_id'],
                                    nic['port_no'],
                )
        self.instance['node'] = self.node['id']

    def _create_pm(self):
        self.pm = virtual_power_driver.VirtualPowerManager(
                        node=self.node,
                        instance=self.instance)
        return self.pm


class VPDMissingOptionsTestCase(BareMetalVPDTestCase):

    def test_get_conn_missing_options(self):
        self.flags(virtual_power_ssh_host=None, group="baremetal")
        self.flags(virtual_power_host_user=None, group="baremetal")
        self.flags(virtual_power_host_pass=None, group="baremetal")
        self._create_node()
        self._create_pm()
        self._conn = None
        self.assertRaises(exception.NovaException,
                self.pm._get_conn)
        self._conn = None
        self.flags(virtual_power_ssh_host='127.0.0.1', group="baremetal")
        self.assertRaises(exception.NovaException,
                self.pm._get_conn)
        self._conn = None
        self.flags(virtual_power_host_user='user', group="baremetal")
        self.assertRaises(exception.NovaException,
                self.pm._get_conn)


class VPDClassMethodsTestCase(BareMetalVPDTestCase):

    def setUp(self):
        super(VPDClassMethodsTestCase, self).setUp()
        self.flags(virtual_power_ssh_host='127.0.0.1', group="baremetal")
        self.flags(virtual_power_host_user='user', group="baremetal")
        self.flags(virtual_power_host_pass='password', group="baremetal")

    def test_get_conn_success_pass(self):
        self._create_node()
        self._create_pm()
        self._conn = self.pm._get_conn()
        self.mox.StubOutWithMock(connection, 'ssh_connect')
        connection.ssh_connect(mox.IsA(self._conn)).AndReturn(True)
        self.mox.ReplayAll()
        self.pm._set_connection()
        self.assertEqual(self.pm.connection_data.host, '127.0.0.1')
        self.assertEqual(self.pm.connection_data.username, 'user')
        self.assertEqual(self.pm.connection_data.password, 'password')
        self.assertEqual(self.pm.connection_data.keyfile, None)
        self.mox.VerifyAll()

    def test_get_conn_success_key(self):
        self.flags(virtual_power_host_pass='', group="baremetal")
        self.flags(virtual_power_host_key='/id_rsa_file.txt',
            group="baremetal")
        self._create_node()
        self._create_pm()
        self._conn = self.pm._get_conn()
        self.mox.StubOutWithMock(connection, 'ssh_connect')
        connection.ssh_connect(mox.IsA(self._conn)).AndReturn(True)
        self.mox.ReplayAll()
        self.pm._set_connection()
        self.assertEqual(self.pm.connection_data.host, '127.0.0.1')
        self.assertEqual(self.pm.connection_data.username, 'user')
        self.assertEqual(self.pm.connection_data.password, '')
        self.assertEqual(self.pm.connection_data.keyfile, '/id_rsa_file.txt')
        self.mox.VerifyAll()

    def test_get_full_node_list(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_run_command')
        cmd = self.pm._vp_cmd.list_cmd
        self.pm._run_command(cmd).AndReturn("testNode")

        self.mox.ReplayAll()
        name = self.pm._get_full_node_list()
        self.assertEqual(name, 'testNode')
        self.mox.VerifyAll()

    def test_check_for_node(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_get_full_node_list')
        self.pm._get_full_node_list().\
                AndReturn(["testNode"])

        self.mox.StubOutWithMock(self.pm, '_run_command')
        cmd = self.pm._vp_cmd.get_node_macs.replace('{_NodeName_}', 'testNode')
        self.pm._run_command(cmd).\
                AndReturn(["111111111111", "ffeeddccbbaa"])

        self.mox.ReplayAll()
        name = self.pm._check_for_node()
        self.assertEqual(name, '"testNode"')
        self.mox.VerifyAll()

    def test_check_for_node_not_found(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_get_full_node_list')
        self.pm._get_full_node_list().AndReturn(["testNode"])

        self.mox.StubOutWithMock(self.pm, '_run_command')
        cmd = self.pm._vp_cmd.get_node_macs.replace('{_NodeName_}', 'testNode')
        self.pm._run_command(cmd).AndReturn(["aabbccddeeff", "ffeeddccbbaa"])

        self.mox.ReplayAll()
        name = self.pm._check_for_node()
        self.assertEqual(name, '')
        self.mox.VerifyAll()

    def test_activate_node(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.mox.StubOutWithMock(self.pm, 'is_power_on')
        self.pm._check_for_node().AndReturn('"testNode"')
        self.pm._run_command(self.pm._vp_cmd.start_cmd).AndReturn("Started")
        self.pm.is_power_on().AndReturn(True)
        self.mox.ReplayAll()
        state = self.pm.activate_node()
        self.assertEqual(state, 'active')
        self.mox.VerifyAll()

    def test_activate_node_fail(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.mox.StubOutWithMock(self.pm, 'is_power_on')
        self.pm._check_for_node().AndReturn('"testNode"')
        self.pm._run_command(self.pm._vp_cmd.start_cmd).AndReturn("Started")
        self.pm.is_power_on().AndReturn(False)
        self.mox.ReplayAll()
        state = self.pm.activate_node()
        self.assertEqual(state, 'error')
        self.mox.VerifyAll()

    def test_deactivate_node(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.mox.StubOutWithMock(self.pm, 'is_power_on')
        self.pm._check_for_node().AndReturn('"testNode"')
        self.pm.is_power_on().AndReturn(True)
        self.pm._run_command(self.pm._vp_cmd.stop_cmd).AndReturn("Stopped")
        self.pm.is_power_on().AndReturn(False)
        self.mox.ReplayAll()
        state = self.pm.deactivate_node()
        self.assertEqual(state, 'deleted')
        self.mox.VerifyAll()

    def test_deactivate_node_fail(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.mox.StubOutWithMock(self.pm, 'is_power_on')
        self.pm._check_for_node().AndReturn('"testNode"')
        self.pm.is_power_on().AndReturn(True)
        self.pm._run_command(self.pm._vp_cmd.stop_cmd).AndReturn("Stopped")
        self.pm.is_power_on().AndReturn(True)
        self.mox.ReplayAll()
        state = self.pm.deactivate_node()
        self.assertEqual(state, 'error')
        self.mox.VerifyAll()

    def test_reboot_node(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.mox.StubOutWithMock(self.pm, 'is_power_on')
        self.pm._check_for_node().AndReturn(['"testNode"'])
        self.pm._run_command(self.pm._vp_cmd.reboot_cmd).AndReturn("Restarted")
        self.pm.is_power_on().AndReturn(True)
        self.mox.ReplayAll()
        state = self.pm.reboot_node()
        self.assertEqual(state, 'active')
        self.mox.VerifyAll()

    def test_reboot_node_fail(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.mox.StubOutWithMock(self.pm, 'is_power_on')
        self.pm._check_for_node().AndReturn(['"testNode"'])
        self.pm._run_command(self.pm._vp_cmd.reboot_cmd).AndReturn("Restarted")
        self.pm.is_power_on().AndReturn(False)
        self.mox.ReplayAll()
        state = self.pm.reboot_node()
        self.assertEqual(state, 'error')
        self.mox.VerifyAll()

    def test_is_power_on(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.pm._check_for_node().AndReturn(['"testNode"'])
        self.pm._run_command(self.pm._vp_cmd.list_running_cmd).\
                AndReturn(['"testNode"'])
        self.pm._matched_name = 'testNode'
        self.mox.ReplayAll()
        state = self.pm.is_power_on()
        self.assertEqual(state, True)
        self.mox.VerifyAll()

    def test_is_power_on_fail(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.pm._check_for_node().AndReturn(['"NotFoundNode"'])
        self.pm._run_command(self.pm._vp_cmd.list_running_cmd).\
                AndReturn(['"NotFoundNode"'])
        self.pm._matched_name = 'testNode'
        self.mox.ReplayAll()
        state = self.pm.is_power_on()
        self.assertEqual(state, False)
        self.mox.VerifyAll()

    def test_is_power_on_match_subname(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(self.pm, '_run_command')
        self.pm._check_for_node().AndReturn(['"testNode"'])
        self.pm._run_command(self.pm._vp_cmd.list_running_cmd).\
                AndReturn(['"testNode01"'])
        self.pm._matched_name = '"testNode"'
        self.mox.ReplayAll()
        state = self.pm.is_power_on()
        self.assertEqual(state, False)
        self.mox.VerifyAll()

    def test_run_command(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_set_connection')
        self.mox.StubOutWithMock(nutils, 'ssh_execute')
        self.pm._set_connection().AndReturn(True)
        nutils.ssh_execute(None, '/usr/bin/VBoxManage test return',
                check_exit_code=True).AndReturn(("test\nreturn", ""))
        self.pm._matched_name = 'testNode'
        self.mox.ReplayAll()
        result = self.pm._run_command("test return")
        self.assertEqual(result, ['test', 'return'])
        self.mox.VerifyAll()

    def test_run_command_raises_exception(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_set_connection')
        self.mox.StubOutWithMock(nutils, 'ssh_execute')

        self.pm._set_connection().AndReturn(True)
        nutils.ssh_execute(None, '/usr/bin/VBoxManage test return',
                check_exit_code=True).\
                AndRaise(exception.ProcessExecutionError)
        self.mox.ReplayAll()

        result = self.pm._run_command("test return")
        self.assertEqual(result, [])
        self.mox.VerifyAll()

    def test_activate_node_with_exception(self):
        self._create_node()
        self._create_pm()

        self.mox.StubOutWithMock(self.pm, '_check_for_node')
        self.mox.StubOutWithMock(nutils, 'ssh_execute')

        self.pm._check_for_node().AndReturn(['"testNode"'])
        self.pm._check_for_node().AndReturn(['"testNode"'])
        nutils.ssh_execute('test', '/usr/bin/VBoxManage startvm ',
                check_exit_code=True).\
                AndRaise(exception.ProcessExecutionError)
        nutils.ssh_execute('test', '/usr/bin/VBoxManage list runningvms',
                check_exit_code=True).\
                AndRaise(exception.ProcessExecutionError)

        self.mox.ReplayAll()
        self.pm._connection = 'test'
        state = self.pm.activate_node()
        self.assertEqual(state, 'error')
        self.mox.VerifyAll()
