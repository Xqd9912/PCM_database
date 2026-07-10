#!/usr/bin/env python
"""为前端 Structure Descriptors Visualization (beta) 预计算结构描述符。

方案（与项目负责人确认）：
  * 元素无关 SOAP —— 所有原子视为同一 species，仅编码局域几何/拓扑。
    62 种元素下若用全局 species 基组，原始维度约 90 万/原子，不可行；
    元素无关方案维度固定 252，任意筛选子集都落在同一可比空间，构建也快。
  * 每个结构：per-atom SOAP → 对原子取平均（average='outer'，即 beta 文档
    "n*m 特征矩阵取平均得单个结构特征量"）→ L2 归一化。
  * 完整向量直接落盘（252 维已足够小，无需离线压缩）；浏览器端对筛选后的
    子集即时做 PCA 降到 2D。

输入:
  docs/data.json                 —— 记录数组（提供 sid 顺序）
  docs/structures/<sid>.poscar   —— 每条记录的代表结构
输出:
  docs/descriptors.json          —— {meta, sids, dim, data(base64 float32 行主序)}

用法（在 pcm_database 环境内）:
  python scripts/build_descriptors.py
"""
import base64
import json
from pathlib import Path

import numpy as np
from ase.io import read
from dscribe.descriptors import SOAP

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = DOCS / "data.json"
STRUCT_DIR = DOCS / "structures"
OUT = DOCS / "descriptors.json"

# SOAP 超参（元素无关：单一 species）。r_cut 覆盖非晶第一、二配位壳层。
SOAP_PARAMS = dict(r_cut=6.0, n_max=8, l_max=6, periodic=True, average="outer")
DUMMY_Z = 6  # 所有原子重标为同一元素（C），实现元素无关

BATCH = 64  # dscribe.create 分批，便于打印进度


def load_atoms(sid: str):
    """读取 POSCAR，重标为单一 species，强制周期性。"""
    atoms = read(STRUCT_DIR / f"{sid}.poscar", format="vasp")
    atoms.set_atomic_numbers([DUMMY_Z] * len(atoms))
    atoms.set_pbc(True)
    return atoms


def main():
    recs = json.loads(DATA.read_text(encoding="utf-8"))
    sids = [r["sid"] for r in recs]

    soap = SOAP(species=[DUMMY_Z], **SOAP_PARAMS)
    dim = soap.get_number_of_features()
    print(f"records={len(sids)} SOAP dim={dim} params={SOAP_PARAMS}")

    vecs = np.zeros((len(sids), dim), dtype=np.float64)
    for start in range(0, len(sids), BATCH):
        batch_sids = sids[start:start + BATCH]
        atoms_list = [load_atoms(s) for s in batch_sids]
        out = soap.create(atoms_list, n_jobs=1)  # (n, dim)
        vecs[start:start + len(batch_sids)] = np.atleast_2d(out)
        print(f"  {min(start + BATCH, len(sids))}/{len(sids)}", flush=True)

    # 逐结构 L2 归一化（让 PCA 反映形状而非规模）
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    def b64(a):
        return base64.b64encode(a.astype(np.float32).ravel(order="C").tobytes()).decode("ascii")

    payload = {
        "meta": {
            "descriptor": "SOAP",
            "species_mode": "element-agnostic",
            "average": SOAP_PARAMS["average"],
            "normalized": "l2-per-structure",
            "r_cut": SOAP_PARAMS["r_cut"],
            "n_max": SOAP_PARAMS["n_max"],
            "l_max": SOAP_PARAMS["l_max"],
            "periodic": SOAP_PARAMS["periodic"],
            "note": "z-scored PCA is fit in-browser on the filtered subset.",
        },
        "dim": dim,
        "sids": sids,
        "data": b64(vecs),
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    mb = OUT.stat().st_size / 1e6
    print(f"wrote {OUT} ({mb:.2f} MB), {len(sids)}x{dim} float32")


if __name__ == "__main__":
    main()
