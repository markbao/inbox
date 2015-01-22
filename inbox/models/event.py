from datetime import datetime
time_parse = datetime.utcfromtimestamp
from dateutil.parser import parse as date_parse

from sqlalchemy import (Column, String, ForeignKey, Text, Boolean, DateTime,
                        UniqueConstraint)
from sqlalchemy.orm import relationship, backref, validates

from inbox.sqlalchemy_ext.util import MAX_TEXT_LENGTH, JSON, MutableDict
from inbox.models.base import MailSyncBase
from inbox.models.mixins import HasPublicID, HasRevisions
from inbox.models.calendar import Calendar
from inbox.models.namespace import Namespace
from inbox.models.when import Time, TimeSpan, Date, DateSpan


TITLE_MAX_LEN = 1024
LOCATION_MAX_LEN = 255
RECURRENCE_MAX_LEN = 255
REMINDER_MAX_LEN = 255
OWNER_MAX_LEN = 1024
_LENGTHS = {'location': LOCATION_MAX_LEN,
            'owner': OWNER_MAX_LEN,
            'title': TITLE_MAX_LEN,
            'raw_data': MAX_TEXT_LENGTH}


class Event(MailSyncBase, HasRevisions, HasPublicID):
    """Data for events."""
    API_OBJECT_NAME = 'event'

    namespace_id = Column(ForeignKey(Namespace.id, ondelete='CASCADE'),
                          nullable=False)
    namespace = relationship(Namespace, load_on_pending=True)

    calendar_id = Column(ForeignKey(Calendar.id, ondelete='CASCADE'),
                         nullable=False)
    calendar = relationship(Calendar,
                            backref=backref('events', passive_deletes=True),
                            load_on_pending=True)

    # A server-provided unique ID.
    uid = Column(String(767, collation='ascii_general_ci'), nullable=False)

    raw_data = Column(Text, nullable=False)

    title = Column(String(TITLE_MAX_LEN), nullable=True)

    start = Column(DateTime, nullable=False)
    end = Column(DateTime, nullable=True)
    all_day = Column(Boolean, nullable=False)

    description = Column(Text, nullable=True)
    location = Column(String(LOCATION_MAX_LEN), nullable=True)

    owner = Column(String(OWNER_MAX_LEN), nullable=True)
    read_only = Column(Boolean, nullable=False)

    __table_args__ = (UniqueConstraint('uid', 'namespace_id', name='uuid'),)

    _participant_cascade = 'save-update, merge, delete, delete-orphan'
    participants_by_email = Column(MutableDict.as_mutable(JSON), default={},
                                   nullable=True)

    def __init__(self, *args, **kwargs):
        MailSyncBase.__init__(self, *args, **kwargs)
        if self.participants_by_email is None:
            self.participants_by_email = {}

    def update(self, session, event):
        self.raw_data = event.raw_data
        self.title = event.title
        self.description = event.description
        self.location = event.location
        self.start = event.start
        self.end = event.end
        self.all_day = event.all_day
        self.owner = event.owner
        self.read_only = event.read_only
        self.participants = event.participants

    @validates('owner', 'location', 'title', 'raw_data')
    def validate_length(self, key, value):
        max_len = _LENGTHS[key]
        return value if value is None else value[:max_len]

    @property
    def participants(self):
        return self.participants_by_email.values()

    @participants.setter
    def participants(self, participants):
        # We need to do this because the codes which creates event often
        # does it by calling something like event = Event(..., participants=[])
        # in this case self.participants_by_email is None since the constructor
        # hasn't run yet.
        if self.participants_by_email is None:
            self.participants_by_email = {}

        for p in participants:
            self.participants_by_email[p['email_address']] = p

    # Use a list for lowing to json to preserve original order
    @property
    def participant_list(self):
        return [{'name': p['name'],
                 'email': p['email_address'],
                 'status': p['status'],
                 'notes': p['notes'],
                 'id': p['public_id']}
                for p in self.participants_by_email.values()]

    @participant_list.setter
    def participant_list(self, p_list):
        """
        Updates the participant list based off of a list so that order can
        be preserved from creation time. (Doesn't allow re-ordering).

        """

        # First add or update the ones we don't have yet
        all_emails = []

        for p in p_list:
            all_emails.append(p['email'])
            existing = self.participants_by_email.get(p['email'])
            if existing:
                existing['name'] = p.get('name')
                existing['notes'] = p.get('notes')
                existing['status'] = p.get('status')
            else:
                new_p = {"name": p.get('name'),
                         "email_address": p['email'],
                         "notes": p.get('notes'),
                         "status": p.get('status')}
                self.participants_by_email[p['email']] = new_p

        # Now remove the ones we have stored that are not in the list
        remove = list(set(self.participants_by_email.keys()) - set(all_emails))
        for email in remove:
            del self.participants_by_email[email]

    @property
    def when(self):
        if self.all_day:
            start = self.start.date()
            end = self.end.date()
            return Date(start) if start == end else DateSpan(start, end)
        else:
            start = self.start
            end = self.end
            return Time(start) if start == end else TimeSpan(start, end)

    @when.setter
    def when(self, when):
        if 'time' in when:
            self.start = self.end = time_parse(when['time'])
            self.all_day = False
        elif 'start_time' in when:
            self.start = time_parse(when['start_time'])
            self.end = time_parse(when['end_time'])
            self.all_day = False
        elif 'date' in when:
            self.start = self.end = date_parse(when['date'])
            self.all_day = True
        elif 'start_date' in when:
            self.start = date_parse(when['start_date'])
            self.end = date_parse(when['end_date'])
            self.all_day = True

    @property
    def versioned_relationships(self):
        return ['participants_by_email']
