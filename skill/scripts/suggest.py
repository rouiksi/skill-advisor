#!/usr/bin/env python3
"""Suggests up to 3 skills for a work context. BM25 ranking, runs locally: the chat never leaves the device.

Usage: python3 suggest.py "testo del contesto" [--min 0.35] [--json] [--installed a,b] [--dismiss NOME]
Env:   SKILL_ADVISOR_INDEX_URL  (URL raw di index.json, oppure percorso locale)
"""
import argparse, json, math, os, re, sys, time, urllib.request

INDEX_URL = os.environ.get(
    "SKILL_ADVISOR_INDEX_URL",
    "https://raw.githubusercontent.com/rouiksi/skill-advisor/main/index/index.json",
)
CACHE_DIR = os.path.expanduser("~/.cache/skill-advisor")
CACHE = os.path.join(CACHE_DIR, "index.json")
DISMISSED = os.path.join(CACHE_DIR, "dismissed.json")
TTL = 6 * 3600

STOP = set("""a an and are as at be by for from in into is it of on or the to use with this that you your can my me
il lo la i gli le un una di da con su per tra fra e o che non se come del della dei delle al alla allo ai agli
mi ci ti si ne voglio vorrei fare fai fammi puoi devo deve questo questa questi queste mio mia miei mie
nel nella nei sul sulla dal dalla piu più anche solo ora poi""".split())
# IT->EN bridge so Italian requests also hit English descriptions
IT_EN = {"documento": "document", "foglio": "spreadsheet", "fogli": "spreadsheet", "presentazione": "presentation",
         "presentazioni": "presentation", "diapositive": "slide", "grafico": "chart", "grafici": "chart",
         "immagine": "image", "immagini": "image", "sito": "website", "pagina": "page", "codice": "code",
         "testare": "test", "modulo": "form", "moduli": "form", "tabella": "table", "colori": "color",
         "marchio": "brand", "animazione": "animation", "animata": "animation", "arte": "art",
         "unisci": "merge", "unire": "merge", "dividi": "split", "estrai": "extract", "crea": "create",
         "creare": "create", "scrivi": "write", "scrivere": "write", "modifica": "edit", "modificare": "edit"}
K1, B = 1.4, 0.6
FIELD_WEIGHT = {"name": 3, "examples": 2, "keywords": 1, "description": 1, "value": 1}


def stem(w):
    for suf in ("zioni", "zione", "mente"):
        if w.endswith(suf) and len(w) > len(suf) + 3:
            return w[: -len(suf)]
    return w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w


def tokens(text):
    out = []
    for w in re.findall(r"[a-zà-ù0-9]{2,}", text.lower()):
        if w not in STOP:
            out.append(stem(IT_EN.get(w, w)))
    return out


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
            pass  # offline: fall back to stale cache
    return json.load(open(CACHE)) if os.path.exists(CACHE) else {"skills": []}


def load_dismissed():
    try:
        return set(json.load(open(DISMISSED)))
    except Exception:
        return set()


def doc_tokens(s):
    toks = []
    fields = {"name": s["name"].replace("-", " "), "examples": " ".join(s.get("examples", [])),
              "keywords": " ".join(s.get("keywords", [])), "description": s["description"],
              "value": s.get("value", "")}
    for f, text in fields.items():
        toks += tokens(text) * FIELD_WEIGHT[f]
    return toks


def rank(query, skills):
    q = set(tokens(query))
    if not q or not skills:
        return []
    docs = [doc_tokens(s) for s in skills]
    N, avg = len(docs), sum(map(len, docs)) / len(docs)
    df = {t: sum(1 for d in docs if t in d) for t in q}
    idf = {t: math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5)) for t in q}
    # normalise by the best achievable score so thresholds don't depend on query length
    norm = sum(idf[t] for t in q if df[t]) * (K1 + 1) or 1
    out = []
    for s, d in zip(skills, docs):
        tf = {}
        for t in d:
            if t in q:
                tf[t] = tf.get(t, 0) + 1
        sc = sum(idf[t] * tf[t] * (K1 + 1) / (tf[t] + K1 * (1 - B + B * len(d) / avg)) for t in tf)
        sc /= norm
        if any(set(tokens(n)) <= q for n in s.get("not_for", []) if tokens(n)):
            sc *= 0.3  # explicit "not for this" from enrichment
        out.append((sc, s))
    return sorted(out, key=lambda x: -x[0])


def suggest(text, min_score=0.35, installed=(), limit=3):
    skip = load_dismissed() | set(installed)
    skills = [s for s in load_index().get("skills", []) if s["name"] not in skip]
    ranked = rank(text, skills)
    if not ranked or ranked[0][0] < min_score:
        return []
    top = ranked[0][0]
    # keep only clear contenders: within 60% of the best match
    return [(round(sc, 2), s) for sc, s in ranked if sc >= min_score and sc >= 0.6 * top][:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("context", nargs="?", default="")
    ap.add_argument("--min", type=float, default=0.35)
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
            why = s.get("value") or s["description"][:140]
            print(f"- {s['name']} ({sc}): {why} -> {s['url']}")


if __name__ == "__main__":
    main()
