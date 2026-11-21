#!/usr/bin/env python3
"""Suggests up to 3 skills for a work context. Matching runs locally: the chat never leaves the device.

Usage: python3 suggest.py "testo del contesto" [--min 0.25] [--json] [--dismiss NOME]
Env:   SKILL_ADVISOR_INDEX_URL  (URL raw di index.json, oppure percorso locale)
"""
import argparse, json, os, re, sys, time, urllib.request

INDEX_URL = os.environ.get(
    "SKILL_ADVISOR_INDEX_URL",
    "https://raw.githubusercontent.com/rouiksi/skill-advisor/main/index/index.json",
)
CACHE_DIR = os.path.expanduser("~/.cache/skill-advisor")
CACHE = os.path.join(CACHE_DIR, "index.json")
DISMISSED = os.path.join(CACHE_DIR, "dismissed.json")
TTL = 6 * 3600

STOP = set("""a an and are as at be by for from in into is it of on or the to use with this that you your can
il lo la i gli le un una di da con su per tra fra e o che non se come del della dei delle al alla mi ci
voglio vorrei fare fai puoi devo questo questa""".split())
# small IT->EN bridge so Italian requests match English skill descriptions
IT_EN = {"documento": "document", "documenti": "document", "foglio": "spreadsheet", "fogli": "spreadsheet",
         "excel": "xlsx", "word": "docx", "presentazione": "presentation", "slide": "slides",
         "grafico": "chart", "grafica": "design", "immagine": "image", "immagini": "image",
         "sito": "website", "pagina": "page", "codice": "code", "testare": "test", "test": "testing",
         "server": "server", "pdf": "pdf", "modulo": "form", "moduli": "forms", "tabella": "table",
         "colori": "colors", "marchio": "brand", "logo": "brand", "animazione": "animation",
         "gif": "gif", "arte": "art", "lettera": "letter", "comunicazione": "communications"}


def tokens(text):
    out = []
    for w in re.findall(r"[a-zà-ù0-9]{2,}", text.lower()):
        if w in STOP:
            continue
        out.append(stem(IT_EN.get(w, w)))
    return set(out)


def stem(w):
    return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w


def load_index():
    if os.path.exists(INDEX_URL):
        return json.load(open(INDEX_URL))
    fresh = os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < TTL
    if not fresh:
        try:
            req = urllib.request.Request(INDEX_URL, headers={"User-Agent": "skill-advisor"})
            data = urllib.request.urlopen(req, timeout=3).read()
            json.loads(data)  # validate before caching
            os.makedirs(CACHE_DIR, exist_ok=True)
            open(CACHE, "wb").write(data)
        except Exception:
            pass  # offline or bad response: fall back to stale cache
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {"skills": []}


def load_dismissed():
    try:
        return set(json.load(open(DISMISSED)))
    except Exception:
        return set()


def score(ctx, s):
    name = tokens(s["name"].replace("-", " "))
    kw, desc = {stem(k) for k in s.get("keywords", [])}, tokens(s["description"])
    raw = 3 * len(ctx & name) + 2 * len(ctx & kw) + len(ctx & desc)
    return raw / (3 + len(ctx) ** 0.5)  # normalised: long contexts don't win by size alone


def suggest(text, min_score=0.25, installed=(), limit=3):
    ctx = tokens(text)
    skip = load_dismissed() | set(installed)
    ranked = sorted(((score(ctx, s), s) for s in load_index().get("skills", [])
                     if s["name"] not in skip), key=lambda x: -x[0])
    return [(round(sc, 2), s) for sc, s in ranked if sc >= min_score][:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("context", nargs="?", default="")
    ap.add_argument("--min", type=float, default=0.25)
    ap.add_argument("--installed", default="", help="nomi separati da virgola")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dismiss")
    a = ap.parse_args()

    if a.dismiss:
        d = load_dismissed() | {a.dismiss}
        os.makedirs(CACHE_DIR, exist_ok=True)
        json.dump(sorted(d), open(DISMISSED, "w"))
        print(f"'{a.dismiss}' non verra' piu' suggerita.")
        return

    res = suggest(a.context or sys.stdin.read(), a.min, [x for x in a.installed.split(",") if x])
    if a.json:
        print(json.dumps([{"score": sc, **s} for sc, s in res], ensure_ascii=False))
    else:
        for sc, s in res:
            print(f"- {s['name']} ({sc}): {s['description'][:140]} -> {s['url']}")


if __name__ == "__main__":
    main()
