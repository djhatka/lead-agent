# The recipe Railway follows to build and run the live server.
# (A "Docker image" = a sealed box with Python + our code + its libraries,
#  so the server runs exactly the same everywhere.)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    MEDIA_DIR=/data/media \
    OUTBOX_DIR=/data/outbox \
    BACKUP_DIR=/data/backups

WORKDIR /app

# Libraries first (this step is cached, so code-only changes rebuild in seconds)
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# /data is the persistent disk (a Railway volume): photos, emails, nightly backups
RUN mkdir -p /data

EXPOSE 8000

# ONE process on purpose: the scheduler clock and the live feed live inside it.
# Migrations run automatically at start-up (app/database.py → migrate()).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
