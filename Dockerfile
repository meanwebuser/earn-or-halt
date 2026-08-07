FROM python:3.13-alpine

RUN apk add --no-cache ca-certificates openssl \
    && addgroup -S app \
    && adduser -S -G app -u 10001 app \
    && mkdir -p /app /data \
    && chown -R app:app /app /data

WORKDIR /app
COPY --chown=app:app . /app

USER app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    EOH_DATA_DIR=/data \
    EOH_HOST=0.0.0.0 \
    EOH_PORT=8787

EXPOSE 8787
ENTRYPOINT ["python3", "-m", "earn_or_halt"]
CMD ["run"]
