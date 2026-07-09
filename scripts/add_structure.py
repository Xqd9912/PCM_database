#!/usr/bin/env python3
"""贡献助手：新增一个结构到数据库。

自动用 ASE 计算化学式/数密度/原子数，其余字段由参数给定，
把结构文件复制进 data/raw/，追加一条到 pcm_metadata.json/csv，
并重建 pcm.db。

用法示例:
    python add_structure.py path/to/CONTCAR \
        --phase amorphous --temperature 300 --contributor "Qundao Xu" \
        --dest GeTe/my_model_01 [--hpc-source "~/xqd/.../CONTCAR"]
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ase.io import read

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
META_JSON = ROOT / "data" / "metadata" / "pcm_metadata.json"
META_CSV = ROOT / "data" / "metadata" / "pcm_metadata.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("struct", type=Path, help="结构文件 (POSCAR/CONTCAR)")
    ap.add_argument("--phase", required=True, choices=["amorphous", "liquid", "crystalline"])
    ap.add_argument("--temperature", required=True, help="温度，如 300 或 300K")
    ap.add_argument("--contributor", required=True)
    ap.add_argument("--dest", required=True,
                    help="在 data/raw 下的相对目录，如 GeTe/model_01")
    ap.add_argument("--hpc-source", default="", help="HPC 来源路径（可选）")
    args = ap.parse_args()

    atoms = read(str(args.struct), format="vasp")
    vol = atoms.get_volume()
    fname = args.struct.name if args.struct.name in ("POSCAR", "CONTCAR") else "POSCAR"
    dest_dir = RAW / args.dest
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / fname
    shutil.copy2(args.struct, dest_file)
    rel = str(dest_file.relative_to(RAW))

    temp = f"{int(str(args.temperature).rstrip('Kk'))}K"
    rec = {
        "化学式": atoms.get_chemical_formula(),
        "相": args.phase,
        "温度": temp,
        "结构文件": rel,
        "密度_Atom_per_Angstrom3": round(len(atoms) / vol, 5) if vol else None,
        "体系原子数": len(atoms),
        "贡献者": args.contributor,
        "HPC来源路径": args.hpc_source,
        "代表帧来源": "manual-add",
    }

    records = json.loads(META_JSON.read_text(encoding="utf-8")) if META_JSON.exists() else []
    if any(x["结构文件"] == rel for x in records):
        print(f"[warn] {rel} 已存在于 metadata，跳过追加。")
    else:
        records.append(rec)
        META_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        import pandas as pd
        pd.DataFrame(records).to_csv(META_CSV, index=False, encoding="utf-8-sig")
        print(f"已追加: {rec['化学式']} {temp} {args.phase} -> {rel}")

    # 重建 pcm.db
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_asedb.py")], check=True)


if __name__ == "__main__":
    main()
