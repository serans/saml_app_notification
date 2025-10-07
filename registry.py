from authzsvc_api.apiWrapper import ApiWrapper
from datetime import datetime
import logging
import defusedxml.ElementTree as et
from OpenSSL import crypto

class Contact:
    def __init__(self, email:str, name:str):
        self.email = email
        self.name = name

class App:
    _NAMESPACE = {'ds': "http://www.w3.org/2000/09/xmldsig#"}

    def __init__(self, app_id:str, definition:str):
        self._id = app_id
        self._expiration_date:datetime | None = self._get_expiration_date(definition)
        self._contact = None

    def _get_expiration_date(self, definition:str) -> datetime | None:
        """ Parses the XML definition of the SAML application to extract the earliest certificate expiration date.

        Returns:
            datetime | None: The earliest expiration date found among the certificates, or None if no valid
            certificates are found or they have no expiration date.
        """
        root = et.fromstring(definition)
        certificates = root.findall('.//ds:X509Certificate', App._NAMESPACE)

        if not certificates:
            logging.info(f'No certificates found for application with id: {self._id}')
            return None

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
                continue

            if not cert_expiration:
                logging.error(f'No expiration date found for certificate in application with id: {id}')
                continue
            cert_expiration = cert_expiration.decode('utf-8')
            cert_expiration = datetime.strptime(cert_expiration, '%Y%m%d%H%M%SZ')

            if earliest_expiration_date:
                earliest_expiration_date = min(cert_expiration, earliest_expiration_date)
            else:
                earliest_expiration_date = cert_expiration

        return earliest_expiration_date


    @property
    def contacts(self) -> list[Contact]:
        """
        Fetches contact information (owners and administrators) for this application from the API.
        This method lazy-loads contact data to avoid overloading the API with requests.

        Raises:
            ValueError: If the application data cannot be accessed or is not found for the given application ID.
        """
        if self._contact is None:
            application_data = SamlRegistry.api.auth_api_get_all(
                request_url=f"Application",
                params = {
                    'field': ['id', 'ownerId', 'administratorsId', 'applicationIdentifier'],
                    'filter': f'id: {self._id}'
                }
            )

            if len(application_data) != 1:
                raise ValueError(f"Error accessing application data for application with id: {self._id}")

            app_info = application_data[0]

            self._contact:list[Contact] = list()
            if app_info["ownerId"]:
                owner = SamlRegistry.api.auth_api_get(
                    request_url=f'Identity/{app_info["ownerId"]}',
                    params={
                        'field': ["primaryAccountEmail", "displayName"],
                    }
                )
                if owner['primaryAccountEmail']:
                    self._contact.append(Contact(
                        email=owner['primaryAccountEmail'],
                        name=owner['displayName'])
                    )

            if app_info["administratorsId"]:
                administrator = SamlRegistry.api.auth_api_get(
                    request_url=f'Group/{app_info["administratorsId"]}',
                    params={
                        'field': ["primaryAccountEmail", "displayName"],
                    }
                )
                if 'primaryAccountEmail' in administrator and administrator['primaryAccountEmail']:
                    self._contact.append(Contact(
                        email=administrator['primaryAccountEmail'],
                        name=administrator['displayName'])
                    )

        return self._contact


class AppList(list[App]):
    def expiring_by(self, deadline: datetime) -> 'AppList':
        filtered = AppList()
        for app in self:
            if app._expiration_date is not None and app._expiration_date <= deadline:
                filtered.append(app)
        return filtered


class SamlRegistry:
    """ Interface to the SAML applications registry
    usage:
        SamlRegistry.init(server, username, password, api_url, client_id)
        apps = SamlRegistry.get_apps()
    """
    @staticmethod
    def init(server:str, username:str, password:str, api_url:str, client_id:str):
        SamlRegistry.api = ApiWrapper(
            server=server,
            realm='cern',
            username=username,
            password=password,
            api_url=api_url,
            client_id=client_id,
        )

    @staticmethod
    def get_apps() -> AppList:
        """ Fetch all SAML applications from the registry """

        logging.debug(f"Fetching saml provider ID")

        provider = SamlRegistry.api.auth_api_get_all(
            request_url=f"Registration/providers",
            params= {
                'field':'id',
                'filter':'authenticationProviderIdentifier:saml'
                }
        )

        if len(provider) != 1 and 'id' not in provider[0]:
            raise ValueError("Error accessing SAML provider ID")
        saml_provider_id = provider[0]['id']

        # auth_api_get_all returns a list of dicts, despite the type hint saying dict
        saml_apps:list = SamlRegistry.api.auth_api_get_all(
            request_url=f"Registration/{saml_provider_id}/search",
        ) # type: ignore
        logging.info(f"Got {len(saml_apps)} registrations")

        apps = AppList()
        for saml_app in saml_apps:
            app_id = saml_app['applicationId']
            definition = saml_app['definition']
            try:
                apps.append(App(app_id, definition))
            except et.ParseError as e:
                logging.error(f"app {app_id} error parsing XML: {e}")
                continue
        return apps
