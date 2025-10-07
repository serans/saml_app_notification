#!/usr/bin/env python3

from datetime import datetime, timedelta
from emailer import Emailer
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from registry import SamlRegistry
import logging
import sys
import os

class Config(BaseSettings):
    """
    Sends notification emails to SAML application owners if their saml certificates are expiring in less than `min_certificate_longevity` days

    All arguments except `api_password` can be passed either as command line arguments or as ENV variables.
    - To pass as ENV variables, prepend APP_ to the variable name, and use uppercase only (eg APP_API_URL)
    - APP_API_PASSWORD must be set as an ENV variable and can't be passed as a cli argument
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",  # ENV vars will be DB_HOST, DB_PORT, etc.
        cli_parse_args=True,  # Enable CLI argument parsing
        cli_avoid_json=True,  # Use simple CLI args instead of JSON
    )

    # Logging settings
    logging_level: str = Field("INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
    logging_format: str = Field("%(asctime)s - %(levelname)s - %(message)s", description="Logging format")

    # API settings
    keycloak_server: str = Field("auth.cern.ch", description="Keycloak server address")
    api_client_id: str = Field("python-user-scripts", description="API client ID")
    api_url: str = Field("https://authorization-service-api.web.cern.ch/api/v1.0/", description="API URL")
    api_username: str = Field(description="API username")
    api_password: SecretStr = Field(
        description="API password (ENV only!)",
        json_schema_extra={'cli': False}
    )
    api_client_id: str = Field("python-user-scripts", description="API client ID")

    # Email Settings
    smtp_server: str = Field('cernmxxx.cern.ch', description="SMTP server address")
    smtp_port: int = Field(25, description="SMTP server port")
    email_sender: str = Field("sso.noreply@cern.ch", description="Email sender address")
    dry_run: bool = Field(False, description="Prints emails in screen instead of sending them")
    max_emails_to_send: int = Field(100, description="Maximum number of emails to send. Script fails BEFORE sending any email if it's expected to send this many")

    # Certificate Settings
    min_certificate_longevity: int = Field(
        60,
        description="If a certificate expires in less than this many days, the message specified in 'message_template' will be sent to the corresponding application owners",
    )
    message_subject: str = Field("SAML certificates expiration", description="Subject line of the notification email")
    message_template_path: str = Field("/app/template.jinja", description="Path of the template file to use for the notification email body")

if __name__ == "__main__":
    # Read configuration from command line args or ENV variables
    try:
        config = Config() # pyright: ignore[reportCallIssue]
    except ValidationError as e:
        for error in e.errors():
            print(f"{ ''.join([str(x) for x in error['loc']]) }: {error['msg']}", file=sys.stderr)
        print(f"\nFor more help, run '{sys.argv[0]} --help'\n", file=sys.stderr)
        sys.exit(-1)

    # Configure logging
    try:
        logging.basicConfig(level=config.logging_level, format=config.logging_format)
    except ValueError as e:
        print(f"Invalid logging level or format '{config.logging_level}' '{config.logging_format}: {e}", file=sys.stderr)
        sys.exit(-1)

    # Check that the template file exists and read it
    if not os.path.isfile(config.message_template_path):
        logging.error(f"Message template file '{config.message_template_path}' does not exist.")
        sys.exit(-1)
    with open(config.message_template_path, "r") as f:
        template = f.read()

    # Initialize registry and emailer
    SamlRegistry.init(
        server=config.keycloak_server,
        username=config.api_username,
        password=config.api_password.get_secret_value(),
        api_url=config.api_url,
        client_id=config.api_client_id,
    )

    emailer = Emailer(
        smtp_server=config.smtp_server,
        smtp_port=config.smtp_port,
        sender=config.email_sender,
        subject=config.message_subject,
        template=template,
        dry_run=config.dry_run,
    )

    # Read Saml apps that expire within the provided deadline
    deadline = datetime.now() + timedelta(days=config.min_certificate_longevity)
    logging.info(f"Filtering applications with certificates expiring before {deadline}")
    apps = SamlRegistry.get_apps().expiring_by(deadline)

    logging.info(f"Found {len(apps)} applications with certificates expiring before {deadline}")

    if len(apps) == 0:
        sys.exit(0)

    # Add apps to be notified by email
    for app in apps:
        logging.info(f"App {app._id} expires on {app._expiration_date}")
        emailer.add(app) # type: ignore

    if emailer.num_messages() > config.max_emails_to_send:
        logging.error(f"Number of messages to send ({emailer.num_messages()}) exceeds the configured maximum ({config.max_emails_to_send}). Aborting")
        sys.exit(-1)

    emailer.send_all()
