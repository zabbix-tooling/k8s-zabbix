import datetime
import hashlib
import importlib
import json
import logging
import re

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


def json_encoder(obj) -> str:
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise Exception("unable to encode")


def transform_value(value: str) -> str:
    if value is None:
        return 0
    m = re.match(r'^(\d+)(Ki)$', str(value))
    if m:
        if m.group(2) == "Ki":
            return str(int(float(m.group(1)) * 1024))

    m = re.match(r'^(\d+)(m)$', str(value))
    if m:
        if m.group(2) == "m":
            return str(float(m.group(1)) / 1000)
    return value


def slugit(name_space, name, maxlen):
    if name_space:
        slug = name_space + '/' + name
    else:
        slug = name

    if len(slug) <= maxlen:
        return slug

    prefix_pos = int((maxlen / 2) - 1)
    suffix_pos = len(slug) - int(maxlen / 2) - 2
    return slug[:prefix_pos] + "~" + slug[suffix_pos:]


class K8sResourceManager:
    def __init__(self, resource, zabbix_host=None):
        self.resource = resource
        self.zabbix_host = zabbix_host

        self.objects = dict()
        self.containers = dict()  # containers only used for pods

        mod = importlib.import_module('k8sobjects')
        class_label = K8S_RESOURCES[resource]
        self.resource_class = getattr(mod, class_label.capitalize(), None)

    def add_obj(self, obj):
        if not self.resource_class:
            logger.error('No Resource Class found for "%s"' % self.resource)
            return

        new_obj = self.resource_class(obj, self.resource, manager=self)
        if new_obj.uid not in self.objects:
            # new object
            self.objects[new_obj.uid] = new_obj
        elif self.objects[new_obj.uid].data_checksum != new_obj.data_checksum:
            # existing object with modified data
            new_obj.last_sent_zabbix_discovery = self.objects[new_obj.uid].last_sent_zabbix_discovery
            new_obj.last_sent_zabbix = self.objects[new_obj.uid].last_sent_zabbix
            new_obj.last_sent_web = self.objects[new_obj.uid].last_sent_web
            new_obj.is_dirty_web = True
            new_obj.is_dirty_zabbix = True
            self.objects[new_obj.uid] = new_obj

        # return created or updated object
        return self.objects[new_obj.uid]

    def del_obj(self, obj):
        if not self.resource_class:
            logger.error('No Resource Class found for "%s"' % self.resource)
            return

        resourced_obj = self.resource_class(obj, self.resource, manager=self)
        if resourced_obj.uid in self.objects:
            del self.objects[resourced_obj.uid]
        return resourced_obj


INITIAL_DATE = datetime.datetime(2000, 1, 1, 0, 0)


class K8sObject:
    def __init__(self, obj_data, resource, manager=None):
        self.is_dirty_zabbix = True
        self.is_dirty_web = True
        self.last_sent_zabbix_discovery = INITIAL_DATE
        self.last_sent_zabbix = INITIAL_DATE
        self.last_sent_web = INITIAL_DATE
        self.resource = resource
        self.data = obj_data
        self.data_checksum = self.calculate_checksum()
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

    def calculate_checksum(self):
        return hashlib.md5(
            json.dumps(
                self.data,
                sort_keys=True,
                default=json_encoder,
            ).encode('utf-8')
        ).hexdigest()

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
        return []
