import logging

from .k8sobject import K8sObject

logger = logging.getLogger(__file__)


class Ingress(K8sObject):
    object_type = 'ingress'

    @property
    def resource_data(self):
        data = super().resource_data
        return data

    def get_zabbix_metrics(self):
        data = self.resource_data
        return data
