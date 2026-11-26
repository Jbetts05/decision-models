FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY --chown=app:app compliance ./compliance
COPY --chown=app:app web ./web
COPY --chown=app:app scenarios ./scenarios
USER app
EXPOSE 8080
CMD ["python", "-m", "compliance", "serve", "--host", "0.0.0.0", "--port", "8080"]
