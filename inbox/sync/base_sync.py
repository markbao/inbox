import gevent
import gevent.event
from datetime import datetime
from collections import Counter

from inbox.log import get_logger
logger = get_logger()
from inbox.basicauth import ConnectionError, ValidationError
from inbox.models.session import session_scope
from inbox.util.concurrency import retry_with_logging
from inbox.models import Account
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
        return base_poll(self.account_id, self.provider_instance,
                         self.last_sync, self.target_obj, self.set_last_sync,
                         self.log)


def base_poll(account_id, provider_instance, last_sync_fn, target_obj,
              set_last_sync_fn, log):
    """
    Query a remote provider for updates and persist them to the database.

    Parameters
    ----------
    account_id: int
        ID for the account whose items should be queried.
    db_session: sqlalchemy.orm.session.Session
        Database session
    provider: Interface to the remote item data provider.
        Must have a PROVIDER_NAME attribute and implement the get()
        method.

    """
    # Get a timestamp before polling, so that we don't subsequently miss remote
    # updates that happen while the poll loop is executing.
    sync_timestamp = datetime.utcnow()
    provider_name = provider_instance.PROVIDER_NAME

    with session_scope() as db_session:
        account = db_session.query(Account).get(account_id)
        last_sync = None
        if last_sync_fn(account) is not None:
            # Note explicit offset is required by e.g. Google calendar API.
            last_sync = datetime.isoformat(last_sync_fn(account)) + 'Z'

    items = provider_instance.get_items(last_sync)
    with session_scope() as db_session:
        account = db_session.query(Account).get(account_id)
        change_counter = Counter()
        for item in items:
            namespace_id = account.namespace.id

            assert item.uid is not None, 'Got remote item with null uid'
            assert isinstance(item.uid, basestring)

            local_item = db_session.query(target_obj).filter(
                target_obj.namespace == account.namespace,
                target_obj.provider_name == provider_name,
                target_obj.uid == item.uid).first()

            if local_item is not None:
                if item.deleted:
                    db_session.delete(local_item)
                    change_counter['deleted'] += 1
                else:
                    local_item.name = item.name
                    local_item.email_address = item.email_address
                    local_item.raw_data = item.raw_data
                    change_counter['updated'] += 1
            else:
                local_item = target_obj(
                    namespace_id=namespace_id, uid=item.uid,
                    name=item.name, provider_name=item.provider_name,
                    email_address=item.email_address, raw_data=item.raw_data)
                db_session.add(local_item)
                db_session.flush()

                change_counter['added'] += 1

        set_last_sync_fn(account, sync_timestamp)

        log.info('sync', added=change_counter['added'],
                 updated=change_counter['updated'],
                 deleted=change_counter['deleted'])

        db_session.commit()
