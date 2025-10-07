import pytest
from emailer import Emailer
from registry import Contact, App
from datetime import datetime
import smtplib
from unittest import mock

def test_prepare_message_replacements():
    template = "App {APPLICATION_ID} owned by {RECIPIENT_NAME} notified for {APPLICATION_LIST}."
    recipient = Contact(email='user@example.com', name='Alice')
    app = App('my-app', '<root></root>')
    # set a fake expiration date for the test
    app._expiration_date = datetime(2026, 1, 2)

    e = Emailer(smtp_server='localhost', smtp_port=25, sender='noreply@example.com', subject='Test', template=template, dry_run=True)
    msg = e._prepare_message(recipient, [app])
    assert msg['To'] == 'user@example.com'
    assert msg['From'] == 'noreply@example.com'
    assert msg['Subject'] == 'Test'
    body = msg.get_content()
    assert 'Alice' in body
    assert 'my-app' in body
    assert '2026-01-02' in body


def test_prepare_message_no_expiration():
    template = "App {APPLICATION_ID} notified for {APPLICATION_LIST}."
    recipient = Contact(email='user@example.com', name='Bob')
    app = App('no-exp', '<root></root>')
    app._expiration_date = None

    e = Emailer(smtp_server='localhost', smtp_port=25, sender='noreply@example.com', subject='S', template=template, dry_run=True)
    msg = e._prepare_message(recipient, [app])
    body = msg.get_content()
    assert 'N/A' in body

def test_add_and_num_messages():
    owner1 = Contact(email='owner1@example.com', name='A')
    owner2 = Contact(email='owner2@example.com', name='B')
    app1 = App('id1', '<root></root>')
    app1._contact = [owner1]

    app2 = App('id2', '<root></root>')
    app2._contact = [owner1]

    app3 = App('id3', '<root></root>')
    app3._contact = [owner2]

    app4 = App('id3', '<root></root>')
    app4._contact = [owner1, owner2]  # multiple owners

    e = Emailer(smtp_server='localhost', smtp_port=25, sender='s', subject='sub', template='t', dry_run=True)
    
    e.add(app1)
    assert e.num_messages() == 1

    # same user, num_messages should still be 1
    e.add(app2)
    assert e.num_messages() == 1

    # different user, num_messages should be 2
    e.add(app3)
    assert e.num_messages() == 2

    # app with two previous owners that are already being notified, num_messages should still be 2
    e.add(app4)
    assert e.num_messages() == 2

def test_send_all_dry_run_prints(capsys):
    recipient = Contact(email='x@y.com', name='X')
    app = App('id2', '<root></root>')
    app._expiration_date = None
    app._contact = [recipient]

    template = "Hi {RECIPIENT_NAME} - {APPLICATION_LIST}"
    e = Emailer(smtp_server='localhost', smtp_port=25, sender='s', subject='sub', template=template, dry_run=True)
    e.add(app)
    e.send_all()
    captured = capsys.readouterr()
    assert 'Hi X' in captured.out
    assert 'id2' in captured.out

@mock.patch('smtplib.SMTP')
def test_send_all_uses_smtp(mock_smtp):
    # ensure that when not dry_run we call send_message on the SMTP server
    recipient = Contact(email='z@z.com', name='Z')
    app = App('id3', '<root></root>')
    app._expiration_date = None
    app._contact = [recipient]

    template = "X {RECIPIENT_NAME} {APPLICATION_ID}"
    # create Emailer not in dry run mode; patching SMTP ensures no network
    e = Emailer(smtp_server='smtp.test', smtp_port=1025, sender='s', subject='sub', template=template, dry_run=False)
    e.add(app)
    e.send_all()

    # verify send_message was called at least once
    assert mock_smtp.return_value.send_message.called
