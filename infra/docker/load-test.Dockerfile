FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace

WORKDIR /workspace

COPY requirements-p2p.txt /tmp/requirements-p2p.txt
RUN pip install --no-cache-dir -r /tmp/requirements-p2p.txt

CMD ["python3", "--version"]
