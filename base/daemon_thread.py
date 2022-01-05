import json
import logging
import re
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pprint import pformat

from kubernetes import client, watch
from kubernetes import config as kube_config
from kubernetes.client import ApiClient
from pyzabbix import ZabbixMetric, ZabbixSender

from base.config import Configuration, ClusterAccessConfigType
from base.timed_threads import TimedThread
from base.watcher_thread import WatcherThread
from k8sobjects import K8sObject, K8sResourceManager
from k8sobjects.container import get_container_zabbix_metrics
from k8sobjects.pvc import get_pvc_volumes_for_all_nodes

exit_flag = threading.Event()


@dataclass
class DryResult:
    failed: int = 0
    processed: int = 0


def get_data_timeout_datetime() -> datetime:
    return datetime.now() - timedelta(minutes=1)


def get_discovery_timeout_datetime() -> datetime:
    return datetime.now() - timedelta(hours=1)


class KubernetesApi:
    __shared_state = dict(core_v1=None,
                          apps_v1=None,
                          extensions_v1=None)

    def __init__(self, api_client: ApiClient):
        self.__dict__ = self.__shared_state
        if not getattr(self, 'core_v1', None):
            self.core_v1 = client.CoreV1Api(api_client)
        if not getattr(self, 'apps_v1', None):
            self.apps_v1 = client.AppsV1Api(api_client)
        if not getattr(self, 'exentsions_v1', None):
            self.extensions_v1 = client.ExtensionsV1beta1Api(api_client)


class CheckKubernetesDaemon:
    data: dict[str, K8sResourceManager] = {}
    discovery_sent: dict[str, datetime] = {}
    thread_lock = threading.Lock()

    def __init__(self, config: Configuration,
                 resources: list[str],
                 discovery_interval: int, data_resend_interval: int,
                 ):
        self.manage_threads: list[TimedThread | WatcherThread] = []
        self.config = config
        self.logger = logging.getLogger(__file__)
        self.discovery_interval = int(discovery_interval)
        self.data_resend_interval = int(data_resend_interval)

        self.api_zabbix_interval = 60
        self.rate_limit_seconds = 30

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

        self.logger.info(f"Initialized cluster access for {config.k8s_config_type}")
        # K8S API
        self.debug_k8s_events = False
        self.core_v1 = KubernetesApi(self.api_client).core_v1
        self.apps_v1 = KubernetesApi(self.api_client).apps_v1
        self.extensions_v1 = KubernetesApi(self.api_client).extensions_v1

        self.zabbix_sender = ZabbixSender(zabbix_server=config.zabbix_server)
        self.zabbix_resources = CheckKubernetesDaemon.exclude_resources(resources,
                                                                        self.config.zabbix_resources_exclude)
        self.zabbix_host = config.zabbix_host
        self.zabbix_debug = config.zabbix_debug
        self.zabbix_single_debug = config.zabbix_single_debug
        self.zabbix_dry_run = config.zabbix_dry_run

        self.web_api = None
        self.web_api_enable = config.web_api_enable
        self.web_api_resources = CheckKubernetesDaemon.exclude_resources(resources,
                                                                         self.config.web_api_resources_exclude)

        self.web_api_host = config.web_api_host
        self.web_api_token = config.web_api_token
        self.web_api_cluster = config.web_api_cluster
        self.web_api_verify_ssl = config.web_api_verify_ssl

        self.resources = CheckKubernetesDaemon.exclude_resources(resources, self.config.resources_exclude)

        self.logger.info(f"Init K8S-ZABBIX Watcher for resources: {','.join(self.resources)}")
        self.logger.info(f"Zabbix Host: {self.zabbix_host} / Zabbix Proxy or Server: {config.zabbix_server}")
        if self.web_api_enable:
            self.logger.info(f"WEB Api Host {self.web_api_host} with resources {','.join(self.web_api_resources)}")

    @staticmethod
    def exclude_resources(available_types: list[str], excluded_types: list[str]) -> list[str]:
        result = []
        for k8s_type_available in available_types:
            if k8s_type_available not in excluded_types:
                result.append(k8s_type_available)
        return result

    def handler(self, signum: int, *args: str) -> None:
        if signum in [signal.SIGTERM]:
            self.logger.info('Signal handler called with signal %s... stopping (max %s seconds)' % (signum, 3))
            exit_flag.set()
            for thread in self.manage_threads:
                thread.join(timeout=3)
            self.logger.info('All threads exited... exit check_kubernetesd')
            sys.exit(0)
        elif signum in [signal.SIGUSR1]:
            self.logger.info('=== Listing count of data hold in CheckKubernetesDaemon.data ===')
            with self.thread_lock:
                for r, d in self.data.items():
                    for obj_name, obj_d in d.objects.items():
                        self.logger.info(
                            f"resource={r}, last_sent_zabbix={obj_d.last_sent_zabbix}, " +
                            f"last_sent_web={obj_d.last_sent_web}"
                        )
                for resource_discovered, resource_discovered_time in self.discovery_sent.items():
                    self.logger.info(
                        f"resource={resource_discovered}, last_discovery_sent={resource_discovered_time}")
        elif signum in [signal.SIGUSR2]:
            self.logger.info('=== Listing all data hold in CheckKubernetesDaemon.data ===')
            with self.thread_lock:
                for r, d in self.data.items():
                    for obj_name, obj_d in d.objects.items():
                        data_print = pformat(obj_d.data, indent=2)
                        self.logger.info(f"resource={r}, object_name={obj_name}, object_data={data_print}")

    def run(self) -> None:
        self.start_data_threads()
        self.start_api_info_threads()
        self.start_loop_send_discovery_threads()
        self.start_resend_threads()

    def start_data_threads(self) -> None:
        for resource in self.resources:
            with self.thread_lock:
                self.data.setdefault(resource, K8sResourceManager(resource, zabbix_host=self.zabbix_host))
                if resource == 'pods':
                    self.data.setdefault('containers', K8sResourceManager('containers'))

            # watcher threads
            if resource == 'containers':
                pass
            elif resource == 'components':
                thread = TimedThread(resource, self.data_resend_interval, exit_flag,
                                     daemon_object=self, daemon_method='watch_data')
                self.manage_threads.append(thread)
                thread.start()
            elif resource == 'pvcs':
                thread = TimedThread(resource, self.data_resend_interval, exit_flag,
                                     daemon_object=self, daemon_method='watch_data')
                self.manage_threads.append(thread)
                thread.start()
            # additional looping data threads
            elif resource == 'services':
                thread = TimedThread(resource, self.data_resend_interval, exit_flag,
                                     daemon_object=self, daemon_method='report_global_data_zabbix',
                                     delay_first_run_seconds=self.discovery_interval + 5)
                self.manage_threads.append(thread)
                thread.start()
            elif resource == 'containers':
                thread = TimedThread(resource, self.data_resend_interval, exit_flag,
                                     daemon_object=self, daemon_method='report_global_data_zabbix',
                                     delay_first_run_seconds=self.discovery_interval + 5)
                self.manage_threads.append(thread)
                thread.start()
            else:
                thread = WatcherThread(resource, exit_flag,
                                       daemon_object=self, daemon_method='watch_data')
                self.manage_threads.append(thread)
                thread.start()

    def start_api_info_threads(self) -> None:
        if 'nodes' not in self.resources:
            # only send api heartbeat once
            return

        thread = TimedThread('api_heartbeat', self.api_zabbix_interval, exit_flag,
                             daemon_object=self, daemon_method='send_heartbeat_info')
        self.manage_threads.append(thread)
        thread.start()

    def start_loop_send_discovery_threads(self) -> None:
        for resource in self.resources:
            send_discovery_thread = TimedThread(resource, self.discovery_interval, exit_flag,
                                                daemon_object=self, daemon_method='send_zabbix_discovery',
                                                delay_first_run=True,
                                                delay_first_run_seconds=30)
            self.manage_threads.append(send_discovery_thread)
            send_discovery_thread.start()

    def start_resend_threads(self) -> None:
        for resource in self.resources:
            resend_thread = TimedThread(resource, self.data_resend_interval, exit_flag,
                                        daemon_object=self, daemon_method='resend_data',
                                        delay_first_run=True,
                                        delay_first_run_seconds=60,
                                        )
            self.manage_threads.append(resend_thread)
            resend_thread.start()

    def get_api_for_resource(self, resource: str) -> None:
        if resource in ['nodes', 'components', 'secrets', 'pods', 'services', 'pvcs']:
            api = self.core_v1
        elif resource in ['deployments', 'daemonsets', 'statefulsets']:
            api = self.apps_v1
        elif resource in ['ingresses']:
            api = self.extensions_v1
        else:
            raise AttributeError('No valid resource found: %s' % resource)
        return api

    def get_web_api(self) -> None:
        if not hasattr(self, '_web_api'):
            from .web_api import WebApi
            self._web_api = WebApi(self.web_api_host, self.web_api_token, verify_ssl=self.web_api_verify_ssl)
        return self._web_api

    def watch_data(self, resource: str) -> None:
        api = self.get_api_for_resource(resource)
        stream_named_arguments = {"timeout_seconds": self.config.k8s_api_stream_timeout_seconds}
        request_named_arguments = {"_request_timeout": self.config.k8s_api_request_timeout_seconds}
        self.logger.info(
            "Watching for resource >>>%s<<< with a stream duration of %ss or request_timeout of %ss" % (
                resource,
                self.config.k8s_api_stream_timeout_seconds,
                self.config.k8s_api_request_timeout_seconds)
        )
        while True:
            w = watch.Watch()
            if resource == 'nodes':
                for obj in w.stream(api.list_node, **stream_named_arguments):
                    self.watch_event_handler(resource, obj)
            elif resource == 'deployments':
                for obj in w.stream(api.list_deployment_for_all_namespaces, **stream_named_arguments):
                    self.watch_event_handler(resource, obj)
            elif resource == 'daemonsets':
                for obj in w.stream(api.list_daemon_set_for_all_namespaces, **stream_named_arguments):
                    self.watch_event_handler(resource, obj)
            elif resource == 'statefulsets':
                for obj in w.stream(api.list_stateful_set_for_all_namespaces, **stream_named_arguments):
                    self.watch_event_handler(resource, obj)
            elif resource == 'components':
                # The api does not support watching on component status
                with self.thread_lock:
                    for obj in api.list_component_status(watch=False, **request_named_arguments).to_dict().get('items'):
                        self.data[resource].add_obj_from_data(obj)
                time.sleep(self.data_resend_interval)
            elif resource == 'pvcs':
                pvc_volumes = get_pvc_volumes_for_all_nodes(api=api,
                                                            timeout=self.config.k8s_api_request_timeout_seconds,
                                                            namespace_exclude_re=self.config.namespace_exclude_re,
                                                            resource_manager=self.data[resource])
                with self.thread_lock:
                    for obj in pvc_volumes:
                        self.data[resource].add_obj(obj)
                time.sleep(self.data_resend_interval)
            elif resource == 'ingresses':
                for obj in w.stream(api.list_ingress_for_all_namespaces, **stream_named_arguments):
                    self.watch_event_handler(resource, obj)
            elif resource == 'tls':
                for obj in w.stream(api.list_secret_for_all_namespaces, **stream_named_arguments):
                    self.watch_event_handler(resource, obj)
            elif resource == 'pods':
                for obj in w.stream(api.list_pod_for_all_namespaces, **stream_named_arguments):
                    self.watch_event_handler(resource, obj)
            elif resource == 'services':
                for obj in w.stream(api.list_service_for_all_namespaces, **stream_named_arguments):
                    self.watch_event_handler(resource, obj)
            else:
                self.logger.error("No watch handling for resource %s" % resource)
                time.sleep(60)
            self.logger.debug("Watch/fetch completed for resource >>>%s<<<, restarting" % resource)

    def watch_event_handler(self, resource: str, event: dict) -> None:

        obj = event['object'].to_dict()
        event_type = event['type']
        name = obj['metadata']['name']
        namespace = str(obj['metadata']['namespace'])

        if self.config.namespace_exclude_re and re.match(self.config.namespace_exclude_re, namespace):
            self.logger.debug(f"skip namespace {namespace}")
            return

        if self.debug_k8s_events:
            self.logger.info(f"{event_type} [{resource}]: {namespace}/{name} : >>>{pformat(obj, indent=2)}<<<")
        else:
            self.logger.debug(f"{event_type} [{resource}]: {namespace}/{name}")

        with self.thread_lock:
            if not self.data[resource].resource_class:
                self.logger.error('Could not add watch_event_handler! No resource_class for "%s"' % resource)
                return

        if event_type.lower() == 'added':
            with self.thread_lock:
                resourced_obj = self.data[resource].add_obj_from_data(obj)

            if resourced_obj and (resourced_obj.is_dirty_zabbix or resourced_obj.is_dirty_web):
                self.send_object(resource, resourced_obj, event_type,
                                 send_zabbix_data=resourced_obj.is_dirty_zabbix,
                                 send_web=resourced_obj.is_dirty_web)
        elif event_type.lower() == 'modified':
            with self.thread_lock:
                resourced_obj = self.data[resource].add_obj_from_data(obj)
            if resourced_obj and (resourced_obj.is_dirty_zabbix or resourced_obj.is_dirty_web):
                self.send_object(resource, resourced_obj, event_type,
                                 send_zabbix_data=resourced_obj.is_dirty_zabbix,
                                 send_web=resourced_obj.is_dirty_web)
        elif event_type.lower() == 'deleted':
            with self.thread_lock:
                resourced_obj = self.data[resource].del_obj(obj)
                self.delete_object(resource, resourced_obj)
        else:
            self.logger.info('event type "%s" not implemented' % event_type)

    def report_global_data_zabbix(self, resource) -> None:
        """ aggregate and report information for some speciality in resources """
        if resource not in self.discovery_sent:
            self.logger.debug('skipping report_global_data_zabbix for %s, discovery not send yet!' % resource)
            return

        data_to_send = list()

        if resource == 'services':
            num_services = 0
            num_ingress_services = 0
            with self.thread_lock:
                for obj_uid, resourced_obj in self.data[resource].objects.items():
                    num_services += 1
                    if resourced_obj.resource_data['is_ingress']:
                        num_ingress_services += 1

            data_to_send.append(
                ZabbixMetric(self.zabbix_host, 'check_kubernetes[get,services,num_services]',
                             str(num_services)))
            data_to_send.append(
                ZabbixMetric(self.zabbix_host, 'check_kubernetes[get,services,num_ingress_services]',
                             str(num_ingress_services)))
            self.send_data_to_zabbix(resource, None, data_to_send)
        elif resource == 'containers':
            # aggregate pod data to containers for each namespace
            with self.thread_lock:
                containers = dict()
                for obj_uid, resourced_obj in self.data['pods'].objects.items():
                    ns = resourced_obj.name_space
                    if ns not in containers:
                        containers[ns] = dict()

                    pod_data = resourced_obj.resource_data
                    pod_base_name = resourced_obj.base_name
                    try:
                        container_status = json.loads(pod_data['container_status'])
                    except Exception as e:
                        self.logger.error(e)
                        continue

                    # aggregate container information
                    for container_name, container_data in container_status.items():
                        containers[ns].setdefault(pod_base_name, dict())
                        containers[ns][pod_base_name].setdefault(container_name, container_data)

                        for k, v in containers[ns][pod_base_name][container_name].items():
                            if isinstance(v, int):
                                containers[ns][pod_base_name][container_name][k] += container_data[k]
                            elif k == 'status' and container_data[k].startswith('ERROR'):
                                containers[ns][pod_base_name][container_name][k] = container_data[k]

                for ns, d1 in containers.items():
                    for pod_base_name, d2 in d1.items():
                        for container_name, container_data in d2.items():
                            data_to_send += get_container_zabbix_metrics(self.zabbix_host, ns, pod_base_name,
                                                                         container_name, container_data)

                self.send_data_to_zabbix(resource, None, data_to_send)

    def resend_data(self, resource) -> None:

        with self.thread_lock:
            try:
                metrics = list()
                if resource not in self.data or len(self.data[resource].objects) == 0:
                    self.logger.warning("no resource data available for %s , stop delivery" % resource)
                    return

                # Zabbix
                for obj_uid, obj in self.data[resource].objects.items():
                    zabbix_send = False
                    if resource in self.discovery_sent:
                        zabbix_send = True
                    elif obj.last_sent_zabbix < (datetime.now() - timedelta(seconds=self.data_resend_interval)):
                        self.logger.debug("resend zabbix : %s  - %s/%s data because its outdated" % (
                            resource, obj.name_space, obj.name))
                        zabbix_send = True
                    if zabbix_send:
                        metrics += obj.get_zabbix_metrics()
                        obj.last_sent_zabbix = datetime.now()
                        obj.is_dirty_zabbix = False
                if len(metrics) > 0:
                    if resource not in self.discovery_sent:
                        self.logger.debug(
                            'skipping resend_data zabbix , discovery for %s - %s/%s not sent yet!' % (
                                resource, obj.name_space, obj.name))
                    else:
                        self.send_data_to_zabbix(resource, metrics=metrics)

                # Web
                for obj_uid, obj in self.data[resource].objects.items():
                    if obj.is_dirty_web:
                        if obj.is_unsubmitted_web():
                            self.send_to_web_api(resource, obj, 'ADDED')
                        else:
                            self.send_to_web_api(resource, obj, 'MODIFIED')
                    else:
                        if obj.is_unsubmitted_web():
                            self.send_to_web_api(resource, obj, 'ADDED')
                        elif obj.last_sent_web < (datetime.now() - timedelta(seconds=self.data_resend_interval)):
                            self.send_to_web_api(resource, obj, 'MODIFIED')
                            self.logger.debug("resend web : %s/%s data because its outdated" % (resource, obj.name))
                    obj.last_sent_web = datetime.now()
                    obj.is_dirty_web = False
            except RuntimeError as e:
                self.logger.warning(str(e))

    def delete_object(self, resource_type: str, resourced_obj: K8sObject) -> None:
        # TODO: trigger zabbix discovery, srsly?
        self.send_to_web_api(resource_type, resourced_obj, "deleted")

    def send_zabbix_discovery(self, resource: str) -> None:
        # aggregate data and send to zabbix
        self.logger.info(f"send_zabbix_discovery: {resource}")
        with self.thread_lock:
            if resource not in self.data:
                self.logger.warning('send_zabbix_discovery: resource "%s" not in self.data... skipping!' % resource)
                return

            data = list()
            for obj_uid, obj in self.data[resource].objects.items():
                data += obj.get_zabbix_discovery_data()

            if data:
                metric = obj.get_discovery_for_zabbix(data)
                self.logger.debug('send_zabbix_discovery: resource "%s": %s' % (resource, metric))
                self.send_discovery_to_zabbix(resource, metric=metric)
            else:
                self.logger.warning('send_zabbix_discovery: resource "%s" has no discovery data' % resource)

            self.discovery_sent[resource] = datetime.now()

    def send_object(self, resource, resourced_obj, event_type, send_zabbix_data=False, send_web=False) -> None:
        # send single object for updates
        with self.thread_lock:
            if send_zabbix_data:
                if resourced_obj.last_sent_zabbix < datetime.now() - timedelta(seconds=self.rate_limit_seconds):
                    self.send_data_to_zabbix(resource, obj=resourced_obj)
                    resourced_obj.last_sent_zabbix = datetime.now()
                    resourced_obj.is_dirty_zabbix = False
                else:
                    self.logger.debug('obj >>>type: %s, name: %s/%s<<< not sending to zabbix! rate limited (%is)' % (
                        resource, resourced_obj.name_space, resourced_obj.name, self.rate_limit_seconds))
                    resourced_obj.is_dirty_zabbix = True

            if send_web:
                if resourced_obj.last_sent_web < datetime.now() - timedelta(seconds=self.rate_limit_seconds):
                    self.send_to_web_api(resource, resourced_obj, event_type)
                    resourced_obj.last_sent_web = datetime.now()
                    if resourced_obj.is_dirty_web is True and not send_zabbix_data:
                        # only set dirty False if send_to_web_api worked
                        resourced_obj.is_dirty_web = False
                else:
                    self.logger.debug('obj >>>type: %s, name: %s/%s<<< not sending to web! rate limited (%is)' % (
                        resource, resourced_obj.name_space, resourced_obj.name, self.rate_limit_seconds))
                    resourced_obj.is_dirty_web = True

    def send_heartbeat_info(self, *args) -> None:
        result = self.send_to_zabbix([
            ZabbixMetric(self.zabbix_host, 'check_kubernetesd[discover,api]', str(int(time.time())))
        ])
        if result.failed > 0:
            self.logger.error("failed to send heartbeat to zabbix")
        else:
            self.logger.debug("successfully sent heartbeat to zabbix ")

    def send_to_zabbix(self, metrics: list[ZabbixMetric]):
        if self.zabbix_dry_run:
            result = DryResult()
        else:
            try:
                result = self.zabbix_sender.send(metrics)
            except Exception as e:
                self.logger.error(e)
                result = DryResult()
                result.failed = 1
                result.processed = 0

        if self.zabbix_debug:
            if len(metrics) > 1:
                self.logger.info('===> Sending to zabbix: >>>\n%s\n<<<' % pformat(metrics, indent=2))
            else:
                self.logger.info('===> Sending to zabbix: >>>%s<<<' % metrics)
        return result

    def send_discovery_to_zabbix(self, resource: str, metric: ZabbixMetric = None, obj: K8sObject = None) -> None:
        if resource not in self.zabbix_resources:
            self.logger.warning(
                f'resource {resource} ist not activated, active resources are : {",".join(self.zabbix_resources)}')
            return

        if obj:
            discovery_data = obj.get_discovery_for_zabbix()
            if not discovery_data:
                self.logger.warning('No discovery_data for obj %s, not sending to zabbix!' % obj.uid)
                return

            discovery_key = 'check_kubernetesd[discover,' + resource + ']'
            result = self.send_to_zabbix([ZabbixMetric(self.zabbix_host, discovery_key, discovery_data)])
            if result.failed > 0:
                self.logger.error("failed to sent zabbix discovery: %s : >>>%s<<<" % (discovery_key, discovery_data))
            elif self.zabbix_debug:
                self.logger.info("successfully sent zabbix discovery: %s  >>>>%s<<<" % (discovery_key, discovery_data))
        elif metric:
            result = self.send_to_zabbix([metric])
            if result.failed > 0:
                self.logger.error("failed to sent mass zabbix discovery: >>>%s<<<" % metric)
            elif self.zabbix_debug:
                self.logger.info("successfully sent mass zabbix discovery: >>>%s<<<" % metric)
        else:
            self.logger.warning('No obj or metrics found for send_discovery_to_zabbix [%s]' % resource)

    def send_data_to_zabbix(self, resource: str, obj=None, metrics=None) -> None:
        if metrics is None:
            metrics = list()
        if resource not in self.zabbix_resources:
            return

        if obj and len(metrics) == 0:
            metrics = obj.get_zabbix_metrics()

        if len(metrics) == 0 and obj:
            self.logger.debug('No zabbix metrics to send for %s: %s' % (obj.uid, metrics))
            return
        elif len(metrics) == 0:
            self.logger.debug('No zabbix metrics or no obj found for [%s]' % resource)
            return

        if self.zabbix_single_debug:
            for metric in metrics:
                result = self.send_to_zabbix([metric])
                if result.failed > 0:
                    self.logger.error("failed to sent zabbix items: %s", metric)
                else:
                    self.logger.info("successfully sent zabbix items: %s", metric)
        else:
            result = self.send_to_zabbix(metrics)
            if result.failed > 0:
                self.logger.error("failed to sent %s zabbix items, processed %s items [%s: %s]"
                                  % (result.failed, result.processed, resource, obj.name if obj else 'metrics'))
                self.logger.debug(metrics)
            else:
                self.logger.debug("successfully sent %s zabbix items [%s: %s]" % (
                    len(metrics), resource, obj.name if obj else 'metrics'))

    def send_to_web_api(self, resource, obj, action) -> None:
        if resource not in self.web_api_resources:
            return

        if self.web_api_enable:
            api = self.get_web_api()
            data_to_send = obj.resource_data
            data_to_send['cluster'] = self.web_api_cluster

            api.send_data(resource, data_to_send, action)
        else:
            self.logger.debug("suppressing submission of %s %s/%s" % (resource, obj.name_space, obj.name))
