#!/usr/bin/env python3
"""Rebuilds the skill index from the whitelisted sources. Stdlib only.

Outputs (in --out):
  index.json       skills that passed every gate (what Claude/ChatGPT read)
  candidates.json  community skills that passed the checks but still need manual approval
  rejected.json    skills/sources excluded, with the reason
  changelog.json   added / removed / updated between runs

Usage: python3 crawler/build_index.py [--sources sources.json] [--out index]
Env:   GITHUB_TOKEN (optional, raises the API rate limit)
"""
import argparse, concurrent.futures as cf, datetime, hashlib, json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from security import scan  # noqa: E402

TRUST = {"official": 100, "verified": 80, "community": 40}
SCRIPT_EXT = (".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".cjs", ".ts", ".ps1", ".rb")
SKIP_PATH = re.compile(r"(^|/)(\.experimental|\.deprecated|node_modules|tests?|examples?|templates?)(/|$)", re.I)
STOP = set("""a an and are as at be by for from in into is it of on or the to use used using
when with this that these those you your can will should any all also its not only
il lo la i gli le un una di da in con su per tra fra e o che non se come del della dei
delle al alla quando questo questa usa usare skill skills claude user users file files""".split())
NOW = datetime.datetime.now(datetime.timezone.utc)


def http_get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "skill-advisor-crawler", "Accept": accept})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def gh(path):
    return json.loads(http_get(f"https://api.github.com/{path}"))


def parse_frontmatter(text):
    m = re.match(r"^﻿?---\s*\n(.*?)\n---", text, re.S)
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


def clean(text, limit=300):
    text = re.sub(r"<[^>]+>|[`*_#\[\]]", "", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def keywords(name, desc, n=12):
    seen, out = set(), []
    for w in re.findall(r"[a-zà-ù0-9]{3,}", f"{name.replace('-', ' ')} {desc}".lower()):
        if w not in STOP and w not in seen:
            seen.add(w); out.append(w)
    return out[:n]


def age_days(iso):
    return (NOW - datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


def crawl(src, gates, rejected):
    repo, tier = src["repo"], src["tier"]
    meta = gh(f"repos/{repo}")
    if meta.get("archived"):
        rejected.append({"id": src["id"], "reason": "repository archiviato"}); return []
    if age_days(meta["pushed_at"]) > gates["max_age_days"]:
        rejected.append({"id": src["id"], "reason": f"non aggiornato da {age_days(meta['pushed_at'])} giorni"}); return []
    if tier == "community":
        if meta.get("stargazers_count", 0) < gates["community_min_stars"]:
            rejected.append({"id": src["id"], "reason": "troppo poche stelle"}); return []
        if gates["community_license_required"] and not meta.get("license"):
            rejected.append({"id": src["id"], "reason": "nessuna licenza"}); return []

    branch = src.get("branch") or meta["default_branch"]
    sha = gh(f"repos/{repo}/commits/{branch}")["sha"]
    tree = [n for n in gh(f"repos/{repo}/git/trees/{sha}?recursive=1").get("tree", []) if n["type"] == "blob"]
    skill_files = [n["path"] for n in tree if n["path"].endswith("SKILL.md") and not SKIP_PATH.search(n["path"])]

    def fetch(path):
        return http_get(f"https://raw.githubusercontent.com/{repo}/{sha}/{path}", accept="text/plain")

    def one(path):
        folder = path.rsplit("/", 1)[0] if "/" in path else ""
        raw = fetch(path)
        fm = parse_frontmatter(raw)
        name, desc = clean(fm.get("name", ""), 80), clean(fm.get("description", ""))
        if not name or not desc or name in src.get("exclude", []):
            return None
        scripts = [n["path"] for n in tree if folder and n["path"].startswith(folder + "/")
                   and n["path"].lower().endswith(SCRIPT_EXT) and n.get("size", 0) < 300_000][:10]
        files = {path: raw}
        for p in scripts:
            try:
                files[p] = fetch(p)
            except Exception:
                pass
        high, med = scan(files, src.get("trusted_hosts", []))
        parts = folder.split("/")
        plugin = parts[parts.index("skills") - 1] if "skills" in parts[1:] else ""
        return {
            "id": f"{src['id']}/{plugin + '/' if plugin else ''}{name}",
            "name": name,
            "plugin": plugin,
            "description": desc,
            "keywords": keywords(name, desc),
            "source": src["id"],
            "tier": tier,
            "trust": TRUST[tier],
            "platforms": src.get("platforms", []),
            "url": f"https://github.com/{repo}/tree/{branch}/{folder}",
            "version": hashlib.sha256("".join(files[k] for k in sorted(files)).encode()).hexdigest()[:12],
            "_high": high,
            "_med": med,
        }

    with cf.ThreadPoolExecutor(16) as ex:
        return [x for x in ex.map(one, skill_files) if x]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="sources.json")
    ap.add_argument("--out", default="index")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.sources))

    cfg = json.load(open(a.sources))
    gates = cfg.get("gates", {"max_age_days": 365, "community_min_stars": 200, "community_license_required": True})
    approved = json.load(open(os.path.join(base, "approved.json"))).get("approved", {}) \
        if os.path.exists(os.path.join(base, "approved.json")) else {}
    enr_path = os.path.join(base, "enrichment", "skills.json")
    enr = json.load(open(enr_path)) if os.path.exists(enr_path) else {}

    accepted, candidates, rejected = [], [], []
    for src in cfg["sources"]:
        if src.get("enabled") is False:
            continue
        try:
            found = crawl(src, gates, rejected)
        except Exception as e:  # one broken source must not kill the run
            print(f"[warn] {src['id']}: {e}", file=sys.stderr)
            rejected.append({"id": src["id"], "reason": f"errore lettura: {e}"})
            continue
        n_ok = 0
        for it in found:
            high, med = it.pop("_high"), it.pop("_med")
            if it["tier"] == "official":
                if high or med:
                    it["warnings"] = high + med
            elif high:
                rejected.append({"id": it["id"], "reason": "sicurezza: " + ", ".join(high), "url": it["url"]})
                continue
            elif med:
                it["warnings"] = med
            if it["tier"] == "community" and it["id"] not in approved:
                candidates.append(it)
                continue
            accepted.append(it); n_ok += 1
        print(f"[ok] {src['id']}: {len(found)} trovate, {n_ok} accettate")

    seen, uniq = {}, []
    for it in sorted(accepted, key=lambda x: ("/claude/" not in x["url"], len(x["url"]))):
        k = (it["source"], it["name"], it["description"])
        if k not in seen:
            seen[k] = 1; uniq.append(it)
    accepted = uniq
    ids = {}
    for it in accepted:  # keep ids unique when one repo has two different skills with the same name/plugin
        n = ids[it["id"]] = ids.get(it["id"], 0) + 1
        if n > 1:
            it["id"] += f"~{n}"

    # dedupe by name: a copy from a less trusted source is dropped, the most trusted wins
    best = {}
    for it in accepted:
        cur = best.get(it["name"])
        if cur is None or it["trust"] > cur[0]["trust"]:
            best[it["name"]] = [it]
        elif it["trust"] == cur[0]["trust"]:
            cur.append(it)  # same tier: different skills that share a name (e.g. per-plugin "setup")
    skills = sorted((x for group in best.values() for x in group), key=lambda x: x["id"])
    candidates = [c for c in candidates if c["name"] not in best]

    for s in skills:
        e = enr.get(s["name"]) if s["source"] == "anthropic-skills" else enr.get(s["id"])
        if e:
            s.update({k: e[k] for k in ("category", "value", "examples", "not_for") if k in e})
            s["enriched"] = "ok" if e.get("for_version") == s["version"] else "stale"

    os.makedirs(a.out, exist_ok=True)
    idx_path = os.path.join(a.out, "index.json")
    old = {}
    if os.path.exists(idx_path):
        old = {s["id"]: s for s in json.load(open(idx_path)).get("skills", [])}
    # fail-safe: a run that lost most of the catalogue is a crawl problem, not reality
    if not skills or (old and len(skills) < 0.5 * len(old)):
        print(f"[abort] {len(skills)} skill (prima {len(old)}): indice precedente mantenuto", file=sys.stderr)
        sys.exit(1)

    new = {s["id"]: s for s in skills}
    now = NOW.isoformat(timespec="seconds")
    change = {"at": now, "added": sorted(set(new) - set(old)), "removed": sorted(set(old) - set(new)),
              "updated": sorted(k for k in set(new) & set(old) if new[k]["version"] != old[k]["version"])}

    def dump(name, obj, compact=False):
        with open(os.path.join(a.out, name), "w") as f:
            json.dump(obj, f, ensure_ascii=False, **({"separators": (",", ":")} if compact else {"indent": 1}))

    dump("index.json", {"schema": 2, "generated_at": now, "count": len(skills), "skills": skills}, compact=True)
    dump("candidates.json", sorted(candidates, key=lambda x: x["id"]))
    dump("rejected.json", rejected)
    log_path = os.path.join(a.out, "changelog.json")
    log = json.load(open(log_path)) if os.path.exists(log_path) else []
    if change["added"] or change["removed"] or change["updated"]:
        # keep the log small: store counts plus the first ids of each list
        log = ([{k: (v[:50] if isinstance(v, list) else v) for k, v in change.items()} |
                {"counts": {k: len(change[k]) for k in ("added", "removed", "updated")}}] + log)[:100]
    dump("changelog.json", log)
    by_tier = {t: sum(1 for s in skills if s["tier"] == t) for t in TRUST}
    print(f"[done] {len(skills)} skill {by_tier} | candidate {len(candidates)} | scartate {len(rejected)} "
          f"| +{len(change['added'])} -{len(change['removed'])} ~{len(change['updated'])}")


if __name__ == "__main__":
    main()
