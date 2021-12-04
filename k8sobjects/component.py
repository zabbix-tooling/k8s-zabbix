import logging

from pyzabbix import ZabbixMetric

from .k8sobject import K8sObject

logger = logging.getLogger(__file__)


class Component(K8sObject):
    object_type = 'service'

    @property
    def resource_data(self):
        data = super().resource_data

        data['failed_conds'] = []
        for cond in [x for x in self.data['conditions'] if x['type'].lower() == "healthy"]:
            if cond['status'] != 'True':
                data['failed_conds'].append(cond['type'])

        if len(data['failed_conds']) > 0:
            data['healthy'] = 'ERROR: %s' % data['failed_conds']
        else:
            data['healthy'] = 'OK'
        return data

    def get_zabbix_metrics(self):
        data = self.resource_data
        data_to_send = list()

        data_to_send.append(ZabbixMetric(
            self.zabbix_host,
            'check_kubernetesd[get,components,' + self.name + ',available_status]',
            data['healthy'])
        )

        return data_to_send
