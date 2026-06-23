#!/usr/bin/env bash
# Mirror this project's skills, memory, and key docs to the SIoT MCP gateway
# knowledge store (navbot-knowledge upstream server on 10.10.8.113).
#
# Source of truth (local) -> /home/mcp/knowledge/claude-navbot/ (VM):
#   .claude/commands/navbot/*.md  -> skills/<name>/SKILL.md
#   <project memory dir>/*.md      -> memory/
#   docs/                          -> docs/
#   CLAUDE.md                      -> CLAUDE.md
#
# Safe to run repeatedly. Used both for the initial deploy and by the
# Claude Code Stop hook. Never fails the caller: exits 0 even if the VM is
# unreachable (logs a warning to stderr).

set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENC="$(printf '%s' "$REPO" | sed 's:/:-:g')"
MEM_DIR="$HOME/.claude/projects/$ENC/memory"
VM="${NAVBOT_MCP_VM:-mcp-vm}"      # ssh alias for the gateway VM (root@10.10.8.113)
TARGET="/home/mcp/knowledge/claude-navbot"

warn() { printf 'sync_knowledge_to_mcp: %s\n' "$*" >&2; }

command -v rsync >/dev/null 2>&1 || { warn "rsync not found; skipping"; exit 0; }
ssh -o ConnectTimeout=6 -o BatchMode=yes "$VM" 'true' 2>/dev/null \
  || { warn "VM $VM unreachable; skipping sync"; exit 0; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# skills: each slash command -> skills/<name>/SKILL.md
if compgen -G "$REPO/.claude/commands/navbot/*.md" >/dev/null; then
  for f in "$REPO"/.claude/commands/navbot/*.md; do
    name="$(basename "$f" .md)"
    mkdir -p "$STAGE/skills/$name"
    cp "$f" "$STAGE/skills/$name/SKILL.md"
  done
fi

# memory
if compgen -G "$MEM_DIR/*.md" >/dev/null; then
  mkdir -p "$STAGE/memory"
  cp "$MEM_DIR"/*.md "$STAGE/memory/"
fi

# docs (whole tree) + project CLAUDE.md
[ -d "$REPO/docs" ] && { mkdir -p "$STAGE/docs"; cp -R "$REPO/docs/." "$STAGE/docs/"; }
[ -f "$REPO/CLAUDE.md" ] && cp "$REPO/CLAUDE.md" "$STAGE/CLAUDE.md"

cat > "$STAGE/README.md" <<'MD'
# claude-navbot knowledge

Mirror of the claude-navbot project's skills, memory, and docs, served to the
SIoT MCP gateway by the `navbot-knowledge` server (prefix `nav`). Refreshed by
`scripts/sync_knowledge_to_mcp.sh` in the repo (run by a Claude Code Stop hook).

- `CLAUDE.md` — project context / instructions
- `skills/<name>/SKILL.md` — the `/navbot:*` bench-test commands
- `memory/` — project memory facts (Pi access, hardware reconfig, index)
- `docs/` — project documentation (status, validation records, hardware, ops)
MD

ssh "$VM" "mkdir -p $TARGET" 2>/dev/null
if rsync -az --delete -e ssh "$STAGE/" "$VM:$TARGET/" 2>/dev/null; then
  ssh "$VM" "chown -R mcp:mcp $TARGET" 2>/dev/null || true
  printf 'sync_knowledge_to_mcp: pushed skills+memory+docs to %s:%s\n' "$VM" "$TARGET"
else
  warn "rsync to $VM failed; skipping"
fi
exit 0
