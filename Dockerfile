# Obraz amazon-mcp (repozytorium wojtek80b2-ui/amazon-mcp) w trybie usługi HTTP.
# Budowany z klonu repozytorium jako kontekstem; .env nigdy nie trafia do obrazu (sekrety z env_file).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd -r -u 10001 mcp
USER mcp
EXPOSE 8000
CMD ["python", "-m", "amazon_mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
