import logging
import threading
import time

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from base.daemon_thread import CheckKubernetesDaemon


class TimedThread(threading.Thread):
    stop_thread = False
    restart_thread = False
    daemon = True

    # TODO: change default of delay_first_run_seconds to 120 seconds
    def __init__(self, resource: str, interval: int,
                 exit_flag: threading.Event,
                 daemon_object: 'CheckKubernetesDaemon',
                 daemon_method: str,
                 delay_first_run: bool = False,
                 delay_first_run_seconds: int = 60):
        self.cycle_interval_seconds = interval
        self.exit_flag = exit_flag
        self.resource = resource
        self.daemon_object = daemon_object
        self.daemon_method = daemon_method
        self.delay_first_run = delay_first_run
        self.delay_first_run_seconds = delay_first_run_seconds
        threading.Thread.__init__(self, target=self.run)
        self.logger = logging.getLogger(__file__)

    def stop(self) -> None:
        self.logger.info('OK: Thread "' + self.resource + '" is stopping"')
        self.stop_thread = True

    def run(self) -> None:
        # manage first run
        if self.delay_first_run:
            self.logger.info(
                '%s -> %s | delaying first run by %is [interval %is]' %
                (self.resource, self.daemon_method, self.delay_first_run_seconds,
                 self.cycle_interval_seconds)
            )
            time.sleep(self.delay_first_run_seconds)
            try:
                self.run_requests(first_run=True)
            except Exception as e:
                self.logger.exception(e)

        # manage timed runs
        while not self.exit_flag.wait(self.cycle_interval_seconds):
            try:
                self.run_requests()
            except Exception as e:
                self.logger.exception(e)
                self.logger.warning(
                    'looprun failed on timed thread %s.%s [interval %is]\nback off ... retrying in %s seconds' %
                    (self.resource, self.daemon_method, self.cycle_interval_seconds, self.cycle_interval_seconds)
                )
                time.sleep(self.cycle_interval_seconds)

        self.logger.info('terminating looprun thread %s.%s' % (self.resource, self.daemon_method))

    def run_requests(self, first_run: bool = False) -> None:
        if first_run:
            self.logger.debug('first looprun on timed thread %s.%s [interval %is]' %
                              (self.resource, self.daemon_method, self.cycle_interval_seconds))
            getattr(self.daemon_object, self.daemon_method)(self.resource)
            self.logger.debug('first looprun complete on timed thread %s.%s [interval %is]' %
                              (self.resource, self.daemon_method, self.cycle_interval_seconds))
        else:
            self.logger.debug('looprun on timed thread %s.%s [interval %is]' %
                              (self.resource, self.daemon_method, self.cycle_interval_seconds))
            getattr(self.daemon_object, self.daemon_method)(self.resource)
            self.logger.debug('looprun complete on timed thread %s.%s [interval %is]' %
                              (self.resource, self.daemon_method, self.cycle_interval_seconds))
