# Worker image — runs the content pipeline (extraction + document building).
# Build context = repo root (so we can copy DsideOS/ + the pipeline it imports).
#   docker build -f DsideOS/worker/Dockerfile -t dsideos-worker .
FROM python:3.12-slim

# System deps:
#  - libreoffice: headless .docx -> .pdf conversion (answer key)
#  - fonts: Kruti Dev 010 + a Unicode Devanagari font for correct PDF rendering
#  - fontconfig: so LibreOffice picks up the installed fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fontconfig \
        fonts-deva \
        fonts-lohit-deva \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY DsideOS/worker/requirements.txt /app/worker-requirements.txt
RUN pip install --no-cache-dir -r /app/worker-requirements.txt

# Install bundled fonts (Kruti Dev 010 + Nirmala UI live in DsideOS/fonts/).
# fonts/ is gitignored (licensed) — see DsideOS/fonts/.abstract.md for how to
# provision them on the build host before building the image.
COPY DsideOS/fonts/ /usr/share/fonts/truetype/dsideos/
RUN fc-cache -f -v || true

# App code: the backend + the pipeline it imports in place.
COPY DsideOS/ /app/DsideOS/
COPY clients/target-academy/pipeline/ /app/clients/target-academy/pipeline/

# NOTE: the builders need the client's branded assets at runtime —
#   clients/target-academy/resources/ (front-page.docx, etc.)
#   clients/target-academy/templates/ (logo, watermark)
# These are client IP (gitignored, NOT in the repo or image). They are mounted
# as a read-only volume at runtime — provisioned on the server, see DEPLOY.md.
# The directories are created here so the mount targets exist.
RUN mkdir -p /app/clients/target-academy/resources \
             /app/clients/target-academy/templates

ENV PYTHONPATH=/app/DsideOS:/app
WORKDIR /app/DsideOS

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info", "--concurrency=3"]
