# Red-DiscordBot mit dem c2bridge-Cog – läuft als Dienst im Compose-Stack der C2-Seite.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install Red-DiscordBot

RUN useradd -m red && mkdir /data && chown red /data
COPY c2bridge /opt/c2bridge
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER red
VOLUME /data
ENTRYPOINT ["/entrypoint.sh"]
