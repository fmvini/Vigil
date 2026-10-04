# Build the ordinary API image first; this adds worker-only OS controls.
ARG VIGIL_BASE_IMAGE=vigil-api:latest
FROM ${VIGIL_BASE_IMAGE}
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends iptables iproute2 util-linux \
    && rm -rf /var/lib/apt/lists/*
COPY egress.py /opt/vigil/egress.py
ENV PYTHONDONTWRITEBYTECODE=1 VIGIL_WORKER_NAMESPACE=dedicated
ENTRYPOINT ["python", "/opt/vigil/egress.py"]
CMD ["taskiq", "worker", "app.monitoring.tasks:broker", "--workers", "1", "--max-async-tasks", "50", "--max-prefetch", "50", "--ack-type", "manual"]
