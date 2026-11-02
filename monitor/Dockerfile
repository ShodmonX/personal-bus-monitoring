# Browser binaries/dependencies are in the official Playwright image.
# Use EXACTLY the same Playwright Python package version as the image.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app TZ=Asia/Tashkent
WORKDIR /app

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends xvfb xauth \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/debug \
    && chown -R pwuser:pwuser /app
COPY monitor/requirements.txt /tmp/monitor-requirements.txt
RUN pip install --no-cache-dir -r /tmp/monitor-requirements.txt
COPY --chown=pwuser:pwuser monitor /app/monitor
COPY --chown=pwuser:pwuser shared /app/shared
COPY --chown=pwuser:pwuser stops.json /app/stops.json
USER pwuser

# Xvfb is always available; Chromium is started only after the user presses Start.
CMD ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24", "uvicorn", "monitor.app:app", "--host", "0.0.0.0", "--port", "8099", "--workers", "1"]
