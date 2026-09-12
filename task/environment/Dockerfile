# The image the agent works in and the image the grader runs in. One stage: the depot
# is line-delimited JSON and the work needs only the standard library, because every
# quantity the policy turns on is a string, an integer or a tuple of integers.
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The grader dependencies, pinned and baked in at build time so nothing is installed
# once the image is running.
RUN pip install --no-cache-dir \
        pytest==8.4.1 \
        pytest-json-ctrf==0.3.5

RUN mkdir -p /app
WORKDIR /app

COPY data/REISSUE.md /app/REISSUE.md
COPY data/depot /app/depot
