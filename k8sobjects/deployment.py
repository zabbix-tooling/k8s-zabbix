import logging

from pyzabbix import ZabbixMetric
from .k8sobject import K8sObject, transform_value

logger = logging.getLogger(__file__)


class Deployment(K8sObject):
    object_type = 'deployment'

    @property
    def resource_data(self):
        data = super().resource_data

        for status_type in self.data['status']:
            if status_type == 'conditions':
                continue
            data.update({status_type: transform_value(self.data['status'][status_type])})

        failed_conds = []
        if self.data['status']['conditions']:
            available_conds = [x for x in self.data['status']['conditions'] if x['type'].lower() == "available"]
            if available_conds:
                for cond in available_conds:
                    if cond['status'] != 'True':
                        failed_conds.append(cond['type'])

        data['failed cons'] = failed_conds
        if len(failed_conds) > 0:
            data['status'] = 'ERROR: ' + (','.join(failed_conds))
        else:
            data['status'] = 'OK'

        return data

    def get_zabbix_metrics(self):
        data = self.resource_data
        data_to_send = []

        for status_type in self.data['status']:
            if status_type == 'conditions':
                continue

            data_to_send.append(ZabbixMetric(
                self.zabbix_host,
                'check_kubernetesd[get,deployments,%s,%s,%s]' % (self.name_space, self.name, status_type),
                transform_value(self.data['status'][status_type]))
            )

        data_to_send.append(ZabbixMetric(
            self.zabbix_host,
            'check_kubernetesd[get,deployments,%s,%s,available_status]' % (self.name_space, self.name), data['status']))

        return data_to_send
