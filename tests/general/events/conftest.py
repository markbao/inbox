from pytest import fixture


@fixture(scope='function')
def event_sync(config, db):
    from inbox.events.base import EventSync
    return EventSync('gmail', 1, 1)


@fixture(scope='function')
def events_provider(config, db):
    return EventsProviderStub()


class EventsProviderStub(object):
    """
    Events provider stub to stand in for an actual provider.
    See ContactsProviderStub.

    """
    def __init__(self, provider_name='test_provider'):
        self._events = []
        self._next_uid = 1
        self.PROVIDER_NAME = provider_name

    def supply_event(self, title='', deleted=False):
        from inbox.events.google import GoogleEvent

        when = '2011-01-21 02:37:21'
        self._events.append(GoogleEvent(namespace_id=1,
                                        uid=str(self._next_uid),
                                        title=title,
                                        description='',
                                        location='',
                                        start=when,
                                        end=when,
                                        all_day=False,
                                        owner='',
                                        read_only=False,
                                        raw_data='',
                                        deleted=deleted,
                                        participants=[]))
        self._next_uid += 1

    def get_calendars(self):
        name = '{}._calendar'.format(self.PROVIDER_NAME)
        return [dict(uid=1,
                     name=name,
                     read_only=True,
                     description='',
                     deleted=False)]

    def get_events(self, calendar_uid, sync_from_time=None):
        return self._events
