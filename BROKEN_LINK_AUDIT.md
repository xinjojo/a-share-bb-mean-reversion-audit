# BROKEN_LINK_AUDIT.md — Markdown 内部链接完整性审计

**审计目标：** 扫描仓库内全部 Markdown 内部相对链接，确认 **0 unresolved broken links**。

**扫描范围：** 全文件系统所有 `.md` 文件（含 R0-C 新增入口文档），排除外部链接（`http/https/mailto`）与锚点（`#`）。

**审计结果：** `65` 个内部链接，`0` broken ✅

| 项目 | 值 |
|---|---|
| 扫描 Markdown 文件数 | 50 |
| 内部相对链接总数 | 65 |
| 未解析 broken links | **0** |
| 修复记录 | 迁移后修复旧 README 3 处失效路径链接（→ 重写为当前 canonical 路径）；新建 3 个入口文档（README/CURRENT_STATUS/RESEARCH_MAP）统一使用迁移后路径；R0.1 修复 README 中 1 处畸形 INVALID canonical 链接（`[[archive/invalid/](...)RESULTS_LATEST.md]` → 标准链接） |

**说明：**
- 迁移（R0-B，`git mv` 468 文件）后，旧版 README 中指向顶层旧路径的 3 个链接失效，已通过 R0-C 重写修复。
- 本审计为扫描时刻快照；新增/修改文档后应重新运行扫描。

**复现命令：**
```bash
python3 - << 'PYEOF'
import re, os
mds=[]
for root,dirs,files in os.walk('.'):
    if '.git' in root: continue
    mds += [os.path.join(root,f) for f in files if f.endswith('.md')]
rx=re.compile(r'\[[^\]]*\]\(([^)]+)\)|!\[[^\]]*\]\(([^)]+)\)')
bad=[]; total=0
for md in mds:
    base=os.path.dirname(md)
    for m in rx.finditer(open(md,encoding='utf-8',errors='replace').read()):
        t=(m.group(1) or m.group(2)).strip()
        if not t or t.startswith(('#','http://','https://','mailto:')): continue
        t=t.split('#')[0]
        if not t: continue
        total+=1
        if not os.path.exists(os.path.normpath(os.path.join(base,t))): bad.append((md,t))
print("links",total,"broken",len(bad),bad)
PYEOF
```
