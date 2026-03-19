FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=120 --retries=5 -r requirements.txt

# Ephemeris data will be downloaded on first run and cached in /app/data/
# This avoids build failures when NASA JPL servers are slow/unreachable

# Copy application
COPY app/ app/

# Create data directory
RUN mkdir -p data

# Environment
ENV ASTRODASH_DB=data/astrodash.db
ENV PYTHONUNBUFFERED=1

EXPOSE 9090

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:9090/api/settings || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9090"]
