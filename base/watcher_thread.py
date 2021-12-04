import logging
import threading

from urllib3.exceptions import ProtocolError


class WatcherThread(threading.Thread):
    stop_thread = False
    restart_thread = False
    daemon: bool = False

    def __init__(self, resource, exit_flag, daemon, daemon_method):
        self.exit_flag = exit_flag
        self.resource = resource
        self.daemon = daemon
        self.daemon_method = daemon_method
        threading.Thread.__init__(self, target=self.run)
        self.logger = logging.getLogger(__file__)

    def stop(self):
        self.logger.info('OK: Thread "' + self.resource + '" is stopping"')
        self.stop_thread = True

    def run(self):
        self.logger.info('[start thread|watch] %s -> %s' % (self.resource, self.daemon_method))
        try:
            getattr(self.daemon, self.daemon_method)(self.resource)
        except (ProtocolError, ConnectionError) as e:
            self.logger.error(e)
            self.daemon.dirty_threads = True
            self.restart_thread = True
