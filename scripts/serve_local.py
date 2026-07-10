#!/usr/bin/env python3
"""本地维护者服务器：静态服务 docs/ + 提供 /api/upload 写入数据库。

仅供本地使用（勿部署公开）。浏览器上传结构文件后：
  - 保存到 data/raw/<dest>/<POSCAR|CONTCAR>
  - 用 ASE 计算化学式/数密度/原子数，追加到 data/metadata/pcm_metadata.json/.csv
  - 增量更新 docs/data.json 并复制结构到 docs/structures/<sid>.poscar
  - （pcm.db 可用 scripts/build_asedb.py 另行重建）

用法: python scripts/serve_local.py [--port 8080]
"""
import argparse
import json
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ase.io import read

from annotate_functionality import classify  # 复用功能性标注规则

VALID_FN = {"PCM", "OTS", "SOM", "PCM candidates", "Others"}

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
RAW = ROOT / "data" / "raw"
META_JSON = ROOT / "data" / "metadata" / "pcm_metadata.json"
META_CSV = ROOT / "data" / "metadata" / "pcm_metadata.csv"
DATA_JSON = DOCS / "data.json"
STRUCT_DIR = DOCS / "structures"


def elements(formula):
    return sorted(set(re.findall(r"[A-Z][a-z]?", formula)))


def add_record(p):
    content = p["content"]
    if not content.strip():
        raise ValueError("空文件")
    up = (p.get("filename") or "").upper()
    fname = "CONTCAR" if "CONTCAR" in up else "POSCAR"
    dest = re.sub(r"\.+", ".", (p.get("dest") or "").strip().strip("/"))
    if not dest or ".." in dest or dest.startswith("/"):
        raise ValueError("非法存放路径")
    phase = p.get("phase")
    if phase not in ("amorphous", "liquid", "crystalline"):
        raise ValueError("相态非法")
    contributor = (p.get("contributor") or "").strip()
    if not contributor:
        raise ValueError("贡献者必填")
    temp = f"{int(str(p.get('temperature')).rstrip('Kk'))}K"

    dest_dir = RAW / dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    fpath = dest_dir / fname
    fpath.write_text(content, encoding="utf-8")

    atoms = read(str(fpath), format="vasp")
    vol = atoms.get_volume()
    n = len(atoms)
    rel = str(fpath.relative_to(RAW))

    formula = atoms.get_chemical_formula()
    func = (p.get("functionality") or "auto").strip()
    functionality = func if func in VALID_FN else classify(formula, is_mp=False)

    recs = json.loads(META_JSON.read_text(encoding="utf-8")) if META_JSON.exists() else []
    if any(r["结构文件"] == rel for r in recs):
        raise ValueError(f"已存在同路径记录: {rel}")
    rec = {
        "化学式": formula,
        "相": phase,
        "温度": temp,
        "功能性": functionality,
        "结构文件": rel,
        "密度_Atom_per_Angstrom3": round(n / vol, 5) if vol else None,
        "体系原子数": n,
        "贡献者": contributor,
        "HPC来源路径": (p.get("hpc_source") or "").strip(),
        "代表帧来源": "web-upload",
    }
    recs.append(rec)
    META_JSON.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    import pandas as pd
    pd.DataFrame(recs).to_csv(META_CSV, index=False, encoding="utf-8-sig")

    # 增量更新站点数据
    data = json.loads(DATA_JSON.read_text(encoding="utf-8")) if DATA_JSON.exists() else []
    used = {d["sid"] for d in data}
    idx = len(recs) - 1
    while f"s{idx:04d}" in used:
        idx += 1
    sid = f"s{idx:04d}"
    STRUCT_DIR.mkdir(parents=True, exist_ok=True)
    (STRUCT_DIR / f"{sid}.poscar").write_text(content, encoding="utf-8")
    els = elements(rec["化学式"])
    entry = {
        "sid": sid, "formula": rec["化学式"], "system": "".join(els), "elements": els,
        "phase": phase, "functionality": functionality, "temperature": temp, "natoms": n,
        "density": rec["密度_Atom_per_Angstrom3"], "contributor": contributor,
        "path": rel, "hpc_source": rec["HPC来源路径"], "source_frame": "web-upload",
    }
    data.append(entry)
    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return entry


class Handler(SimpleHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/ping":
            return self._json(200, {"ok": True, "backend": "local"})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/upload":
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            entry = add_record(payload)
            self._json(200, {"ok": True, "record": entry})
        except Exception as e:
            self._json(400, {"ok": False, "error": str(e)})

    def end_headers(self):
        # 本地开发：禁用缓存，保证改动即时可见
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(DOCS)))
    print(f"本地维护服务器: http://localhost:{args.port}/  (含上传功能, 仅本地)")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
