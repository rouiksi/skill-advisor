#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: silently adds a hint when a skill strongly matches.
Never blocks, never prints anything when there is no strong match.

settings.json:
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 3,
  "command": "python3 ~/.claude/skills/skill-advisor/hooks/suggest_hook.py"}]}]}}
"""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skill", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

try:
    from suggest import suggest
    prompt = json.load(sys.stdin).get("prompt", "")
    if len(prompt) >= 20:  # skip "ok", "si", short replies
        res = suggest(prompt, min_score=0.6, limit=2)
        if res:
            names = ", ".join(f"{s['name']} ({s['url']})" for _, s in res)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"[skill-advisor] Skill ufficiali pertinenti: {names}. "
                                     "Se davvero utili e non gia' in uso, suggeriscile in una riga a fine risposta."}}))
except Exception:
    pass  # a hint is optional: never break the user's prompt
sys.exit(0)
