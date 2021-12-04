import os
import re
from configparser import ConfigParser
from dataclasses import dataclass, field
from enum import Enum
from itertools import chain
from typing import List, Union


def str2bool(v: Union[str, bool]):
    if isinstance(v, bool):
        return v
    return v.lower() in ("yes", "true", "t", "1")


class ClusterAccessConfigType(Enum):
    KUBECONFIG = "kubeconfig"
    INCLUSTER = "incluster"
    TOKEN = "token"


@dataclass(order=True)
class Configuration:
    k8s_config_type: ClusterAccessConfigType = ClusterAccessConfigType.INCLUSTER
    k8s_api_host: str = 'https://example.kube-apiserver.com'
    k8s_api_token: str = ''
    verify_ssl: bool = True
    debug: bool = False
    debug_k8s_events: bool = False
    namespace_exclude_re: str = ""
    resources_exclude: List[str] = field(default_factory=lambda: [])

    sentry_enabled: bool = False
    sentry_dsn: str = ""

    zabbix_server: str = 'example.zabbix-server.com'
    zabbix_resources_exclude: List[str] = field(default_factory=lambda: ["components", "statefulsets", "daemonsets"])
    zabbix_host: str = 'k8s-example-host'
    zabbix_debug: bool = False
    zabbix_single_debug: bool = False
    zabbix_dry_run: bool = False

    web_api_enable: bool = False
    web_api_resources_exclude: List[str] = field(
        default_factory=lambda: ["daemonsets", "components", "services", "statefulsets"])
    web_api_verify_ssl: bool = True
    web_api_host: str = "https://example.api.com/api/v1/k8s"
    web_api_token: str = ""
    web_api_cluster: str = 'k8s-test-cluster'

    discovery_interval_fast: int = 60 * 15
    resend_data_interval_fast: int = 60 * 2

    discovery_interval_slow: int = 60 * 60 * 2
    resend_data_interval_slow: int = 60 * 30

    def _convert_to_type(self, field_name, value):
        if isinstance(getattr(self, field_name), bool):
            value = str2bool(value)
        elif isinstance(getattr(self, field_name), int):
            value = int(value)
        elif isinstance(getattr(self, field_name), list):
            value = re.split(r"[\s,]+", value.strip())
        elif isinstance(getattr(self, field_name), ClusterAccessConfigType):
            value = ClusterAccessConfigType(value)
        return value

    def load_config_file(self, file_name: str):
        if not os.path.isfile(file_name):
            raise ValueError(f"file {file_name} does not exist")

        config_ini = ConfigParser(inline_comment_prefixes="#")

        # fake a "top" section because configparser wants mandatory sections
        with open(file_name) as lines_io:
            lines = chain(["[top]"], lines_io.readlines())
            config_ini.read_file(lines)

        for field_name in self.__dataclass_fields__:  # type: ignore
            if field_name not in config_ini["top"]:
                continue

            value = config_ini["top"][field_name]
            setattr(self, field_name, self._convert_to_type(field_name, value))

    def load_from_environment_variables(self):
        for field_name in self.__dataclass_fields__:
            if field_name.upper() in os.environ and os.environ[field_name.upper()] != "":
                print("setting %s by environment variable %s" % (field_name, field_name.upper()))
                setattr(self, field_name, self._convert_to_type(field_name.os.environ[field_name.upper()]))
