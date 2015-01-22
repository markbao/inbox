from datetime import datetime
from collections import Counter

from inbox.log import get_logger
logger = get_logger()
from inbox.models.session import session_scope
from inbox.models import Contact, Account
from inbox.contacts.google import GoogleContactsProvider
from inbox.sync.base_sync import BaseSync
from inbox.util.debug import bind_context

__provider_map__ = {'gmail': GoogleContactsProvider}


class ContactSync(BaseSync):
    """
    Per-account contact sync engine.

    Parameters
    ----------
    account_id: int
        The ID for the user account for which to fetch contact data.

    poll_frequency: int
        In seconds, the polling frequency for querying the contacts provider
        for updates.

    Attributes
    ---------
    log: logging.Logger
        Logging handler.

    """
    def __init__(self, provider_name, account_id, namespace_id,
                 poll_frequency=300):
        bind_context(self, 'contactsync', account_id)
        self.log = logger.new(account_id=account_id, component='contact sync')
        self.log.info('Begin syncing contacts...')

        BaseSync.__init__(self, account_id, namespace_id, poll_frequency, -1,
                          'Contacts', provider_name)

    @property
    def provider(self):
        return __provider_map__[self.provider_name]

    @property
    def target_obj(self):
        return Contact

    def last_sync(self, account):
        return account.last_synced_contacts

    def set_last_sync(self, account, dt):
        account.last_synced_contacts = dt

    def poll(self):
        return poll_contacts(
            self.account_id, self.provider_instance, self.last_sync,
            self.target_obj, self.set_last_sync, self.log)


def poll_contacts(account_id, provider_instance, last_sync_fn, target_obj,
                  set_last_sync_fn, log):
    """
    Query a remote provider for Contact adds, updates and deletes and persist
    them to the database.

    Parameters
    ----------
    account_id: int
        ID for the account whose items should be queried.
    db_session: sqlalchemy.orm.session.Session
        Database session
    provider: Interface to the remote item data provider.
        Must have a PROVIDER_NAME attribute and implement the get() method.

    """
    # Get a timestamp before polling, so that we don't subsequently miss remote
    # updates that happen while the poll loop is executing.
    sync_timestamp = datetime.utcnow()

    with session_scope() as db_session:
        account = db_session.query(Account).get(account_id)
        last_sync = None
        if last_sync_fn(account) is not None:
            # Note explicit offset is required by e.g. Google calendar API.
            last_sync = datetime.isoformat(last_sync_fn(account)) + 'Z'

    items = provider_instance.get_items(last_sync)

    with session_scope() as db_session:
        account = db_session.query(Account).get(account_id)
        namespace_id = account.namespace.id

        change_counter = Counter()
        for item in items:
            assert item.uid is not None, 'Got remote item with null uid'
            assert isinstance(item.uid, basestring)

            local_item = db_session.query(target_obj).filter(
                target_obj.namespace == account.namespace,
                target_obj.uid == item.uid).first()

            if local_item is not None:
                if item.deleted:
                    db_session.delete(local_item)
                    change_counter['deleted'] += 1
                else:
                    local_item.update(item)
                    change_counter['updated'] += 1
            else:
                local_item = target_obj(namespace_id=namespace_id,
                                        uid=item.uid)
                local_item.update(item)
                db_session.add(local_item)
                db_session.flush()
                change_counter['added'] += 1

        set_last_sync_fn(account, sync_timestamp)

        log.info('sync', added=change_counter['added'],
                 updated=change_counter['updated'],
                 deleted=change_counter['deleted'])

        db_session.commit()
