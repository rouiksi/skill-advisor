#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook: silently adds a hint when a skill strongly matches.
Uses the current prompt plus the last user messages; skips skills already installed on disk.
Never blocks, prints nothing when there is no strong match.

settings.json:
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 3,
  "command": "python3 \"$HOME/.claude/skills/skill-advisor/hooks/suggest_hook.py\""}]}]}}
"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "scripts"), os.path.join(HERE, "..", "skill", "scripts")]


def recent_user_text(path, n=2, max_chars=600):
    """Last n user messages from the transcript (JSONL), newest last. Reads only the file tail."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 200_000))
        lines = f.read().decode("utf-8", "ignore").splitlines()
    msgs = []
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("type") != "user":
            continue
        c = e.get("message", {}).get("content")
        if isinstance(c, list):
            c = " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
        if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):
            msgs.append(c.strip()[:max_chars])
        if len(msgs) >= n:
            break
    return " ".join(reversed(msgs))


def installed_skills(cwd):
    roots = [os.path.expanduser("~/.claude/skills"), os.path.join(cwd or ".", ".claude", "skills")]
    names = set()
    for r in roots:
        names |= {os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(r, "*", "SKILL.md"))}
    for p in glob.glob(os.path.expanduser("~/.claude/plugins/**/skills/*/SKILL.md"), recursive=True):
        names.add(os.path.basename(os.path.dirname(p)))
    return names


try:
    from suggest import suggest
    data = json.load(sys.stdin)
    prompt = data.get("prompt", "")
    if len(prompt) >= 20 and not prompt.lstrip().startswith("/"):  # skip short replies and slash commands
        # current prompt counts double; earlier messages only add context
        ctx = f"{prompt} {prompt} {recent_user_text(data.get('transcript_path'))}"
        res = suggest(ctx, min_score=0.45, installed=installed_skills(data.get("cwd")), limit=2,
                      platform="claude", focus=prompt)
        if res:
            names = "; ".join(f"{s['name']} [{s.get('tier', '')}] — {s.get('value') or s['description'][:120]} ({s['url']})"
                              for _, s in res)
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"[skill-advisor] Skill pertinenti da fonti controllate: {names}. "
                                     "Suggeriscile in una riga a fine risposta SOLO se davvero utili qui "
                                     "e non gia' disponibili tra le tue skill (anche con prefisso, es. anthropic-skills:)."}}))
except Exception:
    pass  # a hint is optional: never break the user's prompt
sys.exit(0)
