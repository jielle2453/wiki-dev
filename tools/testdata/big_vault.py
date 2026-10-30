"""把一個現成的知識庫放大成 N 張卡的測試庫，量 kb home／kb find 的速度用（Obsidian 首頁驗收 1、3；開發用、不進 zip）。

用法：python tools/testdata/big_vault.py <現成的 obsidian-spike 夾（裡面有 知識庫/ 和 來源/）> <輸出夾> [--cards 1000]

做法：整個複製到輸出夾，再把「原檔在、清冊 active、有檔案卡」的那幾份當樣本，一份一份複製成新的純文字原檔
（內容各不相同，不會被當成重複）加清冊條目加檔案卡，直到卡數到 N。只用標準函式庫。
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path


def front_split(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    return (m.group(1), m.group(2)) if m else (None, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--cards", type=int, default=1000)
    args = ap.parse_args()
    if args.out.exists():
        sys.exit(f"輸出夾已經在：{args.out}")
    shutil.copytree(args.base, args.out)
    vault = args.out / "知識庫"
    sources = json.loads((vault / ".system" / "sources.json").read_text(encoding="utf-8"))["sources"]
    roots = {s["alias"]: (vault / s["spec"]).resolve() for s in sources}
    inv_path = vault / ".system" / "inventory.json"
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    cards = {}
    for p in (vault / "檔案索引").rglob("*.md"):
        head, body = front_split(p.read_text(encoding="utf-8"))
        m = re.search(r"^編號: (f-[0-9a-f]+)$", head or "", re.M)
        if m:
            cards[m.group(1)] = (p, head, body)
    seeds = []
    for e in inv["entries"]:
        if e.get("status") != "active" or e.get("id") not in cards or e.get("kind") == "link":
            continue
        uri = e["locations"][0]["uri"]
        alias, _, rel = uri[len("file://"):].partition("/")
        if alias in roots and (roots[alias] / rel).is_file():
            seeds.append((e, alias, rel))
    if not seeds:
        sys.exit("找不到可以當樣本的卡（原檔在、清冊 active、有檔案卡）")
    have = sum(1 for e in inv["entries"] if e.get("status") == "active" and e.get("id") in cards)
    n = 0
    while have + n < args.cards:
        entry, alias, rel = seeds[n % len(seeds)]
        n += 1
        stem = Path(rel).stem
        new_rel = str(Path(rel).with_name(f"{stem}_c{n}.txt")).replace("\\", "/")
        data = f"{stem} 複本 {n}\n這是放大測試庫用的第 {n} 份檔案，內容各不相同。\n".encode("utf-8")
        target = roots[alias] / new_rel
        target.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        fid = "f-" + hashlib.sha256(f"{alias}/{new_rel}".encode("utf-8")).hexdigest()[:8]
        new = json.loads(json.dumps(entry))
        new["id"] = fid
        new["locations"] = [{"uri": f"file://{alias}/{new_rel}", "size": len(data), "mtime": "2026-10-26T16:57:26"}]
        new["fingerprints"] = [{"sha256": sha, "text_sha256": sha, "time": entry["first_seen"], "turn": entry["created_turn"]}]
        new["agenda_fp"] = sha[:12]
        new["first_seen"] = f"2026-10-{1 + n % 28:02d}T09:{n % 60:02d}:00"
        inv["entries"].append(new)
        cpath, head, body = cards[entry["id"]]
        title = re.search(r"^標題: (.*)$", head, re.M).group(1)
        new_title = f"{title} 複本{n}"
        lines = head.split("\n")
        out = []
        skip_list = False
        for ln in lines:
            if skip_list and ln.startswith("  - "):
                continue
            skip_list = False
            if ln.startswith("編號:"):
                ln = f"編號: {fid}"
            elif ln.startswith("標題:"):
                ln = f"標題: {new_title}"
            elif ln.startswith("指紋:"):
                ln = f"指紋: {sha}"
            elif ln.startswith("原檔:"):
                out.append(ln)
                out.append(f"  - file://{alias}/{new_rel}")
                skip_list = True
                continue
            elif ln.startswith("開原檔:"):
                ln = "開原檔: file:" + urllib.request.pathname2url(str(target))
            out.append(ln)
        card = "---\n" + "\n".join(out) + "\n---\n" + body.replace(f"# {title}", f"# {new_title}", 1)
        dest = cpath.parent / f"{new_title}-{fid[2:]}.md"
        dest.write_text(card, encoding="utf-8", newline="\n")
    inv_path.write_text(json.dumps(inv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"放大完成：新增 {n} 張卡（共 {have + n} 張）：{vault}")


if __name__ == "__main__":
    main()
