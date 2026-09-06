FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 arrow
WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir .

RUN mkdir -p /var/lib/arrow-callback && chown -R arrow:arrow /var/lib/arrow-callback
USER arrow

CMD ["uvicorn", "brokers.arrow.callback_app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
