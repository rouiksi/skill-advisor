#!/usr/bin/env python3
"""Writes the body of the 'Skill da approvare' issue from index/candidates.json (stdout).
Prints nothing when there are no candidates."""
import json, sys

c = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "index/candidates.json"))
if not c:
    sys.exit(0)
print("Skill della community che hanno superato i controlli automatici (sicurezza, licenza, stelle, aggiornamento).\n")
print("**Per approvarne una**: aggiungi il suo id in `approved.json` (oppure chiedilo a Claude). "
      "Al giro successivo entra nel catalogo.\n")
for s in c:
    warn = f" ⚠️ {', '.join(s['warnings'])}" if s.get("warnings") else ""
    print(f"- [ ] `{s['id']}` — {s['description'][:160]} ([sorgente]({s['url']})){warn}")
