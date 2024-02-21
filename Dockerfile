FROM python:3 as builder

RUN python3 -m venv /opt/virtualenv \
 && apt-get update \
 && apt-get install build-essential

COPY requirements.txt ./
RUN /opt/virtualenv/bin/pip3 install --no-cache-dir --upgrade -r requirements.txt

FROM python:3-slim

RUN useradd -r -m sungather

COPY --from=builder /opt/virtualenv /opt/virtualenv

WORKDIR /opt/sungather

COPY SunGather/ .

VOLUME /logs
VOLUME /config
VOLUME /registers
COPY SunGather/config-example.yaml /config/config.yaml
COPY SunGather/registers-sungrow.yaml /registers/registers-sungrow.yaml

USER sungather

CMD [ "/opt/virtualenv/bin/python", "sungather.py", "-c", "/config/config.yaml", "-r", "/registers/registers-sungrow.yaml", "-l", "/logs/" ]
