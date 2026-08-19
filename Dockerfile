FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY waf/ ./waf/
COPY policies/ ./policies/

RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn waf.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
