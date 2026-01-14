FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py agent_monitor.py knowledge_base.py web_ui.py entrypoint.sh agent_entrypoint.sh ./
COPY templates ./templates

RUN chmod +x entrypoint.sh agent_entrypoint.sh

CMD ["./entrypoint.sh"]
