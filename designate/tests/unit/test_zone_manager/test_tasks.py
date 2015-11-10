# Copyright 2015 Hewlett-Packard Development Company, L.P.
#
# Author: Endre Karlson <endre.karlson@hp.com>
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
import datetime
import uuid

import mock
from oslotest import base as test
from oslo_utils import timeutils
import six
import testtools

from designate.central import rpcapi as central_api
from designate import context
from designate import rpc
from designate.zone_manager import tasks


class RoObject(object):
    """Read-only object: raise exception on unexpected
    __setitem__ or __setattr__
    """
    def __init__(self, d=None, **kw):
        if d:
            kw.update(d)

        self.__dict__.update(kw)

    def __getitem__(self, k):
        try:
            return self.__dict__[k]
        except KeyError:
            raise NotImplementedError(
                "Attempt to perform __getitem__"
                " %r on RoObject %r" % (k, self.__dict__)
            )

    def __setitem__(self, k, v):
        raise NotImplementedError(
            "Attempt to perform __setitem__ or __setattr__"
            " %r on RoObject %r" % (k, self.__dict__)
        )

    def __setattr__(self, k, v):
        self.__setitem__(k, v)

    def __iter__(self):
        for k in six.iterkeys(self.__dict__):
            yield k, self.__dict__[k]


class DummyTask(tasks.PeriodicTask):
    """Dummy task used to test helper functions"""
    __plugin_name__ = 'dummy'


class TaskTest(test.BaseTestCase):
    def setup_opts(self, config):
        opts = RoObject(**config)

        self.opts = opts
        self.opts_patcher = mock.patch('oslo_config.cfg.CONF')

        self.opts_mock = self.opts_patcher.start()
        self.opts_mock.__getitem__.side_effect = lambda n: opts[n]


class PeriodicTest(TaskTest):
    def setUp(self):
        super(PeriodicTest, self).setUp()

        opts = {
            "zone_manager_task:dummy": RoObject({
                "per_page": 100,
            })
        }
        self.setup_opts(opts)

        self.task = DummyTask()
        self.task.my_partitions = range(0, 10)

    @mock.patch.object(central_api.CentralAPI, 'get_instance')
    def test_iter_zones_no_items(self, get_central):
        # Test that the iteration code is working properly.
        central = mock.Mock()
        get_central.return_value = central

        ctxt = mock.Mock()
        iterer = self.task._iter_zones(ctxt)

        central.find_zones.return_value = []

        with testtools.ExpectedException(StopIteration):
            next(iterer)

    @mock.patch.object(central_api.CentralAPI, 'get_instance')
    def test_iter_zones(self, get_central):
        # Test that the iteration code is working properly.
        central = mock.Mock()
        get_central.return_value = central

        ctxt = mock.Mock()
        iterer = self.task._iter_zones(ctxt)

        items = [RoObject(id=str(uuid.uuid4())) for i in range(0, 5)]
        central.find_zones.return_value = items

        # Iterate through the items causing the "paging" to be done.
        map(lambda i: next(iterer), items)
        central.find_zones.assert_called_once_with(
            ctxt, {"shard": "BETWEEN 0,9"}, limit=100)

        central.find_zones.reset_mock()

        # Call next on the iterator and see it trying to load a new page.
        # Also this will raise a StopIteration since there are no more items.
        central.find_zones.return_value = []
        with testtools.ExpectedException(StopIteration):
            next(iterer)

        central.find_zones.assert_called_once_with(
            ctxt,
            {"shard": "BETWEEN 0,9"},
            marker=items[-1].id,
            limit=100)

    def test_my_range(self):
        self.assertEqual((0, 9), self.task._my_range())


class PeriodicExistsTest(TaskTest):
    def setUp(self):
        super(PeriodicExistsTest, self).setUp()

        opts = {
            "zone_manager_task:periodic_exists": RoObject({
                "per_page": 100,
                "interval": 5
            })
        }
        self.setup_opts(opts)

        # Mock a ctxt...
        self.ctxt = mock.Mock()
        get_admin_ctxt_patcher = mock.patch.object(context.DesignateContext,
                                            'get_admin_context')
        get_admin_context = get_admin_ctxt_patcher.start()
        get_admin_context.return_value = self.ctxt

        # Patch get_notifier so that it returns a mock..
        get_notifier_patcher = mock.patch.object(rpc, 'get_notifier')
        get_notifier = get_notifier_patcher.start()
        self.mock_notifier = mock.Mock()
        get_notifier.return_value = self.mock_notifier

        self.task = tasks.PeriodicExistsTask()
        self.task.my_partitions = range(0, 10)

        # Install our own period results to verify that the end / start is
        # correct below
        self.period = tasks.PeriodicExistsTask._get_period(2)
        self.period_data = {
            "audit_period_beginning": str(self.period[0]),
            "audit_period_ending": str(self.period[1])
        }
        get_period_patcher = mock.patch.object(
            tasks.PeriodicExistsTask, '_get_period')
        self.get_period = get_period_patcher.start()
        self.get_period.return_value = self.period

    def test_emit_exists(self):
        zone = RoObject(
            id=str(uuid.uuid4()))

        with mock.patch.object(self.task, '_iter_zones') as iter_:
            iter_.return_value = [zone]
            self.task()

        data = dict(zone)
        data.update(self.period_data)

        self.mock_notifier.info.assert_called_with(
            self.ctxt, "dns.domain.exists", data)

    def test_emit_exists_no_zones(self):
        with mock.patch.object(self.task, '_iter_zones') as iter_:
            iter_.return_value = []
            self.task()

        self.assertFalse(self.mock_notifier.info.called)

    def test_emit_exists_multiple_zones(self):
        zones = [RoObject() for i in range(0, 10)]
        with mock.patch.object(self.task, '_iter_zones') as iter_:
            iter_.return_value = zones
            self.task()

        for z in zones:
            data = dict(z)
            data.update(self.period_data)
            self.mock_notifier.info.assert_called_with(
                self.ctxt, "dns.domain.exists", data)


class PeriodicSecondaryRefreshTest(TaskTest):
    def setUp(self):
        super(PeriodicSecondaryRefreshTest, self).setUp()

        opts = {
            "zone_manager_task:periodic_secondary_refresh": RoObject({
                "per_page": 100
            })
        }
        self.setup_opts(opts)

        # Mock a ctxt...
        self.ctxt = mock.Mock()
        get_admin_ctxt_patcher = mock.patch.object(context.DesignateContext,
                                                   'get_admin_context')
        get_admin_context = get_admin_ctxt_patcher.start()
        get_admin_context.return_value = self.ctxt

        # Mock a central...
        self.central = mock.Mock()
        get_central_patcher = mock.patch.object(central_api.CentralAPI,
                                        'get_instance')
        get_central = get_central_patcher.start()
        get_central.return_value = self.central

        self.task = tasks.PeriodicSecondaryRefreshTask()
        self.task.my_partitions = 0, 9

    def test_refresh_no_zone(self):
        with mock.patch.object(self.task, '_iter') as _iter:
            _iter.return_value = []
            self.task()

        self.assertFalse(self.central.xfr_zone.called)

    def test_refresh_zone(self):
        transferred = timeutils.utcnow(True) - datetime.timedelta(minutes=62)
        zone = RoObject(
            id=str(uuid.uuid4()),
            transferred_at=datetime.datetime.isoformat(transferred),
            refresh=3600)

        with mock.patch.object(self.task, '_iter') as _iter:
            _iter.return_value = [zone]
            self.task()

        self.central.xfr_zone.assert_called_once_with(self.ctxt, zone.id)

    def test_refresh_zone_not_expired(self):
        # Dummy zone object
        transferred = timeutils.utcnow(True) - datetime.timedelta(minutes=50)
        zone = RoObject(
            id=str(uuid.uuid4()),
            transferred_at=datetime.datetime.isoformat(transferred),
            refresh=3600)

        with mock.patch.object(self.task, '_iter') as _iter:
            _iter.return_value = [zone]
            self.task()

        self.assertFalse(self.central.xfr_zone.called)
