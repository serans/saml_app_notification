# SAML-APP-NOTIFICATION

Emails owners/admins of applications using the SAML provider and whose certificates are going to expire soon or have already expired.
Each recipient receives one email that contains a list of all their applications.

OKD-compatible kubernetes project files are available under `kustomize/` to deploy the script at CERN

## Installation

Local Installation
1. (recommended) Create venv:
```
python3 -m venv .venv
source .venv/bin/activate
```

2. Run installation script
```
./utils.sh dev-install
```

Docker Image
```
./utils.sh docker-build
```

Will create an image called `saml_app_notification:latest`

## Usage

The basic idea is to set a deadline for the certificates, and if the expiration of a certificate happens earlier than the deadline, the app owner will be notified. All parameters can be set either through command line arguments or via ENV variables, and the email templates are written in [jinja](https://jinja.palletsprojects.com/en/stable/)

To run using the Docker image:
1. Create `.secrets/password` and `.secrets/username` with valid credentials.
2. Run `utils.sh docker-run`

## Help

- `./notify_app_owners.py --help` will give detailed usage information, and a description of each config parameter.
- `kustomize/base/certs_about_to_expire.job.yaml` contains a full working example

## Credits
- Based on CERN's `user-contact-scripts`
- In turn largely based on AuthScripts project
