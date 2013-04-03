# Copyright 2012 Hewlett-Packard Development Company, L.P. All Rights Reserved.
#
# Author: Kiall Mac Innes <kiall@hp.com>
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
import flask
from moniker.openstack.common import log as logging
from moniker.openstack.common.rpc import common as rpc_common
from moniker import exceptions
from moniker.central import rpcapi as central_rpcapi

LOG = logging.getLogger(__name__)
central_api = central_rpcapi.CentralAPI()
blueprint = flask.Blueprint('sync', __name__)


@blueprint.route('/domains/sync', methods=['POST'])
def sync_domains():
    context = flask.request.environ.get('context')

    try:
        central_api.sync_domains(context)
    except exceptions.Forbidden:
        return flask.Response(status=401)
    except rpc_common.Timeout:
        return flask.Response(status=504)
    else:
        return flask.Response(status=200)


@blueprint.route('/domains/<domain_id>/sync', methods=['POST'])
def sync_domain(domain_id):
    context = flask.request.environ.get('context')

    try:
        central_api.sync_domain(context, domain_id)
    except exceptions.Forbidden:
        return flask.Response(status=401)
    except exceptions.DomainNotFound:
        return flask.Response(status=404)
    except rpc_common.Timeout:
        return flask.Response(status=504)
    else:
        return flask.Response(status=200)


@blueprint.route('/domains/<domain_id>/records/<record_id>/sync',
                 methods=['POST'])
def sync_record(domain_id, record_id):
    context = flask.request.environ.get('context')

    try:
        central_api.sync_record(context, domain_id, record_id)
    except exceptions.Forbidden:
        return flask.Response(status=401)
    except exceptions.RecordNotFound:
        return flask.Response(status=404)
    except rpc_common.Timeout:
        return flask.Response(status=504)
    else:
        return flask.Response(status=200)