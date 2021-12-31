import logging

from pyzabbix import ZabbixMetric

from .k8sobject import K8sObject, transform_value

logger = logging.getLogger(__file__)


# same as statefulset
# 'status': { 'collision_count': None,
#             'conditions': None,
#             'current_number_scheduled': 8,
#             'desired_number_scheduled': 8,
#             'number_available': 8,
#             'number_misscheduled': 0,
#             'number_ready': 8,
#             'number_unavailable': None,
#             'observed_generation': 8,
#             'updated_number_scheduled': 8}}

class Daemonset(K8sObject):
    object_type = 'daemonset'

    @property
    def resource_data(self):
        data = super().resource_data

        for status_type in self.data['status']:
            if status_type == 'conditions':
                continue
            data.update({status_type: transform_value(self.data['status'][status_type])})

        failed_conds = []
        if self.data['status']['conditions']:
            available_conds = [x for x in self.data['status']['conditions'] if x['type'].lower() == "available"]
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
        data_to_send = []

        for status_type in self.data['status']:
            if status_type in ['conditions', 'update_revision']:
                continue

            data_to_send.append(ZabbixMetric(
                self.zabbix_host,
                'check_kubernetesd[get,statefulsets,%s,%s,%s]' % (self.name_space, self.name, status_type),
                transform_value(self.resource_data[status_type]))
            )

        data_to_send.append(ZabbixMetric(
            self.zabbix_host,
            'check_kubernetesd[get,statefulsets,%s,%s,available_status]' % (self.name_space, self.name),
            self.resource_data['available_status']))

        return data_to_send
