from OpenSSL import crypto
from datetime import datetime, timedelta
from saml_registry.registry import App, AppList, SamlRegistry
import pytest

def _make_cert_notafter(dt: datetime) -> str:
	"""Create a self-signed PEM certificate and return the base64 body text suitable
	for embedding inside an XML <ds:X509Certificate> element (no header/footer).
	"""
	# generate key
	key = crypto.PKey()
	key.generate_key(crypto.TYPE_RSA, 2048)

	cert = crypto.X509()
	cert.get_subject().CN = 'test'
	cert.set_serial_number(1)
	cert.gmtime_adj_notBefore(0)
	# compute seconds delta from now to target dt
	# OpenSSL expects notAfter in format YYYYMMDDHHMMSSZ when setting via gmtime_adj_*
	# use absolute setting via ASN1-time by setting notAfter directly on the cert object
	# For simplicity, set notAfter relative to now using gmtime_adj_notAfter
	delta = int((dt - datetime.now()).total_seconds())
	cert.gmtime_adj_notAfter(delta)
	cert.set_issuer(cert.get_subject())
	cert.set_pubkey(key)
	cert.sign(key, 'sha256')

	pem = crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode('utf-8')
	# strip header/footer and newlines to match expected in registry._get_expiration_date
	body = ''.join(line for line in pem.splitlines() if '-----' not in line)
	return body


def test_get_expiration_date_no_cert():
	xml = '<root></root>'
	a = App('app-no-cert', xml)
	assert a._expiration_date is None


def test_get_expiration_date_single_cert():
	target = datetime.now() + timedelta(days=365)
	cert_body = _make_cert_notafter(target)
	xml = f'<root xmlns:ds="http://www.w3.org/2000/09/xmldsig#"><ds:X509Certificate>{cert_body}</ds:X509Certificate></root>'
	a = App('app-single', xml)
	assert a._expiration_date is not None
	# Compare date portion only to avoid minor timezone/seconds differences
	assert a._expiration_date.date() == target.date()


def test_get_expiration_date_multiple_certs_chooses_earliest():
	earlier = datetime.now() + timedelta(days=30)
	later = datetime.now() + timedelta(days=400)
	b1 = _make_cert_notafter(earlier)
	b2 = _make_cert_notafter(later)
	xml = (
		'<root xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
		f'<ds:X509Certificate>{b1}</ds:X509Certificate>'
		f'<ds:X509Certificate>{b2}</ds:X509Certificate>'
		'</root>'
	)
	a = App('app-multi', xml)
	assert a._expiration_date is not None
	# registry implementation picks earliers expiration
	assert a._expiration_date.date() == earlier.date()


def test_get_expiration_date_ignores_invalid_certs():
	# invalid certificate body should be skipped and result in None
	xml = '<root xmlns:ds="http://www.w3.org/2000/09/xmldsig#"><ds:X509Certificate>INVALID</ds:X509Certificate></root>'
	a = App('app-bad-cert', xml)
	assert a._expiration_date is None


def test_contacts_property_success(monkeypatch):
	# prepare fake API responses
	app_info = {'id': 'my-app', 'ownerId': 'owner-1', 'administratorsId': 'group-1', 'applicationIdentifier': 'x'}
	owner = {'primaryAccountEmail': 'owner@example.com', 'displayName': 'Owner Name'}
	admin = {'primaryAccountEmail': 'admin@example.com', 'displayName': 'Admin Name'}

	class FakeAPI:
		def auth_api_get_all(self, request_url, params=None):
			if request_url == 'Application':
				return [app_info]
			return []

		def auth_api_get(self, request_url, params=None):
			if request_url.startswith('Identity/'):
				return owner
			if request_url.startswith('Group/'):
				return admin
			return {}

	monkeypatch.setattr(SamlRegistry, 'api', FakeAPI(), raising=False)

	# App will call contacts which uses SamlRegistry.api
	a = App('my-app', '<root></root>')
	contacts = a.contacts
	assert any(c.email == 'owner@example.com' for c in contacts)
	assert any(c.email == 'admin@example.com' for c in contacts)


def test_contacts_property_bad_response(monkeypatch):
	class BadAPI:
		def auth_api_get_all(self, request_url, params=None):
			return []

	monkeypatch.setattr(SamlRegistry, 'api', BadAPI(), raising=False)
	a = App('no-app', '<root></root>')
	with pytest.raises(ValueError):
		_ = a.contacts


def test_applist_expiring_by():
	now = datetime.now()
	a1 = App('a1', '<root></root>')
	a2 = App('a2', '<root></root>')
	a1._expiration_date = now + timedelta(days=1)
	a2._expiration_date = now + timedelta(days=10)
	al = AppList([a1, a2])
	filtered = al.expiring_by(now + timedelta(days=5))
	assert len(filtered) == 1
	assert filtered[0]._id == 'a1'

