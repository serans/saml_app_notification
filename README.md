Emails owners/admins of applications using the SAML provider and whose certificates are going to expire soon or have already expired.
Each recipient receives one email that contains a list of all their applications.

The script also publishes a prometheus-compatible `.txt` file with relevant metrics (number of expired certificates, number of processing errors, etc)

OKD-compatible kubernetes project files are available under `deployment/` to deploy the script at CERN

# Credit
- Based on CERN's `user-contact-scripts`
- In turn largely based on AuthScripts project

