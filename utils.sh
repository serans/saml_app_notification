#!/bin/bash

# dev-install.sh - helper to install requirements and build the docker image
set -euo pipefail

export PIP_EXTRA_INDEX_URL=https://cern-nexus.web.cern.ch/repository/pypi-internal/simple
export PIP_TRUSTED_HOST=cern-nexus.web.cern.ch

usage() {
	cat <<EOF
Usage: $(basename "$0") <command> [options]

Commands:
	install             Install runtime requirements from requirements.txt
	dev-install         Install development requirements (editable install of the package)
	test			    Run tests with pytest
	docker-build [TAG]  Build Docker image from the Dockerfile in this repo. Optional TAG (default: saml_app_notification:latest)
	docker-run [TAG]    Run Docker image from the Dockerfile in this repo. Optional TAG (default: saml_app_notification:latest)
	-h, --help          Show this help message
EOF
}

if [ ${#-} -eq 0 ] && [ ${#} -eq 0 ]; then
	# If no args provided, show help
	usage
	exit 0
fi

cmd=${1-}

case "$cmd" in
	install)
		echo "Installing runtime requirements from requirements.txt..."
		python3 -m pip install --upgrade pip
		python3 -m pip install -r requirements.txt
		;;

	dev-install)
		echo "Installing development requirements (editable install)..."
		python3 -m pip install --upgrade pip
		python3 -m pip install -e ".[dev]"
		;;
	
	test)
		echo "Running tests with pytest..."
		pytest
		;;

	docker-build)
		# optional tag as second arg
		tag=${2:-saml_app_notification:latest}
		echo "Building docker image with tag: ${tag}"
		docker build --pull -t "${tag}" .
		;;
	
	docker-run)
		set -x
		# optional tag as second arg
		tag=${2:-saml_app_notification:latest}
		echo "Running docker image with tag: ${tag}"
		docker run --rm \
			-e APP_DRY_RUN=True \
			-e APP_KEYCLOAK_SERVER=auth.cern.ch \
			-e APP_API_USERNAME="$(cat .secrets/username)" \
			-e APP_API_PASSWORD="$(cat .secrets/password)" \
			-e APP_SMTP_SERVER=test.com \
			-v $(pwd)/kustomize/base/templates/about_to_expire.jinja:/app/template.jinja \
			${tag} \
		;;

	-h|--help)
		usage
		;;

	*)
		echo "Unknown command: ${cmd}" >&2
		usage
		exit 1
		;;
esac
