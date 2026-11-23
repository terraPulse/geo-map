FROM python:3.12-slim-bookworm

WORKDIR /opt/layer-manager
COPY management/worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY management/src/layer_manager /opt/layer-manager/layer_manager
COPY management/fixtures/synthetic_layers.json /opt/layer-manager/layer_manager/synthetic_fixtures.json
ENV PYTHONPATH=/opt/layer-manager
ENV BUILD_ALLOW_S3=0
ENTRYPOINT ["python", "-m", "layer_manager.worker_main"]
