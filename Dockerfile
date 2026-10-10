FROM python:3.12-slim

LABEL org.opencontainers.image.source=https://github.com/zbuh/secret_friend \
      org.opencontainers.image.description="Amigo Secreto: sorteio de Natal"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    db_path=/data/secret_friend.db \
    # Behind cloudflared: trust X-Forwarded-For/Proto so rate limits see the real IP and cookies are Secure.
    # Narrow this to the cloudflared LXC IP in the stack if you want.
    FORWARDED_ALLOW_IPS="*"

WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --system --uid 10001 app && mkdir /data && chown app /data
COPY app ./app

USER app
VOLUME /data
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
