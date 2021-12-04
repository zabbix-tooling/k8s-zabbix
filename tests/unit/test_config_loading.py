import os

from base.config import Configuration

RESOURCES_DIR = os.path.realpath(os.path.dirname(os.path.realpath(__file__))) + "/resources"


def test_load_config():
    cfg = Configuration()
    cfg.load_config_file(f"{RESOURCES_DIR}/test.ini")
    cfg.load_from_environment_variables()
    assert (cfg.debug is True)
    assert (cfg.discovery_interval_fast == 12)
    assert ("jacco" in cfg.zabbix_resources_exclude)
    assert ("wacco" in cfg.zabbix_resources_exclude)

