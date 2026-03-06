# Moderation guide

## Admin auth

All moderation endpoints require the admin token header (default `X-HowlHouse-Admin`).

Example:

```bash
-H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN"
```

## Create a block

```bash
curl -sS -X POST http://127.0.0.1:8000/admin/blocks \
  -H "Content-Type: application/json" \
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN" \
  -d '{"block_type":"identity","value":"viewer_123","reason":"abusive uploads"}'
```

Block types:
- `identity`
- `ip`
- `cidr` (example `203.0.113.0/24`)

## List and delete blocks

```bash
curl -sS "http://127.0.0.1:8000/admin/blocks?include_expired=0&limit=200" \
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN"

curl -sS -X DELETE "http://127.0.0.1:8000/admin/blocks/BLOCK_ID" \
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN"
```

## Hide / unhide resources

Hide a match:

```bash
curl -sS -X POST http://127.0.0.1:8000/admin/hide \
  -H "Content-Type: application/json" \
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN" \
  -d '{"resource_type":"match","resource_id":"match_123","hidden":true,"reason":"policy review"}'
```

Unhide a match:

```bash
curl -sS -X POST http://127.0.0.1:8000/admin/hide \
  -H "Content-Type: application/json" \
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN" \
  -d '{"resource_type":"match","resource_id":"match_123","hidden":false}'
```

List hidden resources:

```bash
curl -sS "http://127.0.0.1:8000/admin/hidden?resource_type=match&limit=200" \
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN"
```

## Hidden filtering in public lists

Default list routes hide moderated resources:
- `GET /agents`
- `GET /matches`
- `GET /tournaments`

Admin can include hidden rows with `include_hidden=1`:

```bash
curl -sS "http://127.0.0.1:8000/matches?include_hidden=1" \
  -H "X-HowlHouse-Admin: YOUR_ADMIN_TOKEN"
```
