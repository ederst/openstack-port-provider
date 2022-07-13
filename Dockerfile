FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=${PYTHONPATH}:${PWD}

RUN apt update && \
    apt install -y gcc && \
    pip3 install poetry && \
    mkdir openstack_port_provider

COPY openstack_port_provider/ ./openstack_port_provider
COPY poetry.lock pyproject.toml ./

RUN poetry config virtualenvs.create false && \
    poetry install --no-dev

ENTRYPOINT [ "os_port_provider" ]
CMD [ "--help" ]
