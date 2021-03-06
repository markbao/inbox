from datetime import datetime
import json

from inbox.log import get_logger
from inbox.heartbeat.config import (STATUS_DATABASE,
                                    get_alive_thresholds, get_redis_client,
                                    _get_alive_thresholds, _get_redis_client)


CONTACTS_FOLDER_ID = '-1'
EVENTS_FOLDER_ID = '-2'


class HeartbeatStatusKey(object):
    def __init__(self, account_id, folder_id):
        self.account_id = account_id
        self.folder_id = folder_id
        self.key = '{}:{}'.format(self.account_id, self.folder_id)

    def __repr__(self):
        return self.key

    def __lt__(self, other):
        if self.account_id != other.account_id:
            return self.account_id < other.account_id
        return self.folder_id < other.folder_id

    def __eq__(self, other):
        return self.account_id == other.account_id and \
            self.folder_id == other.folder_id

    @classmethod
    def all_folders(cls, account_id):
        return cls(account_id, '*')

    @classmethod
    def contacts(cls, account_id):
        return cls(account_id, CONTACTS_FOLDER_ID)

    @classmethod
    def events(cls, account_id):
        return cls(account_id, EVENTS_FOLDER_ID)

    @classmethod
    def from_string(cls, string_key):
        account_id, folder_id = map(int, string_key.split(':'))
        return cls(account_id, folder_id)


class HeartbeatStatusProxy(object):
    def __init__(self, account_id, folder_id, device_id=0):
        self.key = HeartbeatStatusKey(account_id, folder_id)
        self.device_id = device_id
        self.heartbeat_at = datetime.min
        self.value = {}

    def publish(self, **kwargs):
        schema = {'provider_name', 'folder_name', 'heartbeat_at', 'state',
                  'action'}

        def check_schema(**kwargs):
            for kw in kwargs:
                assert kw in schema

        try:
            client = get_redis_client(STATUS_DATABASE)
            check_schema(**kwargs)
            now = datetime.utcnow()
            self.value['heartbeat_at'] = str(now)
            self.value.update(kwargs or {})
            client.hset(self.key, self.device_id, json.dumps(self.value))
            self.heartbeat_at = now
            if 'action' in self.value:
                del self.value['action']
        except Exception:
            log = get_logger()
            log.error('Error while writing the heartbeat status',
                      account_id=self.key.account_id,
                      folder_id=self.key.folder_id,
                      device_id=self.device_id,
                      exc_info=True)


class AccountHeartbeatStatus(object):
    folders = []
    alive = False
    missing = False

    def __init__(self, account):
        if account is None or account == {}:
            self.missing = True
            return
        self.raw = account
        # initialize from JSON
        # if format {acct_id: ... }
        if len(account.keys()) == 1:
            self.account_id = account.keys()[0]
            account = account.get(self.account_id)
        self.alive, self.provider, raw_folders = account
        self.init_folders(raw_folders)

    def init_folders(self, raw_folders):
        self.folders = []
        for folder_id in raw_folders:
            self.folders.append(FolderHeartbeatStatus(raw_folders[folder_id],
                                                      folder_id))

    @property
    def dead_folders(self):
        return [f.folder_name for f in self.folders if not f.alive]

    @property
    def initial_sync(self):
        return any([f.status == 'initial' for f in self.folders])

    @property
    def poll_sync(self):
        # should also be 'not initial'
        return all([f.status == 'poll' for f in self.folders])


class FolderHeartbeatStatus(object):
    folder_id = None
    alive = False
    status = None

    def __init__(self, folder, folder_id=None):
        if folder_id:
            self.folder_id = folder_id
        else:
            self.folder_id = folder.keys()[0]
            folder = folder[self.folder_id]
        self.alive, self.folder_name, device = folder
        device_key = device.keys()[0]
        device_status = device[device_key]
        self.status = device_status['state']
        self.heartbeat_at = device_status['heartbeat_at']
        self.action = device_status['action']


def get_heartbeat_status(host=None, port=6379, account_id=None):
    if host:
        thresholds = _get_alive_thresholds()
        client = _get_redis_client(host, port, STATUS_DATABASE)
    else:
        thresholds = get_alive_thresholds()
        client = get_redis_client(STATUS_DATABASE)
    batch_client = client.pipeline()

    keys = []
    match_key = None
    if account_id:
        match_key = HeartbeatStatusKey.all_folders(account_id)
    for k in client.scan_iter(match=match_key, count=100):
        if k == 'ElastiCacheMasterReplicationTimestamp':
            continue
        batch_client.hgetall(k)
        keys.append(k)
    values = batch_client.execute()

    now = datetime.utcnow()

    accounts = {}
    for (k, v) in zip(keys, values):
        key = HeartbeatStatusKey.from_string(k)
        account_alive, provider_name, folders = accounts.get(key.account_id,
                                                             (True, '', {}))
        folder_alive, folder_name, devices = folders.get(key.folder_id,
                                                         (True, '', {}))

        for device_id in v:
            value = json.loads(v[device_id])

            provider_name = value['provider_name']
            folder_name = value['folder_name']

            heartbeat_at = datetime.strptime(value['heartbeat_at'],
                                             '%Y-%m-%d %H:%M:%S.%f')
            state = value.get('state', None)
            action = value.get('action', None)

            if key.folder_id == -1:
                # contacts
                device_alive = (now - heartbeat_at) < thresholds.contacts
            elif key.folder_id == -2:
                # events
                device_alive = (now - heartbeat_at) < thresholds.events
            elif provider_name == 'eas' and action == 'ping':
                # eas w/ ping
                device_alive = (now - heartbeat_at) < thresholds.eas
            else:
                device_alive = (now - heartbeat_at) < thresholds.base
            device_alive = device_alive and \
                (state in set([None, 'initial', 'poll']))

            devices[int(device_id)] = {'heartbeat_at': str(heartbeat_at),
                                       'state': state,
                                       'action': action,
                                       'alive': device_alive}

            # a folder is alive if and only if all the devices handling that
            # folder are alive
            folder_alive = folder_alive and device_alive

            folders[key.folder_id] = (folder_alive, folder_name, devices)

            # an account is alive if and only if all the folders of the account
            # are alive
            account_alive = account_alive and folder_alive

            accounts[key.account_id] = (account_alive, provider_name, folders)

    return accounts


def clear_heartbeat_status(account_id, folder_id=None, device_id=None):
    try:
        client = get_redis_client(STATUS_DATABASE)
        batch_client = client.pipeline()
        if folder_id:
            match_name = HeartbeatStatusKey(account_id, folder_id)
        else:
            match_name = HeartbeatStatusKey.all_folders(account_id)
        for name in client.scan_iter(match_name, 100):
            if device_id:
                batch_client.hdel(name, device_id)
            else:
                batch_client.delete(name)
        batch_client.execute()
    except Exception:
        log = get_logger()
        log.error('Error while deleting from the heartbeat status',
                  account_id=account_id,
                  folder_id=(folder_id or 'all'),
                  device_id=(device_id or 'all'),
                  exc_info=True)
