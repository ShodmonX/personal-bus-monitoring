FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app TZ=Asia/Tashkent
WORKDIR /app
COPY bot/requirements.txt /tmp/bot-requirements.txt
RUN pip install --no-cache-dir -r /tmp/bot-requirements.txt \
    && useradd -m -u 10001 -s /usr/sbin/nologin appuser
COPY --chown=appuser:appuser bot /app/bot
COPY --chown=appuser:appuser shared /app/shared
COPY --chown=appuser:appuser stops.json /app/stops.json
USER appuser
CMD ["python", "-m", "bot.app"]
