FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY testbeds/multihost/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin capme \
    && rm -f /tmp/requirements.txt

WORKDIR /app
COPY src /app/src
COPY configs/fso-multihost.json /app/configs/fso-multihost.json

USER 10001:10001
ENTRYPOINT ["python", "-m", "capme.fso.multihost"]
