from sqlalchemy import Column, Integer, String, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship, backref, validates
from sqlalchemy.schema import UniqueConstraint

from inbox.sqlalchemy_ext.util import MAX_TEXT_LENGTH
from inbox.models.mixins import HasPublicID, HasEmailAddress, HasRevisions
from inbox.models.base import MailSyncBase
from inbox.models.message import Message
from inbox.models.namespace import Namespace


class Contact(MailSyncBase, HasRevisions, HasPublicID, HasEmailAddress):
    """Data for a user's contact."""
    API_OBJECT_NAME = 'contact'

    namespace_id = Column(ForeignKey(Namespace.id, ondelete='CASCADE'),
                          nullable=False)
    namespace = relationship(Namespace, load_on_pending=True)

    # A server-provided unique ID.
    uid = Column(String(64), nullable=False)
    name = Column(Text)
    raw_data = Column(Text)
    # A score to use for ranking contact search results. This should be
    # precomputed to facilitate performant search.
    score = Column(Integer)

    __table_args__ = (UniqueConstraint('uid', 'namespace_id'),)

    def update(self, session, contact):
        self.name = contact.name
        self.raw_data = contact.raw_data
        self.email_address = contact.email_address

    @validates('raw_data')
    def validate_length(self, key, value):
        return value if value is None else value[:MAX_TEXT_LENGTH]


class MessageContactAssociation(MailSyncBase):
    """
    Association table between messages and contacts.

    Examples
    --------
    If m is a message, get the contacts in the to: field with
    [assoc.contact for assoc in m.contacts if assoc.field == 'to_addr']

    If c is a contact, get messages sent to contact c with
    [assoc.message for assoc in c.message_associations if assoc.field ==
    ...  'to_addr']

    """
    contact_id = Column(Integer, ForeignKey(Contact.id, ondelete='CASCADE'),
                        primary_key=True)
    message_id = Column(Integer, ForeignKey(Message.id, ondelete='CASCADE'),
                        primary_key=True)
    field = Column(Enum('from_addr', 'to_addr', 'cc_addr', 'bcc_addr'))
    # Note: The `cascade` properties need to be a parameter of the backref
    # here, and not of the relationship. Otherwise a sqlalchemy error is thrown
    # when you try to delete a message or a contact.
    contact = relationship(
        Contact,
        backref=backref('message_associations', cascade='all, delete-orphan'))
    message = relationship(
        Message,
        backref=backref('contacts', cascade='all, delete-orphan'))
