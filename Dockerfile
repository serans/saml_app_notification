# Single-stage Dockerfile (not distroless)
FROM python:3.11-slim

WORKDIR /app

# No need to write .pyc files or buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build/runtime dependencies needed by some python packages and CA certs
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc \
       libssl-dev \
       libffi-dev \
       build-essential \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy pip.conf so pip can use the internal index defined in the repo
COPY pip.conf /etc/pip.conf
COPY pyproject.toml /app/

# Copy application source so the package can be built/installed by pip
COPY ./src /app/src/

RUN pip install --upgrade pip \
    && pip install --no-cache-dir /app/

# Copy the script and a default template into the image
# The application expects /app/template.jinja by default
COPY notify_app_owners.py /app/

# Create a non-root user and give ownership of /app
RUN groupadd -r app && useradd -r -g app app \
    && chown -R app:app /app

USER app

# Runtime configuration is provided via ENV variables prefixed with APP_
# Example: APP_API_USERNAME, APP_API_PASSWORD, APP_MESSAGE_TEMPLATE_PATH, etc.
ENTRYPOINT ["python", "/app/notify_app_owners.py"]
