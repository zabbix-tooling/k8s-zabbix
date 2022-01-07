import logging
import threading

from urllib3.exceptions import ProtocolError

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from base.daemon_thread import CheckKubernetesDaemon


class WatcherThread(threading.Thread):
    stop_thread = False
    restart_thread = False
    daemon = True

    def __init__(self, resource: str, exit_flag: threading.Event,
                 daemon_object: 'CheckKubernetesDaemon',
                 daemon_method: str):
        self.exit_flag = exit_flag
        self.resource = resource
        self.daemon_object = daemon_object
        self.daemon_method = daemon_method
        threading.Thread.__init__(self, target=self.run)
        self.logger = logging.getLogger(__file__)

    def stop(self) -> None:
        self.logger.info('OK: Thread "' + self.resource + '" is stopping"')
        self.stop_thread = True

    def run(self) -> None:
        self.logger.info('[start thread|watch] %s -> %s' % (self.resource, self.daemon_method))
        try:
            getattr(self.daemon_object, self.daemon_method)(self.resource)
        except (ProtocolError, ConnectionError) as e:
            self.logger.error(e)
            self.restart_thread = True
