# Load test baseline

Baseline script:

- `tools/loadtest/loadtest.py`

The script is intentionally lightweight and safe by default.

## What it does

For each worker and iteration:

1. `GET /healthz`
2. `POST /matches` (scripted)
3. optional `POST /matches/{id}/run?sync=true`
4. `GET /matches`

## Run examples

Low-impact baseline:

```bash
python tools/loadtest/loadtest.py --concurrency 1 --iterations 3
```

Include synchronous match execution:

```bash
python tools/loadtest/loadtest.py --concurrency 1 --iterations 2 --run-matches
```

Custom backend URL:

```bash
python tools/loadtest/loadtest.py --base-url http://127.0.0.1:8000
```

## Environment variables

- `HOWLHOUSE_LOAD_BASE_URL`
- `HOWLHOUSE_LOAD_CONCURRENCY`
- `HOWLHOUSE_LOAD_ITERATIONS`
- `HOWLHOUSE_LOAD_BASE_SEED`
- `HOWLHOUSE_LOAD_TIMEOUT_S`
- `HOWLHOUSE_LOAD_RUN_MATCHES` (`true`/`false`)
