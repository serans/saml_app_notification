Emails owners/admins of applications using the SAML provider and whose certificates are going to expire soon or have already expired.
Each recipient receives one email that contains a list of all their applications.

The script also publishes a prometheus-compatible `.txt` file with relevant metrics (number of expired certificates, number of processing errors, etc)

OKD-compatible kubernetes project files are available under `deployment/` to deploy the script at CERN

# Building

```bash
docker build -t user-contact-scripts:latest .

docker run --rm \
  -e APP_LOGGING_LEVEL=DEBUG \
  -e APP_DRY_RUN=True \
  -e APP_KEYCLOAK_SERVER=auth.cern.ch \
  -e APP_API_USERNAME="$(cat .secrets/username)" \
  -e APP_API_PASSWORD="$(cat .secrets/password)" \
  -e APP_SMTP_SERVER=test.com \
  -v $(pwd)/templates/example.txt:/app/template.txt \
  user-contact-scripts:latest
```

# Testing

```bash
pytest -q
```

# Credit
- Based on CERN's `user-contact-scripts`
- In turn largely based on AuthScripts project
