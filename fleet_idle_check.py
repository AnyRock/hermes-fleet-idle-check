#!/usr/bin/env python3
"""Fleet idle check: report live load of your local inference engines and
recommend one for Hermes subagent dispatch.

用法 / Usage:
    python3 fleet_idle_check.py [path/to/engines.json]   # engines.json defaults to next to this script

输出每行一台引擎，最后一行 `PICK <provider>` 为推荐目标。
在派 Hermes 子代理（delegate_task）之前跑本脚本，然后：
    hermes config set delegation.provider <PICK>
配置在每次派单时现读，改即生效、无需重启；子代理整个生命周期钉在所选引擎上。
"""
import json
import os
import sys
import urllib.request

HERMES_ENV = os.path.expanduser("~/.hermes/.env")


def env_key(name):
    """Look up a key in process env first, then ~/.hermes/.env."""
    if not name:
        return ""
    if name in os.environ:
        return os.environ[name]
    try:
        for line in open(HERMES_ENV, encoding="utf-8"):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return ""


def load_engines(path):
    with open(path, encoding="utf-8") as f:
        engines = json.load(f)
    for e in engines:
        if not e.get("provider") or not e.get("base_url"):
            raise ValueError("each engine needs 'provider' and 'base_url'")
    return engines


def probe(base, key):
    req = urllib.request.Request(base.rstrip("/") + "/metrics")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.load(r)


def main():
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engines.json")
    path = sys.argv[1] if len(sys.argv) > 1 else default
    engines = load_engines(path)

    rows = []
    for e in engines:
        key = env_key(e.get("key_env", ""))
        resident = bool(e.get("resident", True))
        try:
            d = probe(e["base_url"], key)
            live = d.get("live") or {}
            rows.append({
                "provider": e["provider"], "resident": resident, "err": None,
                "state": live.get("state", "?"), "queued": live.get("queued", "?"),
                "tok_s": live.get("tok_s"),
                "images": bool((d.get("engine") or {}).get("images")),
            })
        except Exception as ex:
            rows.append({"provider": e["provider"], "resident": resident,
                         "err": type(ex).__name__})

    for r in rows:
        if r["err"]:
            note = "not running (skipped)" if not r["resident"] else "unreachable"
            print(f"{r['provider']:<12} {note} [{r['err']}]")
        else:
            print(f"{r['provider']:<12} state={r['state']} queued={r['queued']} "
                  f"tok_s={r['tok_s']} images={r['images']}")

    # Pick: among resident+reachable engines prefer idle with empty queue;
    # ties broken by config order (put your preferred default first).
    idle = [r for r in rows if not r["err"] and r["resident"]
            and r["state"] == "idle" and r["queued"] == 0]
    if idle:
        print(f"PICK {idle[0]['provider']}")
        return 0
    alive = [r for r in rows if not r["err"] and r["resident"]]
    if alive:
        alive.sort(key=lambda r: r["queued"] if isinstance(r["queued"], int) else 9)
        print(f"PICK {alive[0]['provider']}  (none idle; least-queued)")
        return 0
    print("PICK none (no usable engine; do not dispatch)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
