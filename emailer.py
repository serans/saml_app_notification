from datetime import datetime
from registry import Contact, App
import logging

class Emailer:
    def __init__(self, smtp_server:str, smtp_port:int, sender:str, subject:str, template:str, dry_run:bool):
        self._smtp_server = smtp_server
        self._smtp_port = smtp_port
        self._sender = sender
        self._dry_run = dry_run
        self._subject = subject
        self._template = template

        self._messages: dict[Contact, list[App]] = dict()

    def add(self, app:App):
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
        if self._dry_run:
            logging.info("Dry run mode enabled, not sending emails")
            self.print_messages()
        else:
            logging.info("Sending emails (not implemented yet)")
            # Here you would implement the actual email sending logic using smtplib or similar library

    def print_messages(self):
        for recipient, apps in self._messages.items():
            print(f"To: {recipient.email} ({recipient.name})")
            print(f"From: {self._sender}")
            body = self._template
            for app in apps:
                body = body.replace("{APPLICATION_ID}", app._id)
                body = body.replace("{EXPIRATION_DATE}", app._expiration_date.strftime('%Y-%m-%d'))
                body = body.replace("{DAYS_LEFT}", str((app._expiration_date - datetime.now()).days))
            print("Body:")
            print(body)
            print("-----")
