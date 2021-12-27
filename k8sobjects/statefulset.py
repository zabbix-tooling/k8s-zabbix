import logging

from pyzabbix import ZabbixMetric

from .k8sobject import K8sObject, transform_value

logger = logging.getLogger(__file__)


class Statefulset(K8sObject):
    object_type = 'statefulset'

    @property
    def resource_data(self):
        data = super().resource_data
        return data

    def get_zabbix_metrics(self):
        data_to_send = []

        for status_type in self.data['status']:
            if status_type == 'conditions':
                continue

            data_to_send.append(ZabbixMetric(
                self.zabbix_host,
                'check_kubernetesd[get,statefulsets,%s,%s,%s]' % (self.name_space, self.name, status_type),
                transform_value(self.data['status'][status_type]))
            )

        return data_to_send
