FROM python:3.11.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY constraints.txt pyproject.toml README.md ./
COPY howlhouse ./howlhouse
RUN pip install --upgrade pip setuptools wheel \
    && pip wheel --no-cache-dir --wheel-dir /wheels -c constraints.txt .

FROM python:3.11.11-slim-bookworm AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY constraints.txt ./
COPY --from=builder /wheels /wheels
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -c constraints.txt /wheels/*

COPY howlhouse ./howlhouse

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin howlhouse \
    && mkdir -p /app/data /app/replays \
    && chown -R howlhouse:howlhouse /app

USER howlhouse

EXPOSE 8000

CMD ["uvicorn", "howlhouse.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
