Emails owners/admins of applications using the SAML provider and whose certificates are going to expire soon or have already expired.
Each recipient receives one email that contains a list of all their applications.

The script also publishes a prometheus-compatible `.txt` file with relevant metrics (number of expired certificates, number of processing errors, etc)

OKD-compatible kubernetes project files are available under `deployment/` to deploy the script at CERN

# Building

```bash
docker build -t user-contact-scripts:latest .

docker run --rm \
  -e APP_API_USERNAME=jon \
  -e APP_API_PASSWORD=$MY_PASSWORD \
  -e APP_SMTP_SERVER=test.com \
  -e APP_MESSAGE_TEMPLATE_PATH=/app/templates/your-template.txt \
  user-contact-scripts:latest
```

# Testing

```bash
pytest -q
```

# Credit
- Based on CERN's `user-contact-scripts`
- In turn largely based on AuthScripts project
