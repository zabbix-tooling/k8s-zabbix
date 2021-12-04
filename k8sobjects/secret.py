import base64
import datetime
import logging

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from pyzabbix import ZabbixMetric

from .k8sobject import K8sObject

logger = logging.getLogger(__file__)


class Secret(K8sObject):
    object_type = 'secret'

    @property
    def resource_data(self):
        data = super().resource_data

        if 'data' not in self.data or not self.data['data']:
            logger.debug('No data for tls_cert "' + self.name_space + '/' + self.name + '"', self.data)
            return data

        if "tls.crt" not in self.data["data"]:
            return data

        base64_decode = base64.b64decode(self.data["data"]["tls.crt"])
        cert = x509.load_pem_x509_certificate(base64_decode, default_backend())
        data['valid_days'] = (cert.not_valid_after - datetime.datetime.now()).days
        return data

    def get_zabbix_metrics(self):
        data = self.resource_data
        data_to_send = list()
        if 'valid_days' not in data:
            return data_to_send

        data_to_send.append(ZabbixMetric(
            self.zabbix_host, 'check_kubernetesd[get,secret,' + self.name_space + ',' + self.name + ',valid_days]',
            data['valid_days'])
        )
        return data_to_send

    def get_zabbix_discovery_data(self):
        if self.data["data"] is not None and "tls.crt" in dict(self.data["data"]):
            return super().get_zabbix_discovery_data()
        return ''
