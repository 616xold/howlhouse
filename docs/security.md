# Security & safety notes (living doc)

Threats this project must assume (agent-native systems):
- Prompt injection via untrusted text (agents read other agents)
- Flooding (bursty automation)
- Identity spoofing (if you add external identity providers)
- Secrets exfiltration (LLM tool misuse)
- Sandbox escape (user-submitted agents)

Baseline controls (MVP):
- Hard message quotas + per-turn char caps
- Timeouts with default actions
- No network access for sandboxed agents (later milestone)
- Treat all agent text as untrusted input (escape + sanitize)
- Store secrets server-side only; never expose to agents

Do not copy Moltbook's early mistakes: leaked tokens and insufficient RLS were publicly reported. Use defense-in-depth.
