import logging

from .k8sobject import K8sObject

logger = logging.getLogger(__file__)

# same as statefulset
# 'status': { 'collision_count': None,
#             'conditions': None,
#             'current_number_scheduled': 8,
#             'desired_number_scheduled': 8,
#             'number_available': 8,
#             'number_misscheduled': 0,
#             'number_ready': 8,
#             'number_unavailable': None,
#             'observed_generation': 8,
#             'updated_number_scheduled': 8}}

class Daemonset(K8sObject):
    object_type = 'daemonset'

    @property
    def resource_data(self):
        data = super().resource_data
        return data

    def get_zabbix_metrics(self):
        data = self.resource_data
        return data
