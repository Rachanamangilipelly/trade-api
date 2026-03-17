# ─────────────────────────────────────────────────────────────
#  India Trade Opportunities API — Dockerfile
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# Metadata
LABEL maintainer="trade-api"
LABEL description="India Trade Opportunities API"

# Security: run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/
COPY run.py .

# Ownership
RUN chown -R appuser:appgroup /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Start
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
