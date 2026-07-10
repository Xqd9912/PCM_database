#!/usr/bin/env python3
"""由 pcm_metadata.json 生成前端站点数据（GitHub Pages 用）。

产出：
  docs/data.json          —— 记录数组（含 system/elements/sid）
  docs/structures/<sid>.poscar —— 每条记录的代表结构文件副本（供 3D 预览/下载）
"""
import json
import math
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "data" / "metadata" / "pcm_metadata.json"
ENERGY = ROOT / "data" / "metadata" / "energy.json"   # MLIP 预测能量(可选)
DOCS = ROOT / "docs"
OUT = DOCS / "data.json"
STRUCT_DIR = DOCS / "structures"
RAW = ROOT / "data" / "raw"


def elements(formula: str):
    return sorted(set(re.findall(r"[A-Z][a-z]?", formula)))


def main():
    recs = json.loads(META.read_text(encoding="utf-8"))
    energy = json.loads(ENERGY.read_text())["values"] if ENERGY.is_file() else {}
    if STRUCT_DIR.exists():
        shutil.rmtree(STRUCT_DIR)
    STRUCT_DIR.mkdir(parents=True, exist_ok=True)

    out = []
    for i, r in enumerate(recs):
        sid = f"s{i:04d}"
        src = RAW / r["结构文件"]
        if src.is_file():
            shutil.copy2(src, STRUCT_DIR / f"{sid}.poscar")
        els = elements(r["化学式"])
        out.append(
            {
                "sid": sid,
                "formula": r["化学式"],
                "system": "".join(els),
                "elements": els,
                "phase": r["相"],
                "temperature": r["温度"],
                "natoms": r["体系原子数"],
                "density": r["密度_Atom_per_Angstrom3"],
                "contributor": r["贡献者"],
                "path": r["结构文件"],
                "hpc_source": r["HPC来源路径"],
                "source_frame": r.get("代表帧来源", ""),
                "energy_per_atom": (lambda v: v if (v is not None and math.isfinite(v)) else None)(energy.get(sid)),  # MLIP(eV/atom)，非 DFT；非有限值记 null
            }
        )
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    n_struct = len(list(STRUCT_DIR.glob("*.poscar")))
    print(f"data.json: {len(out)} 条 ({OUT.stat().st_size//1024} KB)")
    print(f"structures/: {n_struct} 个结构文件")


if __name__ == "__main__":
    main()
