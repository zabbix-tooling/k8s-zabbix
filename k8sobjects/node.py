import logging

import cachetools.func
from pyzabbix import ZabbixMetric
from .k8sobject import K8sObject, transform_value

logger = logging.getLogger(__file__)


# TODO: remove after refactoring
@cachetools.func.ttl_cache(maxsize=1, ttl=60*10)
def get_node_names(api):
    ret = api.list_node(watch=False)
    nodenames = []
    for item in ret.items:
        nodenames.append(item.metadata.name)
    return nodenames


class Node(K8sObject):
    object_type = 'node'

    MONITOR_VALUES = ['allocatable.cpu',
                      'allocatable.ephemeral-storage',
                      'allocatable.memory',
                      'allocatable.pods',
                      'capacity.cpu',
                      'capacity.ephemeral-storage',
                      'capacity.memory',
                      'capacity.pods']

    @property
    def resource_data(self):
        data = super().resource_data

        failed_conds = []
        data['condition_ready'] = False
        for cond in self.data['status']['conditions']:
            if cond['type'].lower() == "ready" and cond['status'] == 'True':
                data['condition_ready'] = True
            else:
                if cond['status'] == 'True':
                    failed_conds.append(cond['type'])

        data['failed_conds'] = failed_conds

        for monitor_value in self.MONITOR_VALUES:
            current_indirection = self.data['status']
            for key in monitor_value.split("."):
                current_indirection = current_indirection[key]

            data[monitor_value] = transform_value(current_indirection)

        return data

    def get_zabbix_metrics(self):
        data_to_send = list()
        data = self.resource_data

        data_to_send.append(
            ZabbixMetric(self.zabbix_host, 'check_kubernetesd[get,nodes,' + self.name + ',available_status]',
                         'not available' if data['condition_ready'] is not True else 'OK'))
        data_to_send.append(
            ZabbixMetric(self.zabbix_host, 'check_kubernetesd[get,nodes,' + self.name + ',condition_status_failed]',
                         data['failed_conds'] if len(data['failed_conds']) > 0 else 'OK'))
        for monitor_value in self.MONITOR_VALUES:
            data_to_send.append(ZabbixMetric(
                self.zabbix_host, 'check_kubernetesd[get,nodes,%s,%s]' % (self.name, monitor_value),
                transform_value(data[monitor_value]))
            )
        return data_to_send
