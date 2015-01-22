from datetime import datetime, timedelta
from inbox.models import Event, Account

ACCOUNT_ID = 1
NAMESPACE_ID = 1
START = datetime.utcnow()
END = START + timedelta(0, 1)


def default_calendar(db_session):
    account = db_session.query(Account).filter(
        Account.id == ACCOUNT_ID).one()
    return account.default_calendar


def default_event(db_session):
    calendar = default_calendar(db_session)

    event = Event(namespace_id=NAMESPACE_ID,
                  calendar=calendar,
                  title='title',
                  description='',
                  location='',
                  read_only=False,
                  start=START,
                  end=END,
                  all_day=False,
                  provider_name='inbox',
                  raw_data='')
    db_session.add(event)
    db_session.commit()

    return event
