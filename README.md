# PCM Database

相变材料 / OTS / SOM 材料的结构数据库。存储非晶/液态/晶态结构（POSCAR/CONTCAR）及其 metadata，
方便课题组维护、贡献上传和下载。

## 架构：ASE db + Git 混合

- **结构与 metadata（Git 跟踪，真源）**
  - `data/raw/<成员>/<路径>/{POSCAR,CONTCAR,INCAR}` — 结构文件，保留 HPC 来源路径结构
  - `data/metadata/pcm_metadata.json` / `.csv` — metadata 索引（真源）
- **可查询主库（本地重建，不入 Git）**
  - `data/pcm.db` — ASE 数据库（SQLite），由 metadata + data/raw 重建

## 环境

```bash
conda create -n pcm_database python=3.11 -y
conda activate pcm_database
pip install ase paramiko pandas
```

## metadata 字段

| 字段 | 说明 |
|---|---|
| 化学式 | ASE 从结构文件读取 |
| 相 | amorphous / liquid / crystalline |
| 温度 | 如 300K |
| 结构文件 | 相对 data/raw 的路径 |
| 密度_Atom_per_Angstrom3 | 数密度 = 原子数 / 晶胞体积 |
| 体系原子数 | |
| 贡献者 | 上传者 |
| HPC来源路径 | 原始 HPC 路径，供溯源 |
| 代表帧来源 | opt-CONTCAR / md-first-frame / manual-add |

## 下载 / 构建主库

```bash
git clone <repo> && cd PCM_database
conda activate pcm_database
python scripts/build_asedb.py          # 生成 data/pcm.db
```

## 查询（ASE CLI）

```bash
ase db data/pcm.db "phase=amorphous,natoms>200"
ase db data/pcm.db "GeSbTe" -c +number_density,contributor,temperature_K
ase db data/pcm.db --count
ase db data/pcm.db -w                   # 启动 Web 浏览界面
```

## 贡献上传

```bash
python scripts/add_structure.py path/to/CONTCAR \
    --phase amorphous --temperature 300 --contributor "你的名字" \
    --dest GeTe/model_01 [--hpc-source "~/xqd/.../CONTCAR"]
git add data/ && git commit -m "add: GeTe model_01"
```
`add_structure.py` 会自动计算化学式/数密度/原子数，追加 metadata 并重建主库。

## Web 主页（GitHub Pages）

`docs/` 是一个纯静态站点（无后端），可用 GitHub Pages 直接托管：概览统计、
材料体系/原子数/数密度图表、可筛选排序的结构浏览表，明暗主题自适应。

```bash
python scripts/build_site_data.py     # 由 metadata 生成 docs/data.json
# 本地预览（纯静态，无上传）
python -m http.server 8000 --directory docs   # 访问 http://localhost:8000

# 本地维护模式（带网页上传功能，推荐维护者使用）
python scripts/serve_local.py --port 8080     # 访问 http://localhost:8080
```

**网页上传（仅本地维护模式）**：`serve_local.py` 在静态站基础上提供 `/api/upload`。
浏览器点右上「⬆ 上传数据」→ 选 POSCAR/CONTCAR（自动算化学式/原子数/密度并 3D 预览）→
填相态/温度/贡献者/存放路径 → 提交，即写入 `data/raw` + 追加 metadata + 更新 `docs/data.json`。
之后 `python scripts/build_asedb.py` 重建主库、`git push` 发布。公开 Pages 无后端，上传按钮自动隐藏。

启用 GitHub Pages：仓库 Settings → Pages → Source 选 `main` 分支的 `/docs` 目录。

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/hpc.sh` | 驱动持久 SSH 会话向 HPC 发命令 |
| `scripts/hpc_scan.sh` | 扫描 HPC 全组含 INCAR 计算目录 |
| `scripts/classify_inventory.py` | 按 IBRION/TEBEG 分类，筛非晶候选 |
| `scripts/dedup_models.py` | 智能去重，每独立模型留一代表 |
| `scripts/build_metadata.py` | ASE 提取，产出 metadata（批量流程） |
| `scripts/build_asedb.py` | 由 metadata 构建 ASE 主库 |
| `scripts/build_site_data.py` | 由 metadata 生成前端 docs/data.json |
| `scripts/build_descriptors.py` | 预计算主库结构的 SOAP 描述符 |
| `scripts/build_mlip_data.py` | 登记 MLIP 训练集，产出统计 / 直方图 / SOAP 抽样 |
| `scripts/add_structure.py` | 贡献助手：新增单个结构 |

## MLIP 训练数据集

`data/MLIP_training_data_DFT_labeled/*.xyz`（extended XYZ，含 `REF_energy` / `REF_forces`）
是用于训练机器学习势函数的 DFT 标注数据，共 **9608 帧 / 1381448 个原子**，四个数据集：
GST225 (4577)、Sb2Te3 (2509)、GeTe (2439)、MP_filtered_pure_GST (83)。

```bash
python scripts/build_mlip_data.py              # 全量重建（解析 + SOAP）
python scripts/build_mlip_data.py --skip-soap  # 只重算统计，复用已有描述符
```

产出：`data/metadata/mlip_metadata.{json,csv}`（每帧一条登记记录，全量）、
`docs/mlip.json`（数据集统计 + 能量/受力直方图分箱）、
`docs/mlip_descriptors.json`（抽样帧的 SOAP 向量，供前端做 PCA）。

口径：直方图与数据集统计走**全量帧**；SOAP 分布图对每个数据集沿轨迹**均匀抽样，上限 800 帧/集**
（MD 相邻帧高度相关，抽样几乎不改变分布形状，却把描述符文件压到与 `docs/descriptors.json` 同量级）。
SOAP 超参与 `build_descriptors.py` 完全一致，故 MLIP 帧与主库结构落在同一可比特征空间。
直方图按 0.1–99.9% 分位裁剪显示范围，范围外样本**单独计数并在图注中说明**（不折进边界箱，
否则会造出并不存在的尖峰）。原始 xyz 体积过大不入 Git（见 `.gitignore`）。

## 数据来源说明（第一批）

从 HPC 全组 8 个成员目录扫描 15025 个计算目录，按熔淬流程（2000K 熔化→quench 300K→opt→MD）
筛选**代表性非晶模型**（优先 opt 末帧 CONTCAR，否则 300K MD 第一帧），智能去重后得 **731 条非晶结构**。
已知局限：少量无路径标记的晶态 opt 可能混入（见 `data/metadata/excluded_crystalline_review.tsv`）。
# PCM_database
