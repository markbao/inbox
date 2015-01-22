"""
Utility functions for creating, reading, updating and deleting events.
Called by the API.

"""
import uuid

from sqlalchemy.orm import subqueryload

from inbox.models import Event, Calendar
from inbox.api.err import InputError


def create(namespace, db_session, calendar, title, description, location,
           reminders, recurrence, when, participants):
    event = Event(
        namespace=namespace,
        calendar=calendar,
        uid=uuid.uuid4().hex,
        raw_data='',
        title=title,
        description=description,
        location=location,
        when=when,
        read_only=False,
        is_owner=True,
        participants={})

    event.participant_list = participants

    db_session.add(event)
    db_session.commit()

    return event


def read(namespace, db_session, event_public_id):
    return db_session.query(Event).filter(
        Event.namespace_id == namespace.id,
        Event.public_id == event_public_id).first()


def update(namespace, db_session, event_public_id, update_attrs):
    event = db_session.query(Event).filter(
        Event.namespace_id == namespace.id,
        Event.public_id == event_public_id).first()

    if not event:
        return event

    if event.read_only:
        raise InputError('Cannot update read_only event.')

    # Translate the calendar public_id to internal id
    calendar_public_id = update_attrs.get('calendar_id')

    if calendar_public_id:
        update_calendar = db_session.query(Calendar).filter(
            Calendar.namespace_id == namespace.id,
            Calendar.public_id == calendar_public_id).one()

        update_attrs['calendar_id'] = update_calendar.id

    for attr in update_attrs:
        if attr in ['title', 'description', 'location', 'when',
                    'participant_list', 'calendar_id']:
            setattr(event, attr, update_attrs[attr])

    db_session.add(event)
    db_session.commit()
    return event


def delete(namespace, db_session, event_public_id):
    """ Delete the event with public_id = `event_public_id`. """
    event = db_session.query(Event).filter(
        Event.namespace_id == namespace.id,
        Event.public_id == event_public_id).one()

    db_session.delete(event)
    db_session.commit()


##
# Calendar CRUD
##

def create_calendar(namespace, db_session, name, description):
    calendar = Calendar(
        namespace=namespace,
        name=name,
        description=description,
        uid=uuid.uuid4().hex,
        read_only=False)

    db_session.add(calendar)
    db_session.commit()

    return calendar


def read_calendar(namespace, db_session, calendar_public_id):
    eager = subqueryload(Calendar.events)
    return db_session.query(Calendar).filter(
        Calendar.namespace_id == namespace.id,
        Calendar.public_id == calendar_public_id). \
        options(eager). \
        first()


def update_calendar(namespace, db_session, calendar_public_id, update_attrs):
    eager = subqueryload(Calendar.events)
    calendar = db_session.query(Calendar).filter(
        Calendar.namespace_id == namespace.id,
        Calendar.public_id == calendar_public_id). \
        options(eager). \
        first()

    if not calendar:
        return calendar

    for attr in update_attrs:
        if attr in ['name', 'description']:
            setattr(calendar, attr, update_attrs[attr])

    db_session.commit()
    return calendar


def delete_calendar(namespace, db_session, calendar_public_id):
    """ Delete the calendar with public_id = `calendar_public_id`. """
    calendar = db_session.query(Calendar).filter(
        Calendar.namespace_id == namespace.id,
        Calendar.public_id == calendar_public_id).first()

    db_session.delete(calendar)
    db_session.commit()
