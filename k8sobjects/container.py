import logging

from pyzabbix import ZabbixMetric

logger = logging.getLogger(__file__)


def get_container_zabbix_metrics(zabbix_host: str, name_space: str,
                                 pod_base_name: str, container_name: str,
                                 data: dict[str, str]) -> list[ZabbixMetric]:
    return [ZabbixMetric(
        zabbix_host, 'check_kubernetesd[get,containers,%s,%s,%s,ready]' % (name_space, pod_base_name, container_name),
        data["ready"],
    ), ZabbixMetric(
        zabbix_host,
        'check_kubernetesd[get,containers,%s,%s,%s,not_ready]' % (name_space, pod_base_name, container_name),
        data["not_ready"],
    ), ZabbixMetric(
        zabbix_host,
        'check_kubernetesd[get,containers,%s,%s,%s,restart_count]' % (name_space, pod_base_name, container_name),
        data["restart_count"],
    ), ZabbixMetric(
        zabbix_host, 'check_kubernetesd[get,containers,%s,%s,%s,status]' % (name_space, pod_base_name, container_name),
        data["status"],
    )]
