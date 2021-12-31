import datetime
import hashlib
import json
import logging
import re
from typing import Dict

from pyzabbix import ZabbixMetric

logger = logging.getLogger(__file__)

K8S_RESOURCES = dict(
    nodes='node',
    components='component',
    services='service',
    deployments='deployment',
    statefulsets='statefulset',
    daemonsets='daemonset',
    pods='pod',
    containers='container',
    secrets='secret',
    ingresses='ingress',
    pvcs='pvc'
)

INITIAL_DATE = datetime.datetime(2000, 1, 1, 0, 0)


def json_encoder(obj) -> str:
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"custom json_encoder: unable to encode {type(obj)}")


def transform_value(value: str) -> str:
    if value is None:
        return "0"
    m = re.match(r'^(\d+)(Ki)$', str(value))
    if m:
        if m.group(2) == "Ki":
            return str(int(float(m.group(1)) * 1024))

    m = re.match(r'^(\d+)(m)$', str(value))
    if m:
        if m.group(2) == "m":
            return str(float(m.group(1)) / 1000)

    if value is None:
        return "0"

    return value


def slugit(name_space: str, name: str, maxlen: int) -> str:
    if name_space:
        slug = name_space + '/' + name
    else:
        slug = name

    if len(slug) <= maxlen:
        return slug

    prefix_pos = int((maxlen / 2) - 1)
    suffix_pos = len(slug) - int(maxlen / 2) - 2
    return slug[:prefix_pos] + "~" + slug[suffix_pos:]


def calculate_checksum_for_dict(data: Dict) -> str:
    json_str = json.dumps(
        data,
        sort_keys=True,
        default=json_encoder,
        indent=2
    )
    checksum = hashlib.md5(json_str.encode('utf-8')).hexdigest()
    return checksum


class K8sObject:
    object_type: str = "UNDEFINED"

    def __init__(self, obj_data: Dict, resource: str, manager=None):
        self.is_dirty_zabbix = True
        self.is_dirty_web = True
        self.last_sent_zabbix_discovery = INITIAL_DATE
        self.last_sent_zabbix = INITIAL_DATE
        self.last_sent_web = INITIAL_DATE
        self.resource = resource
        self.data = obj_data
        self.data_checksum = calculate_checksum_for_dict(obj_data)
        self.manager = manager
        self.zabbix_host = self.manager.zabbix_host

    def __str__(self):
        return self.uid

    @property
    def resource_data(self):
        """ customized values for k8s objects """
        return dict(
            name=self.data['metadata']['name'],
            name_space=self.data['metadata']['namespace'],
        )

    @property
    def uid(self):
        if not hasattr(self, 'object_type'):
            raise AttributeError('No object_type set! Dont use K8sObject itself!')
        elif not self.name:
            raise AttributeError('No name set for K8sObject.uid! [%s] name_space: %s, name: %s'
                                 % (self.object_type, self.name_space, self.name))

        if self.name_space:
            return self.object_type + '_' + self.name_space + '_' + self.name
        return self.object_type + '_' + self.name

    @property
    def name(self):
        name = self.data.get('metadata', {}).get('name')
        if not name:
            raise Exception('Could not find name in metadata for resource %s' % self.resource)
        return name

    @property
    def name_space(self):
        from .node import Node
        from .component import Component
        if isinstance(self, Node) or isinstance(self, Component):
            return None

        name_space = self.data.get('metadata', {}).get('namespace')
        if not name_space:
            raise Exception('Could not find name_space for obj [%s] %s' % (self.resource, self.name))
        return name_space

    def is_unsubmitted_web(self):
        return self.last_sent_web == INITIAL_DATE

    def is_unsubmitted_zabbix(self):
        return self.last_sent_zabbix == INITIAL_DATE

    def is_unsubmitted_zabbix_discovery(self):
        return self.last_sent_zabbix_discovery == datetime.datetime(2000, 1, 1, 0, 0)

    def get_zabbix_discovery_data(self):
        return [{
            "{#NAME}": self.name,
            "{#NAMESPACE}": self.name_space,
            "{#SLUG}": slugit(self.name_space, self.name, 40),
        }]

    def get_discovery_for_zabbix(self, discovery_data=None):
        if discovery_data is None:
            discovery_data = self.get_zabbix_discovery_data()

        return ZabbixMetric(
            self.zabbix_host,
            'check_kubernetesd[discover,%s]' % self.resource,
            json.dumps({
                'data': discovery_data,
            })
        )

    def get_zabbix_metrics(self):
        logger.fatal(f"get_zabbix_metrics: not implemented for {self.object_type}")
        return []
