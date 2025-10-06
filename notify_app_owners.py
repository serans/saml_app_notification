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
    Configuration that automatically reads from ENV and CLI.

    To provide an argument via ENV, prepend APP_ to the variable name and use uppercase letters only.
    E.g. APP_API_URL, APP_SMTP_SERVER, etc.

    Note that api_password (ie APP_API_PASSWORD) can *only* be provided via ENV for security reasons.
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",  # ENV vars will be DB_HOST, DB_PORT, etc.
        cli_parse_args=True,  # Enable CLI argument parsing
        cli_avoid_json=True,  # Use simple CLI args instead of JSON
    )

    # API settings
    keycloak_server: str = Field("keycloak-authzsvc.cern.ch", description="Keycloak server address")
    api_client_id: str = Field("python-user-scripts", description="API client ID")
    api_url: str = Field("https://authorization-service-api.web.cern.ch/api/v1.0/", description="API URL")
    api_username: str = Field(description="API username")
    api_password: SecretStr = Field(
        description="API password (ENV only!)",
        json_schema_extra={'cli': False}
    )
    api_client_id: str = Field("python-user-scripts", description="API client ID")

    # Email Settings
    smtp_server: str = Field(description="SMTP server address")
    smtp_port: int = Field(25, description="SMTP server port")
    email_sender: str = Field("sso.noreply@cern.ch", description="Email sender address")
    dry_run: bool = Field(False, description="Enable dry run mode (no emails sent)")
    max_emails_to_send: int = Field(100, description="Maximum number of emails to send in one run. Used as a safety check: If more users need to be notified probably something is wrong with the process. In that case *no emails will be sent* and the script will fail")

    # Certificate Settings
    min_certificate_longevity: int = Field(
        60,
        description="If a certificate expires in less than this many days, the message specified in `message_template` will be sent to the corresponding application owners",
    )
    message_subject: str = Field("SAML certificates expiration", description="Subject line of the notification email")
    message_template_path: str = Field(description="Path of the template file to use for the notification email body")

if __name__ == "__main__":
    try:
        # This automatically parses ENV vars and CLI args
        config = Config() # pyright: ignore[reportCallIssue]
    except ValidationError as e:
        for error in e.errors():
            print(f"{ "".join([str(x) for x in error['loc']]) }: {error['msg']}", file=sys.stderr)
            print(f"\nFor more help, run '{sys.argv[0]} --help'\n", file=sys.stderr)
        sys.exit(-1)

    if not os.path.isfile(config.message_template_path):
        logging.error(f"Message template file '{config.message_template_path}' does not exist.")
        sys.exit(-1)
    with open(config.message_template_path, "r") as f:
        template = f.read()

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
        template=config.message_template_path,
        dry_run=config.dry_run,
    )

    deadline = datetime.now() + timedelta(days=config.min_certificate_longevity)
    logging.info(f"Filtering applications with certificates expiring before {deadline}")
    apps = SamlRegistry.get_apps().expiring_by(deadline)

    for app in apps:
        logging.info(f"App {app._id} expires on {app._expiration_date}")
        emailer.add(app) # type: ignore

    if emailer.num_messages() > config.max_emails_to_send:
        logging.error(f"Number of messages to send ({emailer.num_messages()}) exceeds the configured maximum ({config.max_emails_to_send}). Aborting")
        sys.exit(-1)

    emailer.send_all()
