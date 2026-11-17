FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd -m edge && mkdir -p /models /certs && chown edge /models
COPY app ./app
COPY tests ./tests
USER edge
