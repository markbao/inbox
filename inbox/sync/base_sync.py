import gevent
import gevent.event

from inbox.log import get_logger
logger = get_logger()
from inbox.basicauth import ConnectionError, ValidationError
from inbox.util.concurrency import retry_with_logging
from inbox.heartbeat.status import HeartbeatStatusProxy, clear_heartbeat_status


class BaseSync(gevent.Greenlet):
    def __init__(self, account_id, namespace_id, poll_frequency, folder_id,
                 folder_name, provider_name):
        self.account_id = account_id
        self.namespace_id = namespace_id
        self.poll_frequency = poll_frequency
        self.folder_id = folder_id
        self.folder_name = folder_name
        self.provider_name = provider_name

        self.shutdown = gevent.event.Event()

        self.log = logger.new(account_id=account_id)
        self.heartbeat_status = HeartbeatStatusProxy(self.account_id,
                                                     self.folder_id)
        self.heartbeat_status.publish(provider_name=self.provider_name,
                                      folder_name=self.folder_name)

        gevent.Greenlet.__init__(self)

    def _run(self):
        return retry_with_logging(self._run_impl, self.log,
                                  account_id=self.account_id)

    def _run_impl(self):
        try:
            self.provider_instance = self.provider(self.account_id,
                                                   self.namespace_id)
            while True:
                # Check to see if this greenlet should exit
                if self.shutdown.is_set():
                    clear_heartbeat_status(self.account_id, self.folder_id)
                    return False

                try:
                    self.poll()
                    self.heartbeat_status.publish(state='poll')

                # If we get a connection or API permissions error, then sleep
                # 2x poll frequency.
                except ConnectionError:
                    self.log.error('Error while polling', exc_info=True)
                    self.heartbeat_status.publish(state='poll error')
                    gevent.sleep(self.poll_frequency)

                gevent.sleep(self.poll_frequency)
        except ValidationError:
            # Bad account credentials; exit.
            self.log.error('Error while establishing the connection',
                           exc_info=True)
            return False

    @property
    def target_obj(self):
        # Return Contact or Event
        raise NotImplementedError

    @property
    def provider(self):
        raise NotImplementedError

    def last_sync(self, account):
        raise NotImplementedError

    def poll(self):
        raise NotImplementedError
