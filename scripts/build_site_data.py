#!/usr/bin/env python3
"""由 pcm_metadata.json 生成前端站点数据 docs/data.json（GitHub Pages 用）。

追加 system 字段（去掉数字的成分体系，如 GeSbTe），供前端分组统计。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "data" / "metadata" / "pcm_metadata.json"
OUT = ROOT / "docs" / "data.json"


def system(formula: str) -> str:
    # 元素符号按字母序拼接，作为成分体系标识
    els = sorted(set(re.findall(r"[A-Z][a-z]?", formula)))
    return "".join(els)


def main():
    recs = json.loads(META.read_text(encoding="utf-8"))
    out = []
    for r in recs:
        out.append(
            {
                "formula": r["化学式"],
                "system": system(r["化学式"]),
                "phase": r["相"],
                "temperature": r["温度"],
                "natoms": r["体系原子数"],
                "density": r["密度_Atom_per_Angstrom3"],
                "contributor": r["贡献者"],
                "path": r["结构文件"],
                "hpc_source": r["HPC来源路径"],
                "source_frame": r.get("代表帧来源", ""),
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"写入 {len(out)} 条 -> {OUT}  ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
