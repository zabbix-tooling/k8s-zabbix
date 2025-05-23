import sys

from kubernetes import client
from kubernetes import config as kube_config
from base.config import ClusterAccessConfigType, Configuration
from base.daemon_thread import KubernetesApi


class RawClient:
    def __init__(self, ini_file):
        config = Configuration()
        config.load_config_file(ini_file)
        self.config = config

        if config.k8s_config_type is ClusterAccessConfigType.INCLUSTER:
            kube_config.load_incluster_config()
            self.api_client = client.ApiClient()
        elif config.k8s_config_type is ClusterAccessConfigType.KUBECONFIG:
            kube_config.load_kube_config()
            self.api_client = kube_config.new_client_from_config()
        elif config.k8s_config_type is ClusterAccessConfigType.TOKEN:
            self.api_configuration = client.Configuration()
            self.api_configuration.host = config.k8s_api_host
            self.api_configuration.verify_ssl = config.verify_ssl
            self.api_configuration.api_key = {"authorization": "Bearer " + config.k8s_api_token}
            self.api_client = client.ApiClient(self.api_configuration)
        else:
            self.logger.fatal(f"k8s_config_type = {config.k8s_config_type} is not implemented")
            sys.exit(1)

        self.apis = {
            'core_v1': KubernetesApi(self.api_client).core_v1,
            'apps_v1': KubernetesApi(self.api_client).apps_v1,
            'extensions_v1': KubernetesApi(self.api_client).extensions_v1
        }
