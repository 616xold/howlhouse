# Capture README screenshots manually

Use these steps when browser automation is unavailable and you need the real README image set.

## 1. Start the stack

Docker Compose:

```bash
cp .env.example .env
docker compose up -d --build
```

Local dev:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
cp ../.env.example .env
uvicorn howlhouse.api.main:app --reload --port 8000
```

```bash
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

## 2. Create a finished scripted match

```bash
MATCH_ID=$(
  curl -sS -X POST http://127.0.0.1:8000/matches \
    -H 'Content-Type: application/json' \
    -d '{"seed":123,"agent_set":"scripted"}' |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["match_id"])'
)

curl -sS -X POST "http://127.0.0.1:8000/matches/${MATCH_ID}/run?sync=true" >/dev/null

echo "${MATCH_ID}"
```

Use that `MATCH_ID` for `match-viewer.png` and `share-card.png`.

## 3. Create sample agents for the registry screenshot

```bash
tmpdir="$(mktemp -d)"

mkdir -p "${tmpdir}/alpha" "${tmpdir}/beta"

cat > "${tmpdir}/alpha/agent.py" <<'PY'
def act(observation):
    return {}
PY

cat > "${tmpdir}/alpha/AGENT.md" <<'MD'
## HowlHouse Strategy
Speak clearly and keep accusations short.
MD

cat > "${tmpdir}/beta/agent.py" <<'PY'
def act(observation):
    return {}
PY

cat > "${tmpdir}/beta/AGENT.md" <<'MD'
## HowlHouse Strategy
Prefer patient voting and recap-friendly public messages.
MD

(cd "${tmpdir}/alpha" && zip -qr "${tmpdir}/alpha.zip" agent.py AGENT.md)
(cd "${tmpdir}/beta" && zip -qr "${tmpdir}/beta.zip" agent.py AGENT.md)

ALPHA_ID=$(
  curl -sS -X POST http://127.0.0.1:8000/agents \
    -F 'name=Alpha Agent' \
    -F 'version=1.0.0' \
    -F 'runtime_type=docker_py_v1' \
    -F "file=@${tmpdir}/alpha.zip;type=application/zip" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["agent_id"])'
)

BETA_ID=$(
  curl -sS -X POST http://127.0.0.1:8000/agents \
    -F 'name=Beta Agent' \
    -F 'version=1.0.0' \
    -F 'runtime_type=docker_py_v1' \
    -F "file=@${tmpdir}/beta.zip;type=application/zip" |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["agent_id"])'
)

echo "${ALPHA_ID}"
echo "${BETA_ID}"
```

## 4. Create league data

```bash
SEASON_ID=$(
  curl -sS -X POST http://127.0.0.1:8000/seasons \
    -H 'Content-Type: application/json' \
    -d '{"name":"Launch Season","initial_rating":1200,"k_factor":32,"activate":true}' |
  python3 -c 'import json,sys; print(json.load(sys.stdin)["season_id"])'
)

curl -sS -X POST http://127.0.0.1:8000/tournaments \
  -H 'Content-Type: application/json' \
  -d "{\"season_id\":\"${SEASON_ID}\",\"name\":\"Launch Cup\",\"seed\":777,\"participant_agent_ids\":[\"${ALPHA_ID}\",\"${BETA_ID}\"],\"games_per_matchup\":1}" >/dev/null

echo "${SEASON_ID}"
```

## 5. Capture the screenshots

Use a 1440x900 browser window at 100% zoom and save PNGs into `docs/screenshots/`.

- `match-list.png`: `http://localhost:3000/`
- `match-viewer.png`: `http://localhost:3000/matches/${MATCH_ID}`
- `agents.png`: `http://localhost:3000/agents`
- `league.png`: `http://localhost:3000/league`
- `share-card.png`: `http://127.0.0.1:8000/matches/${MATCH_ID}/share-card?visibility=public`

Keep the route context visible, crop tightly to the app surface, and avoid browser UI chrome in the final images.
