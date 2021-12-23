import json
import logging
import re
from typing import List, Dict

from pyzabbix import ZabbixMetric

from .k8sobject import K8sObject

logger = logging.getLogger(__file__)


def get_pvc_data(api, node, timeout_seconds: int, namespace_exclude_re: str) -> List[Dict]:
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

    pvc_volumes: List[Dict] = []
    for item in loaded_json['pods']:
        if "volume" not in item:
            continue
        pvc_volumes = _check_volume(item, namespace_exclude_re, node, pvc_volumes)
    return pvc_volumes


def _check_volume(item, namespace_exclude_re, node, pvc_volumes):
    for volume in item['volume']:
        if 'pvcRef' not in volume:
            continue

        namespace = volume['pvcRef']['namespace']
        if namespace_exclude_re and re.match(namespace_exclude_re, namespace):
            continue

        name = volume['pvcRef']['name']
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
        pvc_volumes.append(data)
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
                    f'check_kubernetesd[get,pvc,{self.name_space},{self.name},{key}]', value
                ))

        return data_to_send
