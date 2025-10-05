#!/usr/bin/env python3
import datetime
import sys
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from authzsvc_api.apiWrapper import ApiWrapper
from OpenSSL import crypto
import defusedxml.ElementTree as ET
import logging

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
    keycloak_server: str = Field("keycloak-authzsvc-dev.cern.ch", description="Keycloak server address")
    api_client_id: str = Field("python-user-scripts", description="API client ID")
    api_url: str = Field("https://authorization-service-api-dev.web.cern.ch/api/v1.0/", description="API URL")
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
    expiration_warning_days: int = Field(
        60,
        description="Send warning if a certificate expires within this number of days"
    )
    expired_certificate_template: str = Field(description="Template for expired certificates")
    expiring_soon_certificate_template: str = Field(description="Template for certificates expiring soon")

def get_saml_apps(api: ApiWrapper) -> dict[str, str]:
    logging.info(f"Fetching saml provider ID")

    provider = api.auth_api_get_all(
        request_url=f"Registration/providers",
        params= {
            'field':'id',
            'filter':'authenticationProviderIdentifier:saml'
            }
    )

    if len(provider) != 1 and 'id' not in provider[0]:
        raise ValueError("Error accessing saml provider ID")
    saml_provider_id = provider[0]['id']

    # auth_api_get_all returns a list of dicts, despite the type hint saying dict
    saml_apps:list = api.auth_api_get_all(
        request_url=f"Registration/{saml_provider_id}/search",
    ) # type: ignore
    logging.info(f"Got {len(saml_apps)} registrations")

    # Index apps by applicationId
    return {app['applicationId']: app['definition'] for app in saml_apps}

def get_apps_expiration(api, apps: dict) -> dict[str, datetime.datetime]:

    logging.debug('Finding the applications with expiring certificates')
    NAMESPACE = {'ds': "http://www.w3.org/2000/09/xmldsig#"}

    apps_expiration_date = {}
    for id, definition in apps.items():
        # TODO: do we need this?
        # definition = definition.replace('\n', '')
        try:
            root = ET.fromstring(definition) 
        except ET.ParseError as e:
            logging.error(f'XML Parse error, {e}')
            logging.error(f'Issue coming from the registration of the application with the id: {id}')
            continue

        certificates = root.findall('.//ds:X509Certificate', NAMESPACE)

        if not certificates:
            logging.info(f'No certificates found for application with id: {id}')
            continue

        earliest_expiration_date = None
        for cert in certificates:
            cert_text = cert.text.replace(' ','')

            #Add the correct formating to the certificate
            cert_text = f"-----BEGIN CERTIFICATE-----\n{cert_text}\n-----END CERTIFICATE-----"
            cert_text = cert_text.encode('utf-8')

            try:
                certificate_data = crypto.load_certificate(crypto.FILETYPE_PEM, cert_text)
                cert_expiration = certificate_data.get_notAfter()
            except crypto.Error as e:
                logging.error(f'This certificate cannot be decoded. Decoding error {e}')
                logging.error(f'Certificate with problem: {cert_text}')
            
            if not cert_expiration:
                logging.error(f'No expiration date found for certificate in application with id: {id}')
                continue
            cert_expiration = datetime.datetime.strptime(cert_expiration.decode('utf-8'), '%Y%m%d%H%M%SZ')

            if earliest_expiration_date:
                earliest_expiration_date = max(cert_expiration, earliest_expiration_date)
            else:
                earliest_expiration_date = cert_expiration

        if earliest_expiration_date:
            apps_expiration_date[id] = earliest_expiration_date
    return apps_expiration_date

def get_app_contact_details(api: ApiWrapper, app_id: str) -> list[dict]:
    application_data = api.auth_api_get_all(
        request_url=f"Application",
        params = {
            'field': ['id', 'ownerId', 'administratorsId', 'applicationIdentifier'],
            'filter': f'id: {app_id}'
        }
    )

    if len(application_data) != 1:
        raise ValueError(f"Error accessing application data for application with id: {app_id}")
    
    app_info = application_data[0]
    
    contact_info = list()
    if app_info["ownerId"]:
        owner = api.auth_api_get(
            request_url=f'Identity/{app_info["ownerId"]}',
            params={
                'field': ["primaryAccountEmail", "displayName"],
            }
        )
        if owner['primaryAccountEmail']:
            contact_info.append({
                'email': owner['primaryAccountEmail'],
                'name': owner['displayName']
            })

    if app_info["administratorsId"]:
        administrator = api.auth_api_get(
            request_url=f'Group/{app_info["administratorsId"]}',
            params={
                'field': ["primaryAccountEmail", "displayName"],
            }
        )
        if administrator['primaryAccountEmail']:
            contact_info.append({
                # 'email': administrator['primaryAccountEmail'], <- shouldn't we use this?
                'email':f"{administrator['groupIdentifier']}@cern.ch",
                'name': administrator['displayName']
            })

    return contact_info

def notify_apps_for_deadline(api: ApiWrapper, apps: dict, apps_expiration: dict, template: str, deadline: datetime.datetime):
    apps_to_notify = {}
    deadline = datetime.datetime.now() + datetime.timedelta(days=config.expiration_warning_days)
    for app_id, expiration_date in apps_expiration.items():
        if expiration_date < deadline:
            apps_to_notify[app_id] = get_app_contact_details(api, app_id)
    if len(apps_to_notify) > config.max_emails_to_send:
        logging.error(f"Number of applications to notify ({len(apps_to_notify)}) exceeds the maximum allowed ({config.max_emails_to_send}). Aborting.")
        sys.exit(-1)
    
    for app_id, contacts in apps_to_notify.items():
        expiration_date = apps_expiration[app_id]
        for contact in contacts:
            email_body = template.replace("{APPLICATION_ID}", app_id)
            email_body = email_body.replace("{EXPIRATION_DATE}", expiration_date.strftime('%Y-%m-%d'))
            email_body = email_body.replace("{CONTACT_NAME}", contact['name'] or 'CERN SSO User')
            email_body = email_body.replace("{DAYS_LEFT}", str((expiration_date - datetime.datetime.now()).days))
            print(f"Sending email to {contact['email']} about application {app_id} expiring on {expiration_date.strftime('%Y-%m-%d')}")
            if not config.dry_run:
                import smtplib
                from email.mime.text import MIMEText

                msg = MIMEText(email_body, 'plain')
                msg['Subject'] = f"[Action Required] Certificate for application {app_id} is expiring soon"
                msg['From'] = config.email_sender
                msg['To'] = contact['email']

                with smtplib.SMTP(config.smtp_server, config.smtp_port) as server:
                    server.sendmail(config.email_sender, [contact['email']], msg.as_string())

if __name__ == "__main__":
    """Main application function."""
    # This automatically parses ENV vars and CLI args
    try:
        config = Config() # pyright: ignore[reportCallIssue]
    except ValidationError as e:
        for error in e.errors():
            print(f"{ "".join([str(x) for x in error['loc']]) }: {error['msg']}", file=sys.stderr)
            print(f"\nFor more help, run '{sys.argv[0]} --help'\n", file=sys.stderr)
        sys.exit(-1)
    
    api = ApiWrapper(
        server=config.keycloak_server,
        realm='cern',
        username=config.api_username,
        password=config.api_password.get_secret_value(),
        api_url=config.api_url,
        client_id=config.api_client_id,
    )

    apps = get_saml_apps(api)
    apps_expiration = get_apps_expiration(api, apps)

    apps_to_contact = {}
    num_emails = 0
    for app_id, expiration in apps_expiration.items():
        if expiration < datetime.datetime.now() + datetime.timedelta(days=config.expiration_warning_days):
            apps_to_contact[app_id] = get_app_contact_details(api, app_id)
            num_emails += len(apps_to_contact[app_id])

    if num_emails > config.max_emails_to_send:
        logging.error(f"Number of emails to send ({num_emails}) exceeds the maximum allowed ({config.max_emails_to_send}). Aborting.")
        sys.exit(-1)

    # TODO: prepare all the emails to be sent