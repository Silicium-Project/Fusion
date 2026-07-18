FROM python:3.12-slim

WORKDIR /opt/silicium/Network

COPY Network/requirements-p2p.txt /tmp/requirements-p2p.txt
RUN pip install --no-cache-dir -r /tmp/requirements-p2p.txt

COPY Network/ /opt/silicium/Network/

ENV PYTHONUNBUFFERED=1
