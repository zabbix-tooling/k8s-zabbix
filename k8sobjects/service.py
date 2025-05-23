import logging

from .k8sobject import K8sObject

logger = logging.getLogger("k8s-zabbix")


class Service(K8sObject):
    object_type = "service"

    def get_list(self):
        return self.manager.api.list_service_for_all_namespaces()

    @property
    def resource_data(self):
        data = super().resource_data
        data["is_ingress"] = False
        if self.data["status"]["load_balancer"]["ingress"] is not None:
            data["is_ingress"] = True
        return data

    def get_zabbix_metrics(self):
        data = self.resource_data
        return data
