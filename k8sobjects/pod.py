import logging
import json
import re
from pprint import pformat
from pyzabbix import ZabbixMetric

from k8sobjects import K8sObject, transform_value

logger = logging.getLogger("k8s-zabbix")


class Pod(K8sObject):
    """ Pod discovery is used also for containers """
    object_type = 'pod'
    kind = None

    def get_list(self):
        return self.manager.api.list_pod_for_all_namespaces()

    @property
    def name(self) -> str:
        return self.real_name

    @property
    def real_name(self) -> str:
        if 'metadata' in self.data and 'name' in self.data['metadata']:
            return self.data['metadata']['name']
        raise Exception(f'Could not find name with metadata in data for resource {self.resource}: {self.data}')

    @property
    def base_name(self) -> str:
        if "owner_references" in self.data['metadata'] and self.data['metadata']['owner_references'] is not None:
            try:
                self.kind = self.data['metadata']['owner_references'][0]['kind']
            except Exception as e:
                logger.warning("Pod base_name: metadata: %s, error: %s" % (self.data['metadata'], str(e)))
                self.kind = None

        generate_name = self.real_name

        # override with generate_name
        if "generate_name" in self.data['metadata'] and self.data['metadata']['generate_name']:
            generate_name = self.data['metadata']['generate_name']

        ret_name = ""
        if generate_name is not None:
            match self.kind:
                case "Job":
                    ret_name = re.sub(r'-\d+-$', '', generate_name)
                case "ReplicaSet":
                    ret_name = re.sub(r'-[a-f0-9]{4,}-$', '', generate_name)
                case _:
                    try:
                        ret_name = re.sub(r'-$', '', generate_name)
                    except Exception as e:
                        logger.warning("Container name Exception in Pod: %s\ngenerate_name:%s\ndata:%s\n: %s" %
                                       (self.kind, generate_name, pformat(self.data, indent=2), str(e)))
        return ret_name

    @property
    def resource_data(self):
        data = super().resource_data
        data["containers"] = json.dumps(self.containers)
        container_status = dict()
        data["ready"] = True
        pod_data = {
            "restart_count": 0,
            "ready": 0,
            "not_ready": 0,
            "status": "OK",
        }
        self.phase = self.data["status"]["phase"]

        if "container_statuses" in self.data["status"] and self.data["status"]["container_statuses"] is not None:
            for container in self.data["status"]["container_statuses"]:
                status_values = []
                container_name = container["name"]

                # this pod data
                if container_name not in container_status:
                    container_status[container_name] = {
                        "restart_count": 0,
                        "ready": 0,
                        "not_ready": 0,
                        "status": "OK",
                    }
                container_status[container_name]["restart_count"] += container["restart_count"]
                pod_data["restart_count"] += container["restart_count"]

                if container["ready"] is True:
                    container_status[container_name]["ready"] += 1
                    pod_data["ready"] += 1
                # There are 5 possible Pod phases: Pending, Running, Succeeded, Failed, Unknown
                # Only Failed and Unknown should throw an Error
                elif self.phase not in ["Succeeded", "Running", "Pending"]:
                    container_status[container_name]["not_ready"] += 1
                    pod_data["not_ready"] += 1

                if container["state"] and len(container["state"]) > 0:
                    for status, container_data in container["state"].items():
                        try:
                            reason = container["state"][status]["reason"]
                        except Exception:
                            reason = ""

                        if container_data is not None and status == "terminated" and reason != "Completed":
                            status_values.append("Terminated")

                        if self.phase == "Pending" and reason == 'ImagePullBackOff':
                            container_status[container_name]["not_ready"] += 1
                            pod_data["not_ready"] += 1
                            status_values.append('ImagePullBackOff')

                if len(status_values) > 0:
                    container_status[container_name]["status"] = "ERROR: " + (",".join(status_values))
                    pod_data["status"] = container_status[container_name]["status"]
                    data["ready"] = False

        data["container_status"] = json.dumps(container_status)
        data["pod_data"] = json.dumps(pod_data)
        return data

    @property
    def containers(self):
        containers = {}
        for container in self.data["spec"]["containers"]:
            containers.setdefault(container["name"], 0)
            containers[container["name"]] += 1
        return containers

    def get_zabbix_discovery_data(self) -> list[dict[str, str]]:
        # Main Methode
        data = []
        if self.manager.config.container_crawling == 'container':
            for container in self.containers:
                name = self.base_name
                data += [
                    {
                        "{#NAMESPACE}": self.name_space,
                        "{#NAME}": name,
                        "{#CONTAINER}": container,
                        "{#SLUG}": self.slug(name),
                    }
                ]
        else:
            data += [
                {
                    "{#NAMESPACE}": self.name_space,
                    "{#NAME}": self.real_name,
                }
            ]
        return data

    def get_zabbix_metrics(self):
        data_to_send = list()

        self.data["status"].pop('conditions', None)
        rd = self.resource_data
        pod_data = json.loads(rd["pod_data"])

        if self.manager.config.container_crawling == 'pod':
            for status_type in pod_data:
                data_to_send.append(ZabbixMetric(
                    self.zabbix_host,
                    'check_kubernetesd[get,pods,%s,%s,%s]' % (self.name_space, self.name, status_type),
                    transform_value(pod_data[status_type]))
                )

        return data_to_send

    def get_discovery_for_zabbix(self, discovery_data=None):
        if discovery_data is None:
            discovery_data = self.get_zabbix_discovery_data()
            
        if self.manager.config.container_crawling == 'container':
            discovery_string = "check_kubernetesd[discover, containers]"
        else:
            discovery_string = "check_kubernetesd[discover, pods]"
        return ZabbixMetric(
            self.zabbix_host,
            discovery_string,
            json.dumps(
                {
                    "data": discovery_data,
                }),
        )
