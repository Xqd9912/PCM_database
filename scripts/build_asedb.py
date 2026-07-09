#!/usr/bin/env python3
"""由 data/metadata/pcm_metadata.json + data/raw 结构文件构建 ASE 数据库 pcm.db。

pcm.db 是可查询的主库（SQLite 后端），每条记录 = 一个结构 + 键值对。
ASE 自动索引 formula / natoms / volume；这里额外写入 phase / temperature_K /
number_density / contributor / hpc_source / source_frame / rel_path。

用法: python build_asedb.py [--db pcm.db]
查询示例:
    ase db pcm.db "phase=amorphous,natoms>200"
    ase db pcm.db "GeSbTe" -c +number_density,contributor
"""
import argparse
import json
from pathlib import Path

from ase.db import connect
from ase.io import read

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "data" / "metadata" / "pcm_metadata.json"
RAW = ROOT / "data" / "raw"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "pcm.db")
    args = ap.parse_args()

    records = json.loads(META.read_text(encoding="utf-8"))

    if args.db.exists():
        args.db.unlink()  # 主库由 metadata 可重建，重建前清空（仅本地产物，非 HPC）
    db = connect(args.db)

    n = 0
    with db:
        for r in records:
            fpath = RAW / r["结构文件"]
            if not fpath.is_file():
                print(f"[skip] 缺文件 {r['结构文件']}")
                continue
            atoms = read(str(fpath), format="vasp")
            temp = int(str(r["温度"]).rstrip("Kk")) if r.get("温度") else None
            db.write(
                atoms,
                phase=r["相"],
                temperature_K=temp,
                number_density=r["密度_Atom_per_Angstrom3"],
                contributor=r["贡献者"],
                hpc_source=r["HPC来源路径"],
                source_frame=r.get("代表帧来源", ""),
                rel_path=r["结构文件"],
            )
            n += 1
    print(f"已写入 {n} 条 -> {args.db}")
    print(f"查询示例: ase db {args.db.relative_to(ROOT)} \"phase=amorphous,natoms>200\"")


if __name__ == "__main__":
    main()
