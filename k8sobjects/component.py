import logging

from pyzabbix import ZabbixMetric

from .k8sobject import K8sObject

logger = logging.getLogger(__file__)


class Component(K8sObject):
    object_type = 'component'

    @property
    def resource_data(self):
        data = super().resource_data

        failed_conds = []

        # exclude
        if self.name in ["controller-manager", "scheduler"]:
            # faked, unfortinately k8s prpject broke these checks https://github.com/kubernetes/kubernetes/issues/19570
            data['available_status'] = 'OK: faked'
        elif self.data['conditions']:
            available_conds = [x for x in self.data['conditions'] if x['type'].lower() == "healthy"]
            if available_conds:
                for cond in available_conds:
                    if cond['status'] != 'True':
                        failed_conds.append(cond['type'])

            if len(failed_conds) > 0:
                data['available_status'] = 'ERROR: ' + (','.join(failed_conds))
            else:
                data['available_status'] = 'OK'
        else:
            data['available_status'] = 'OK'

        return data

    def get_zabbix_metrics(self):
        data_to_send = list()

        data_to_send.append(ZabbixMetric(
            self.zabbix_host,
            'check_kubernetesd[get,components,%s,available_status]' % self.name,
            self.resource_data['available_status']))

        return data_to_send
