FROM python:3.10-slim

# Prevent python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1

# Ensure stdout/stderr unbuffered so Docker logs are visible immediately
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies:
#   build-essential — C extension compilation
#   docker.io       — docker CLI for ODM exec
#   gdal-bin        — gdal2tiles.py, gdal_translate (tile generation)
#   libgdal-dev     — GDAL headers for python-gdal binding
#   python3-gdal    — Python GDAL bindings (for tile_service)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    docker.io \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install python-multipart

# Copy source code
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]