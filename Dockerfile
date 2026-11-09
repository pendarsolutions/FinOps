# API + worker image (same code, different command)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/packages:/app/apps/api:/app/apps/worker
WORKDIR /app
RUN useradd --create-home --uid 10001 finops
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY packages ./packages
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY migrations ./migrations
COPY alembic.ini ./
COPY data ./data
COPY docker/entrypoint.sh /entrypoint.sh
# finops-agent upgrade takes the new version's compose file, backup script and command from here
COPY deploy ./deploy
# strip CRLF in case the repo was checked out on Windows without .gitattributes
RUN sed -i 's/\r$//' /entrypoint.sh /app/deploy/*.sh /app/deploy/finops-agent && chmod +x /entrypoint.sh && mkdir -p /app/var/uploads /app/var/catalog && chown -R finops /app/var
USER finops
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["api"]
