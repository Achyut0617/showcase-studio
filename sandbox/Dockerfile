# Base sandbox image: untrusted projects are built and run only inside this.
# Run it through showcase.sandbox.docker_run_args, which adds network, CPU,
# memory and privilege limits.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 runner

WORKDIR /work
USER runner
CMD ["bash"]
