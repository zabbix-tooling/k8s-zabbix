import json
import logging
import re
from typing import List, Dict

from pyzabbix import ZabbixMetric

from . import get_node_names
from .k8sobject import K8sObject
from .k8sresourcemanager import K8sResourceManager

logger = logging.getLogger(__file__)


def _get_pvc_data_for_node(api, node: str, pvc_volumes: List[K8sObject], timeout_seconds: int,
                           namespace_exclude_re: str,
                           resource_manager: K8sResourceManager) -> List[K8sObject]:
    query_params: List[str] = []
    form_params: List[str] = []
    header_params = {}
    body_params = None
    local_var_files: Dict[str, str] = {}
    header_params['Accept'] = api.api_client.select_header_accept(
        ['application/json', 'application/yaml', 'application/vnd.kubernetes.protobuf', 'application/json;stream=watch',
         'application/vnd.kubernetes.protobuf;stream=watch'])  # noqa: E501

    auth_settings = ['BearerToken']  # noqa: E501
    path_params = {'node': node}
    logger.debug(f"Getting pvc infos for node {node}")
    ret = api.api_client.call_api(
        '/api/v1/nodes/{node}/proxy/stats/summary',
        'GET',
        path_params,
        query_params,
        header_params,
        body=body_params,
        post_params=form_params,
        files=local_var_files,
        response_type='str',  # noqa: E501
        auth_settings=auth_settings,
        async_req=False,
        _return_http_data_only=True,
        _preload_content=False,
        _request_timeout=timeout_seconds,
        collection_formats={}
    )

    loaded_json = json.loads(ret.data)

    for item in loaded_json['pods']:
        if "volume" not in item:
            continue
        pvc_volumes = _process_volume(item=item, namespace_exclude_re=namespace_exclude_re, node=node,
                                      pvc_volumes=pvc_volumes,
                                      resource_manager=resource_manager)
    return pvc_volumes


def _process_volume(item: Dict, namespace_exclude_re: str, node: str,
                    pvc_volumes: List[K8sObject],
                    resource_manager: K8sResourceManager) -> List[K8sObject]:
    for volume in item['volume']:
        if 'pvcRef' not in volume:
            continue

        namespace = volume['pvcRef']['namespace']
        name = volume['pvcRef']['name']

        if namespace_exclude_re and re.match(namespace_exclude_re, namespace):
            continue

        for check_volume in pvc_volumes:
            if check_volume.name_space == namespace and name == check_volume.name:
                logger.warning(f"pvc already exists {namespace} / {name}")

        data = {
            'metadata': {
                'name': name,
                'namespace': namespace
            },
            'item': volume
        }
        data['item']['nodename'] = node
        data['item']['usedBytesPercentage'] = float(float(
            data['item']['usedBytes'] / data['item']['capacityBytes'])) * 100

        data['item']['inodesUsedPercentage'] = float(float(
            data['item']['inodesUsed'] / data['item']['inodes'])) * 100

        for key in ['name', 'pvcRef', 'time', 'availableBytes', 'inodesFree']:
            data['item'].pop(key, None)
        pvc = Pvc(obj_data=data, resource="pvcs", manager=resource_manager)
        pvc_volumes.append(pvc)

    return pvc_volumes


def get_pvc_volumes_for_all_nodes(api, timeout: int, namespace_exclude_re: str,
                                  resource_manager: K8sResourceManager) -> List[K8sObject]:
    pvc_volumes: List[K8sObject] = list()
    for node in get_node_names(api):
        pvc_volumes = _get_pvc_data_for_node(api=api, node=node,
                                             pvc_volumes=pvc_volumes,
                                             timeout_seconds=timeout,
                                             namespace_exclude_re=namespace_exclude_re,
                                             resource_manager=resource_manager,
                                             )
    return pvc_volumes


class Pvc(K8sObject):
    object_type = 'pvc'

    @property
    def resource_data(self):
        data = super().resource_data
        return data

    def get_zabbix_metrics(self):
        data_to_send = list()
        for key, value in self.data['item'].items():
            data_to_send.append(
                ZabbixMetric(
                    self.zabbix_host,
                    f'check_kubernetesd[get,pvcs,{self.name_space},{self.name},{key}]', value
                ))

        return data_to_send
