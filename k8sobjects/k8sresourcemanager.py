import importlib
import logging
from datetime import datetime

from kubernetes.client import (AppsV1Api, CoreV1Api,
                               ApiextensionsV1Api)

from base.config import Configuration
from k8sobjects.k8sobject import K8S_RESOURCES, K8sObject

logger = logging.getLogger("k8s-zabbix")


class K8sResourceManager:
    def __init__(self, resource: str, apis: dict | None = None,
                 zabbix_host: str | None = None, config: Configuration | None = None):
        self.resource = resource
        self.apis = apis
        self.zabbix_host = zabbix_host
        self.config = config

        self.objects: dict[str, K8sObject] = dict()
        self.containers: dict = dict()  # containers only used for pods

        mod = importlib.import_module('k8sobjects')
        class_label = K8S_RESOURCES[resource]
        self.resource_class = getattr(mod, class_label.capitalize(), None)
        if self.resource_class is not None:
            self.resource_meta = self.resource_class(None, self.resource, manager=self)

        logger.info(f"Creating new resource manager for resource {resource} with class {self.resource_class}")

        self.api = self.get_api_for_resource(resource)

    def get_api_for_resource(self, resource: str) -> CoreV1Api | AppsV1Api | ApiextensionsV1Api:
        if resource in ['nodes', 'components', 'secrets', 'pods', 'services', 'pvcs']:
            api = self.apis.get('core_v1')
        elif resource in ["deployments", "daemonsets", "statefulsets"]:
            api = self.apis.get('apps_v1')
        elif resource in ["ingresses"]:
            api = self.apis.get('extensions_v1')
        elif resource == 'containers':
            api = None
        else:
            raise AttributeError("No valid resource found: %s" % resource)
        return api

    def add_obj_from_data(self, data: dict) -> K8sObject | None:
        if not self.resource_class:
            logger.error('No Resource Class found for "%s"' % self.resource)
            return None

        new_obj = self.resource_class(data, self.resource, manager=self)
        return self.add_obj(new_obj)

    def add_obj(self, new_obj: K8sObject) -> K8sObject | None:
        if new_obj.uid not in self.objects:
            # new object
            self.objects[new_obj.uid] = new_obj
            new_obj.added = datetime.now()
        elif self.objects[new_obj.uid].data_checksum != new_obj.data_checksum:
            # existing object with modified data
            new_obj.last_sent_zabbix_discovery = self.objects[new_obj.uid].last_sent_zabbix_discovery
            new_obj.last_sent_zabbix = self.objects[new_obj.uid].last_sent_zabbix
            new_obj.last_sent_web = self.objects[new_obj.uid].last_sent_web
            new_obj.added = self.objects[new_obj.uid].added
            new_obj.is_dirty_web = True
            new_obj.is_dirty_zabbix = True
            self.objects[new_obj.uid] = new_obj

        # return created or updated object
        return self.objects[new_obj.uid]

    def del_obj(self, obj: str | dict) -> K8sObject | None:
        if not self.resource_class:
            logger.error('No Resource Class found for "%s"' % self.resource)
            return None

        if isinstance(obj, str):
            # find by string
            resourced_obj = self.objects[obj]
            del self.objects[obj]
        else:
            # find by dict data
            resourced_obj = self.resource_class(obj, self.resource, manager=self)
            if resourced_obj.uid in self.objects:
                del self.objects[resourced_obj.uid]
        return resourced_obj
