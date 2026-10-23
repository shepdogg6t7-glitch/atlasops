FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TORCH_HOME=/root/.cache/torch \
    SENTENCE_TRANSFORMERS_HOME=/root/.cache/sentence_transformers

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .

# Install CPU-only torch first, without deps, so dependency resolution stays on PyPI.
# sentence-transformers requires torch>=2.2; installing it here (CPU build) means
# the subsequent `pip install -r requirements.txt` sees torch as already satisfied
# and won't pull the ~550 MB CUDA wheel from PyPI.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu --no-deps

RUN pip install -r requirements.txt

COPY docker-entrypoint.sh /docker-entrypoint.sh
COPY apps/api ./apps/api

# Pre-download the embedding model at build time so the worker doesn't need
# network access on first run.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
