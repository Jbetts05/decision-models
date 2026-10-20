FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m venv /opt/venv \
    && groupadd --gid 10001 graphapp \
    && useradd --uid 10001 --gid graphapp --create-home graphapp

WORKDIR /app
COPY requirements.txt ./
COPY .venv/wheelhouse /tmp/wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt \
    && rm -rf /tmp/wheels
COPY --chown=graphapp:graphapp traversal ./traversal
COPY --chown=graphapp:graphapp web ./web
COPY --chown=graphapp:graphapp data/traversal ./data/traversal
RUN mkdir -p /app/results/local && chown -R graphapp:graphapp /app/results

USER graphapp
EXPOSE 8080
CMD ["python", "-m", "traversal", "serve"]
