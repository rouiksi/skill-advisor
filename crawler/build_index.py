#!/usr/bin/env python3
"""Rebuilds index/index.json from the whitelisted sources. Stdlib only.

Usage: python3 crawler/build_index.py [--sources sources.json] [--out index]
Env: GITHUB_TOKEN (optional, raises API rate limit).
"""
import argparse, datetime, hashlib, json, os, re, sys, urllib.request

STOP = set("""a an and are as at be by for from in into is it of on or the to use used using
when with this that these those you your can will should any all also its not only
il lo la i gli le un una di da in con su per tra fra e o che non se come del della dei
delle al alla quando questo questa usa usare skill skills claude user users file files""".split())


def http_get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "skill-advisor-crawler", "Accept": accept})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out, key = {}, None
    for line in m.group(1).splitlines():
        kv = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if kv:
            key, val = kv.group(1).lower(), kv.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val
        elif key and line.startswith((" ", "\t")):
            out[key] = (out[key] + " " + line.strip()).strip()
    return {k: v.strip().strip('"').strip("'") for k, v in out.items()}


def clean(text, limit=400):
    text = re.sub(r"<[^>]+>|[`*_#\[\]]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def tokens(text):
    return [w for w in re.findall(r"[a-zà-ù0-9]{3,}", text.lower()) if w not in STOP]


def keywords(name, desc, n=20):
    seen, out = set(), []
    for w in tokens(name.replace("-", " ")) + tokens(desc):
        if w not in seen:
            seen.add(w); out.append(w)
    return out[:n]


def crawl_github(src):
    repo, branch, prefix = src["repo"], src.get("branch", "main"), src.get("path_prefix", "")
    sha = json.loads(http_get(f"https://api.github.com/repos/{repo}/commits/{branch}"))["sha"]
    tree = json.loads(http_get(f"https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1"))
    items = []
    for node in tree.get("tree", []):
        path = node["path"]
        if node["type"] != "blob" or not path.endswith("SKILL.md") or not path.startswith(prefix):
            continue
        raw = http_get(f"https://raw.githubusercontent.com/{repo}/{sha}/{path}", accept="text/plain")
        fm = parse_frontmatter(raw)
        name, desc = clean(fm.get("name", ""), 80), clean(fm.get("description", ""))
        if not name or not desc or name in src.get("exclude", []):
            continue
        folder = path.rsplit("/", 1)[0] if "/" in path else ""
        items.append({
            "id": f"{src['id']}/{name}",
            "name": name,
            "description": desc,
            "keywords": keywords(name, desc),
            "source": src["id"],
            "trust": src.get("trust", 0),
            "platforms": src.get("platforms", []),
            "url": f"https://github.com/{repo}/tree/{branch}/{folder}",
            "version": hashlib.sha256(raw.encode()).hexdigest()[:12],
        })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="sources.json")
    ap.add_argument("--out", default="index")
    a = ap.parse_args()

    sources = json.load(open(a.sources))["sources"]
    best = {}
    for src in sources:
        try:
            found = crawl_github(src) if src["type"] == "github" else []
        except Exception as e:  # one broken source must not kill the run
            print(f"[warn] {src['id']}: {e}", file=sys.stderr)
            continue
        for it in found:  # dedupe by name, keep most trusted source
            cur = best.get(it["name"])
            if cur is None or it["trust"] > cur["trust"]:
                best[it["name"]] = it
        print(f"[ok] {src['id']}: {len(found)} skill")

    skills = sorted(best.values(), key=lambda x: x["name"])
    if not skills:
        print("[abort] 0 skill trovate: indice precedente mantenuto", file=sys.stderr)
        sys.exit(1)

    # merge enrichment (Italian/English examples, category, value); missing => flagged for review
    enr_path = os.path.join(os.path.dirname(a.sources) or ".", "enrichment", "skills.json")
    enr = json.load(open(enr_path)) if os.path.exists(enr_path) else {}
    for s in skills:
        e = enr.get(s["name"])
        if e:
            s.update({k: e[k] for k in ("category", "value", "examples", "not_for") if k in e})
            s["enriched"] = "ok" if e.get("for_version") == s["version"] else "stale"
        else:
            s["enriched"] = "missing"
    todo = [s["name"] for s in skills if s["enriched"] != "ok"]
    if todo:
        print(f"[enrich] da arricchire/aggiornare: {', '.join(todo)}")

    os.makedirs(a.out, exist_ok=True)
    idx_path = os.path.join(a.out, "index.json")
    old = {}
    if os.path.exists(idx_path):
        old = {s["id"]: s for s in json.load(open(idx_path)).get("skills", [])}
    new = {s["id"]: s for s in skills}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    change = {
        "at": now,
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "updated": sorted(k for k in set(new) & set(old) if new[k]["version"] != old[k]["version"]),
    }
    json.dump({"schema": 1, "generated_at": now, "count": len(skills), "skills": skills},
              open(idx_path, "w"), ensure_ascii=False, separators=(",", ":"))

    log_path = os.path.join(a.out, "changelog.json")
    log = json.load(open(log_path)) if os.path.exists(log_path) else []
    if change["added"] or change["removed"] or change["updated"]:
        log = ([change] + log)[:200]
    json.dump(log, open(log_path, "w"), ensure_ascii=False, indent=1)
    print(f"[done] {len(skills)} skill | +{len(change['added'])} -{len(change['removed'])} ~{len(change['updated'])}")


if __name__ == "__main__":
    main()
