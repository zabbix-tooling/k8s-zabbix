import logging

from .k8sobject import K8sObject

logger = logging.getLogger(__file__)


class Statefulset(K8sObject):
    object_type = 'statefulset'

    @property
    def resource_data(self):
        data = super().resource_data
        return data
