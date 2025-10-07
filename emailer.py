from registry import Contact, App
from email.message import EmailMessage
import smtplib
import logging
from jinja2 import Template

class Emailer:
    def __init__(self, smtp_server:str, smtp_port:int, sender:str, subject:str, template:str, dry_run:bool):
        self._smtp_server = smtp_server
        self._smtp_port = smtp_port
        self._sender = sender
        self._dry_run = dry_run
        self._subject = subject
        self._template = template
        self._server = None

        self._messages: dict[Contact, list[App]] = dict()
        if not self._dry_run:
            logging.debug(f"Connecting with SMTP server {self._smtp_server}:{self._smtp_port}")
            self._server = smtplib.SMTP(self._smtp_server, self._smtp_port)


    def add(self, app:App):
        """
        Add an application to the list of apps whose owners will be notified.
        Note that if an owner has multiple apps, they will receive a single email listing all apps.
        """
        if app.contacts is None:
            logging.error(f"App {app._id} has no contact information, skipping")
            return
        for contact in app.contacts:
            if contact not in self._messages:
                self._messages[contact] = [app]
            else:
                self._messages[contact].append(app)

    def num_messages(self) -> int:
        return len(self._messages)

    def send_all(self):
        """ Send all messages, or print them if dry_run is True """
        if not self._dry_run and not self._server:
            raise Exception("SMTP server is not connected")

        for recipient, apps in self._messages.items():
            message = self._prepare_message(recipient, apps)
            logging.info(f"Sending email to {recipient.email} ({len(apps)} apps)")

            if self._dry_run:
                print(message)
                print("----------------------------------------")
            else:
                self._server.send_message(message)

    def _prepare_message(self, recipient: Contact, apps:list[App]) -> EmailMessage:
        message = EmailMessage()
        message['To'] = recipient.email
        message['Subject'] = self._subject
        message['From'] = self._sender

        template = self._template
        context = {
            'recipient': {'email': recipient.email, 'name': recipient.name},
            'apps': [{
                'id':app._id, 
                'expiration': app._expiration_date.strftime("%Y-%m-%d") 
                    if app._expiration_date else "N/A"}
                for app in apps]
        }

        body = Template(template).render(**context)
        message.set_content(body)
        return message
