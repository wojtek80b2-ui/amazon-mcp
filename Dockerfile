# Obraz amazon-mcp (repozytorium wojtek80b2-ui/amazon-mcp) w trybie usługi HTTP.
# Budowany z klonu repozytorium jako kontekstem; .env nigdy nie trafia do obrazu (sekrety z env_file).
# Bez MCP_TOKENS serwer nie wystartuje.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd -r -u 10001 mcp
USER mcp
ENV MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["python", "-m", "amazon_mcp"]
