FROM python:3.12-alpine

WORKDIR /app
COPY app.py .

RUN adduser -D -H alert
USER alert

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget --spider -q http://127.0.0.1:8080/healthz || exit 1

CMD ["python", "app.py"]
