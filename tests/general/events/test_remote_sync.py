import pytest

from tests.util.base import config
from tests.general.events.conftest import EventsProviderStub

# Need to set up test config before we can import from
# inbox.models.tables.
config()
from inbox.models import Event

NAMESPACE_ID = 1

# STOPSHIP(emfree): Test multiple distinct remote providers


@pytest.fixture(scope='function')
def alternate_events_provider(config, db):
    return EventsProviderStub('alternate_provider')


# def test_add_events(events_provider, event_sync, db):
#     """Test that added events get stored."""
#     num_original_local_events = db.session.query(Event). \
#         filter_by(namespace_id=NAMESPACE_ID).count()

#     events_provider.supply_event('subj')
#     events_provider.supply_event('subj2')

#     event_sync.provider_instance = events_provider
#     event_sync.poll()

#     num_current_local_events = db.session.query(Event). \
#         filter_by(namespace_id=NAMESPACE_ID).count()
#     assert num_current_local_events - num_original_local_events == 2


# def test_update_event(events_provider, event_sync, db):
#     """Test that subsequent event updates get stored."""
#     events_provider.supply_event('subj')
#     event_sync.provider_instance = events_provider
#     event_sync.poll()

#     results = db.session.query(Event).filter_by(
#         namespace_id=NAMESPACE_ID).all()
#     titles = [r.title for r in results]
#     assert 'subj' in titles

#     events_provider.__init__()
#     events_provider.supply_event('newsubj')
#     event_sync.poll()
#     db.session.commit()

#     results = db.session.query(Event).filter_by(
#         namespace_id=NAMESPACE_ID).all()
#     subjs = [r.title for r in results]
#     assert 'newsubj' in subjs


def test_multiple_remotes(events_provider, alternate_events_provider,
                          event_sync, db):
    events_provider.supply_event('subj')
    event_sync.provider_instance = events_provider
    event_sync.poll()

    alternate_events_provider.supply_event('subj2')
    event_sync.provider_instance = alternate_events_provider
    event_sync.poll()
    db.session.commit()

    result = db.session.query(Event). \
        filter_by(namespace_id=NAMESPACE_ID,
                  provider_name='test_provider').one()
    alternate_result = db.session.query(Event). \
        filter_by(namespace_id=NAMESPACE_ID,
                  provider_name='alternate_provider').one()
    # Check that both events were persisted, even though they have the same
    # uid.
    assert result.title == 'subj'
    assert alternate_result.title == 'subj2'


# def test_deletes(events_provider, event_sync, db):
#     num_original_events = db.session.query(Event).\
#         filter_by(namespace_id=NAMESPACE_ID).count()

#     events_provider.supply_event('subj')
#     event_sync.provider_instance = events_provider
#     event_sync.poll()

#     num_current_events = db.session.query(Event).\
#         filter_by(namespace_id=NAMESPACE_ID).count()
#     assert num_current_events - num_original_events == 1

#     events_provider.__init__()
#     events_provider.supply_event('subj', deleted=True)
#     event_sync.poll()

#     num_current_events = db.session.query(Event).count()
#     assert num_current_events == num_original_events
