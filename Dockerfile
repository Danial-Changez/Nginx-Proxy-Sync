FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY nginx_proxy_sync ./nginx_proxy_sync

RUN pip install --no-cache-dir .

CMD ["python", "-u", "-m", "nginx_proxy_sync"]
