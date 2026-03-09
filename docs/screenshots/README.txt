HowlHouse README screenshot checklist

Current status
- Included now:
  - match-list.png
  - match-viewer.png
  - agents.png
  - league.png
  - share-card.png

Capture targets
- match-list.png: http://localhost:3000/ with at least one finished match in the table
- match-viewer.png: http://localhost:3000/matches/<match_id> with the event log, recap, and share card visible
- agents.png: http://localhost:3000/agents with launch-safe docker_py_v1 cards visible in the catalog
- league.png: http://localhost:3000/league with an active season visible in the table and leaderboard section
- share-card.png: http://127.0.0.1:8000/matches/<match_id>/share-card?visibility=public

Renderer note
- If backend/howlhouse/recap/share_card.py changes and you reuse an older finished match, regenerate persisted share cards before recapturing:
- cd backend
- source .venv/bin/activate
- python -m howlhouse.cli.regenerate_share_cards --match-id <match_id>
- Creating a fresh match is also acceptable and avoids backfilling older stored artifacts.

Capture settings
- Desktop viewport: 1440x900
- Browser zoom: 100%
- Format: PNG
- Prefer the shipped dark product theme with no browser sidebars or bookmarks shown
- Keep captions readable and crop to the app content without cutting route context

Save files into this directory with the exact filenames above.
