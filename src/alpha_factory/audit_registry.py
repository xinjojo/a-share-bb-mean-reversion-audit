"""A-Share Alpha Factory — registry integrity audit（Phase 0.1）。

一键检查治理账本是否健康，输出 REGISTRY_INTEGRITY_REPORT.md；
任何 P0 问题 → exit non-zero。

检查项（P0）：
- factor_id / experiment_id / attempt_id 唯一性（含空 attempt_id）
- 同一 (expression_hash, universe) 在 Registry 重复（有 AMBIGUITY 治理事件
  的 curated 例外按 P1 记录，仍须指出）
- Graveyard 同一 factor_id 重复
- Library 门禁：成员必须 status==KEEP 且全 gate PASS
- 状态迁移合法性（从 STATUS_HISTORY 重放）
- 空时间戳（created_date / date_killed / approved_date / timestamp / attempt date）
- orphan：Graveyard / Library / Candidates / StatusHistory 指向不存在的 factor_id
- 非法终态（KEEP/FAIL/... 之后又有迁移）
- CSV/parquet 行数 parity
检查项（P1）：空 canonical_expression / 空 formula / 空 factor_name。
"""
from __future__ import annotations

import os

import pandas as pd

from alpha_factory import registry as R

BASE = R.BASE
REPORT = os.path.join(BASE, 'REGISTRY_INTEGRITY_REPORT.md')


def _p0s() -> tuple[list[str], list[str]]:
    out: list[str] = []
    p1: list[str] = []
    reg = R.Registry()
    gy = R.Graveyard()
    lib = R.Library()
    cand = R.Candidates()
    exp = R.Experiments()
    mt = R.MultipleTestingLedger()
    hist = R.StatusHistory()
    gov = R.GovernanceEvents()

    # 1. 唯一性
    if reg.df['factor_id'].duplicated().any():
        dups = reg.df.loc[reg.df['factor_id'].duplicated(), 'factor_id'].tolist()
        out.append(f'P0: FACTOR_REGISTRY duplicated factor_id: {dups}')
    if exp.df['experiment_id'].duplicated().any():
        out.append('P0: EXPERIMENT_REGISTRY duplicated experiment_id')
    if mt.df['attempt_id'].isna().any() or mt.df['attempt_id'].duplicated().any():
        out.append('P0: MULTIPLE_TESTING_LEDGER attempt_id empty or duplicated')

    # 2. Registry 表达式重复（排除有 AMBIGUITY 治理事件的行 → P1）
    h = reg.df[reg.df['expression_hash'].notna()]
    amb_ids = set(gov.df.loc[gov.df['kind'] == 'EXPRESSION_HASH_AMBIGUITY',
                             'factor_id'].dropna())
    dup_pairs = h[h.duplicated(subset=['expression_hash', 'universe'],
                               keep=False)]
    for _fid, g in dup_pairs.groupby(['expression_hash', 'universe']):
        ids = g['factor_id'].tolist()
        non_amb = [i for i in ids if i not in amb_ids]
        amb = [i for i in ids if i in amb_ids]
        if len(non_amb) >= 2 or (len(non_amb) >= 1 and not amb):
            out.append(f'P0: duplicate canonical expression in REGISTRY: {ids} '
                       f'(ambig-excepted: {amb})')
        elif amb:
            p1.append(f'P1: duplicate expression w/ documented ambiguity '
                      f'exception: {ids} (excepted: {amb})')

    # 3. Graveyard 重复
    if gy.df['factor_id'].duplicated().any():
        out.append('P0: ALPHA_GRAVEYARD duplicated factor_id')

    # 4. Library 门禁
    for _, row in lib.df.iterrows():
        fid = row['factor_id']
        cur = reg.current_status(fid)
        probs = []
        if cur != 'KEEP':
            probs.append(f'status={cur}')
        for f in ['multiple_testing_status', 'incremental_alpha_status',
                  'oos_audit', 'leakage']:
            v = row.get(f)
            if not ((v is True) or (isinstance(v, str) and str(v).upper() == 'PASS')):
                probs.append(f'{f}={v}')
        if probs:
            out.append(f'P0: LIBRARY gate violation {fid}: {"; ".join(probs)}')

    # 5. 状态机重放
    forced = set(gov.df.loc[gov.df['kind'] == 'FORCED_STATUS_TRANSITION',
                            'factor_id'].dropna())
    hist_sorted = hist.df.sort_values('timestamp')
    for fid, g in hist_sorted.groupby('factor_id'):
        prev = None
        for _, ev in g.iterrows():
            old = ev['old_status']
            new = ev['new_status']
            if old is None or pd.isna(old):  # 初始事件（backfill/REGISTER）恒合法
                prev = new
                continue
            legal = (new in R.LEGAL_TRANSITIONS.get(prev, set())
                     and prev not in R.TERMINAL_STATUSES)
            if not legal:
                msg = (f'illegal status transition {fid}: {prev} -> {new} '
                       f'({ev.get("reason")})')
                if fid in forced:
                    p1.append(f'P1: {msg} [FORCED_STATUS_TRANSITION documented]')
                else:
                    out.append(f'P0: {msg}')
            prev = new

    # 6. 空时间戳
    if reg.df['created_date'].isna().any():
        out.append('P0: FACTOR_REGISTRY empty created_date')
    if gy.df['date_killed'].isna().any():
        out.append('P0: ALPHA_GRAVEYARD empty date_killed')
    if lib.df['approved_date'].isna().any():
        out.append('P0: ALPHA_LIBRARY empty approved_date')
    if exp.df['timestamp'].isna().any():
        out.append('P0: EXPERIMENT_REGISTRY empty timestamp')
    if hist.df['timestamp'].isna().any():
        out.append('P0: STATUS_HISTORY empty timestamp')
    if mt.df['date'].isna().any():
        out.append('P0: MT_LEDGER empty attempt date')

    # 7. orphan
    reg_ids = set(reg.df['factor_id'])
    for name, df, col in [('GRAVEYARD', gy.df, 'factor_id'),
                          ('LIBRARY', lib.df, 'factor_id'),
                          ('CANDIDATES', cand.df, 'factor_id'),
                          ('STATUS_HISTORY', hist.df, 'factor_id')]:
        orph = sorted(set(df[col].dropna()) - reg_ids)
        if orph:
            out.append(f'P0: orphan factor_id in {name}: {orph}')

    # 8. CSV/parquet parity
    for parq, csvp, _cols in R.store_paths():
        if os.path.exists(parq):
            n_p = len(pd.read_parquet(parq))
            n_c = len(pd.read_csv(csvp)) if os.path.exists(csvp) else -1
            if n_p != n_c:
                out.append(f'P0: CSV/parquet parity {os.path.basename(parq)}: '
                           f'{n_p} vs {n_c}')

    # P1
    if reg.df['canonical_expression'].isna().any():
        p1.append('P1: empty canonical_expression in REGISTRY')
    if reg.df['formula'].isna().any():
        p1.append('P1: empty formula in REGISTRY')
    return out, p1


def write_report() -> tuple[list[str], list[str]]:
    p0, p1 = _p0s()
    reg = R.Registry()
    gy = R.Graveyard()
    lib = R.Library()
    cand = R.Candidates()
    exp = R.Experiments()
    mt = R.MultipleTestingLedger()
    hist = R.StatusHistory()
    gov = R.GovernanceEvents()

    lines = ['# Alpha Factory — Registry Integrity Audit', '']
    lines.append(f'- 审计时间: {R._now_ts()}')
    lines.append(f'- 版本: alpha-factory phase 0.1 governance hardening')
    lines.append('')
    lines.append('## 库规模')
    for name, df in [('FACTOR_REGISTRY', reg.df), ('ALPHA_GRAVEYARD', gy.df),
                     ('ALPHA_LIBRARY', lib.df), ('ALPHA_CANDIDATES', cand.df),
                     ('EXPERIMENT_REGISTRY', exp.df),
                     ('MULTIPLE_TESTING_LEDGER', mt.df),
                     ('FACTOR_STATUS_HISTORY', hist.df),
                     ('GOVERNANCE_EVENTS', gov.df)]:
        lines.append(f'- {name}: {len(df)} 行')
    lines.append('')
    lines.append('## 计数口径（多口径）')
    for k, v in mt.summary().items():
        lines.append(f'- {k} = {v}')
    lines.append('')
    lines.append('## P0 问题')
    if p0:
        for x in p0:
            lines.append(f'- [FAIL] {x}')
    else:
        lines.append('- 无')
    lines.append('')
    lines.append('## P1 问题')
    if p1:
        for x in p1:
            lines.append(f'- [WARN] {x}')
    else:
        lines.append('- 无')
    lines.append('')
    lines.append('## 结论')
    lines.append('P0=0 → REGISTRY INTEGRITY PASS' if not p0
                 else f'P0={len(p0)} → REGISTRY INTEGRITY FAIL (exit non-zero)')
    lines.append('')
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return p0, p1


def main() -> int:
    p0, p1 = write_report()
    for x in p0:
        print(f'[P0] {x}')
    for x in p1:
        print(f'[P1] {x}')
    print(f'REGISTRY_INTEGRITY_REPORT -> {REPORT}')
    print(f'P0 = {len(p0)} ; P1 = {len(p1)}')
    return 1 if p0 else 0


if __name__ == '__main__':
    raise SystemExit(main())
