#!/usr/bin/env python3
"""Check (and optionally fetch) the H3 model set on the network volume. Standard library only.

  verify_models.py                      report what is present / missing
  verify_models.py --download           also download missing confirmed files (resumable)
  verify_models.py --download --unconfirmed --optional   include the extras
Set HF_TOKEN if a repository needs a login. Never blocks boot: it only reports.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MANIFEST = os.path.join(os.path.dirname(HERE), "models.json")


def present(models_dir, entry):
    """Return (state, name) where state is ok / partial / missing."""
    want = entry["approx_gb"] * 1e9
    for name in entry["any_of"]:
        path = os.path.join(models_dir, entry["folder"], name)
        if os.path.isfile(path):
            size = os.path.getsize(path)
            if abs(size - want) <= want * 0.15:
                return "ok", name
            return "partial", name
        if os.path.isfile(path + ".part"):
            return "partial", name
    return "missing", entry["any_of"][0]


def download(url, dest, token):
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    have = os.path.getsize(part) if os.path.exists(part) else 0
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if have:
        req.add_header("Range", "bytes=%d-" % have)
    with urllib.request.urlopen(req, timeout=60) as r:
        total = have + int(r.headers.get("Content-Length", 0))
        mode = "ab" if have and r.status == 206 else "wb"
        if mode == "wb":
            have = 0
        done, last = have, time.time()
        with open(part, mode) as f:
            while True:
                chunk = r.read(8 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 15:
                    last = time.time()
                    print("    %.1f / %.1f GB" % (done / 1e9, total / 1e9), flush=True)
    os.replace(part, dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models-dir", default=os.environ.get("MODELS_DIR", "/workspace/models"))
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--unconfirmed", action="store_true", help="also download entries marked confirmed=false")
    ap.add_argument("--optional", action="store_true", help="also check/download optional entries")
    ap.add_argument("--json", help="write the report to this file")
    a = ap.parse_args()

    entries = json.load(open(a.manifest))["files"]
    report, missing_required = [], 0
    for e in entries:
        if e.get("optional") and not a.optional:
            continue
        state, name = present(a.models_dir, e)
        if state != "ok" and a.download and e.get("url") and (e.get("confirmed") or a.unconfirmed):
            dest = os.path.join(a.models_dir, e["folder"], os.path.basename(e["url"]))
            print("downloading %s (%.1f GB)" % (os.path.basename(dest), e["approx_gb"]), flush=True)
            try:
                download(e["url"], dest, os.environ.get("HF_TOKEN"))
                state, name = present(a.models_dir, e)
            except (urllib.error.URLError, OSError) as err:
                print("  failed: %s (run again to resume)" % err)
        line = "%-8s %s/%s" % (state.upper(), e["folder"], name)
        if e.get("confirmed") is False:
            line += "   (source not confirmed)"
        print(line)
        if state != "ok" and not e.get("optional"):
            missing_required += 1
        report.append({"folder": e["folder"], "file": name, "state": state})
    print("%d required file(s) not ready" % missing_required if missing_required else "model set complete")
    if a.json:
        os.makedirs(os.path.dirname(a.json), exist_ok=True)
        json.dump(report, open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
