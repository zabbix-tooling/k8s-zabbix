import requests
import logging

from k8sobjects.k8sobject import K8S_RESOURCES

logger = logging.getLogger(__file__)


class WebApi:
    def __init__(self, api_host, api_token, verify_ssl=True):
        self.api_host = api_host
        self.api_token = api_token
        self.verify_ssl = verify_ssl

        url = self.get_url()
        r = requests.head(url)
        if r.status_code in [301, 302]:
            self.api_host = r.headers['location']

    def get_headers(self):
        return {
            'Authorization': self.api_token,
            'User-Agent': 'k8s-zabbix agent',
        }

    def get_url(self, resource=None, path_append=""):
        api_resource = None
        if resource:
            api_resource = K8S_RESOURCES[resource]

        url = self.api_host
        if not url.endswith('/'):
            url += '/'

        if not api_resource:
            return url
        return url + api_resource + '/' + path_append

    def send_data(self, resource, data, action):
        path_append = ""
        if action.lower() == 'added':
            func = requests.post
        elif action.lower() == 'modified':
            func = requests.put
        elif action.lower() == 'deleted':
            func = requests.delete
            if 'name_space' in data and data["name_space"]:
                path_append = "%s/%s/%s/" % (
                    data["cluster"],
                    data["name_space"],
                    data["name"],
                )
            else:
                path_append = "%s/%s/" % (
                    data["cluster"],
                    data["name"],
                )
            data = {}
        else:
            return

        url = self.get_url(resource, path_append)

        # empty variables are NOT sent!
        r = func(url,
                 data=data,
                 headers=self.get_headers(),
                 verify=self.verify_ssl,
                 allow_redirects=True)

        if r.status_code > 399:
            logger.warning('%s [%s] %s sended %s but failed data >>>%s<<< (%s)' % (
                self.api_host, r.status_code, url, resource, data, action))
            logger.warning(r.text)
        else:
            logger.debug('%s [%s] %s sucessfully sended %s >>>%s<<< (%s)' % (
                self.api_host, r.status_code, url, resource, data, action))
