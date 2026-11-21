"""Static security checks on a skill's SKILL.md and scripts.

high   -> the skill is rejected outright (any tier)
medium -> official/verified: kept with a warning; community: shown for manual review
This is a filter, not a guarantee: it catches obvious abuse, not clever malware.
"""
import re

HIGH = {
    "pipe-to-shell": r"(curl|wget)[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z)?sh\b",
    "decode-and-run": r"base64\s+(-d|--decode)[^\n]{0,120}\|\s*(ba|z)?sh|eval\s*\(\s*(atob|base64|b64decode)",
    "destroy-home": r"rm\s+-rf\s+(/|~|\$HOME)(\s|$|/\*)",
    "read-secrets": r"(\.ssh/id_|\.aws/credentials|\.netrc|security\s+find-(generic|internet)-password|Login\.keychain)",
    "reverse-shell": r"(/dev/tcp/|nc\s+-e\s|bash\s+-i\s+>&)",
    "prompt-injection": r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions|do\s+not\s+(tell|inform)\s+the\s+user|without\s+the\s+user'?s?\s+knowledge",
    "hidden-unicode": "[​‌‍⁠‪-‮⁦-⁩]",
}
MEDIUM = {
    "raw-ip-url": r"https?://\d{1,3}(\.\d{1,3}){3}",
    "sudo": r"\bsudo\s+\w",
    "env-dump": r"\b(printenv|env)\s*\|\s*(curl|nc|wget)|os\.environ\b[^\n]{0,80}(requests\.|urlopen|http)",
    "html-comment-instructions": r"<!--[^>]{0,400}\b(you must|always|never|claude)\b",
    "obfuscated-exec": r"\bexec\s*\(\s*(compile|bytes\.fromhex|codecs\.decode)",
}
_H = {k: re.compile(v, re.I) for k, v in HIGH.items()}
_M = {k: re.compile(v, re.I) for k, v in MEDIUM.items()}


_URL_HOST = re.compile(r"https?://([^/\s'\"`|]+)", re.I)


def _own_host(match_text, trusted_hosts):
    hosts = _URL_HOST.findall(match_text)
    return bool(hosts) and all(any(h.lower() == t or h.lower().endswith("." + t) for t in trusted_hosts) for h in hosts)


def scan(files, trusted_hosts=()):
    """files: {path: text}. Returns (high_findings, medium_findings) as lists of 'rule@path'.
    trusted_hosts: the publisher's own domains; installing its own CLI from there is only a warning."""
    high, med = [], []
    for path, text in files.items():
        is_doc = path.lower().endswith((".md", ".txt"))
        for k, rx in _H.items():
            matches = [m.group(0) for m in rx.finditer(text)]
            if not matches:
                continue
            if k == "pipe-to-shell" and all(_own_host(m, trusted_hosts) for m in matches):
                med.append(f"official-installer@{path}")
            elif k == "read-secrets" and is_doc:
                med.append(f"mentions-secrets@{path}")  # prose describing a path, not code reading it
            else:
                high.append(f"{k}@{path}")
        for k, rx in _M.items():
            if rx.search(text):
                med.append(f"{k}@{path}")
    return high, med
