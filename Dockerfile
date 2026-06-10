FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e .

VOLUME /data
ENV TARS_DATA_DIR=/data

EXPOSE 9119

ENTRYPOINT ["tars"]
CMD ["start", "--api-host", "0.0.0.0"]
