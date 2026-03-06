FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin howlhouse \
    && mkdir -p /app/data /app/replays \
    && chown -R howlhouse:howlhouse /app

USER howlhouse

EXPOSE 8000

CMD ["uvicorn", "howlhouse.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
