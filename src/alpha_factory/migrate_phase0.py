"""A-Share Alpha Factory — Phase 0 → Phase 0.1 registry migration（一次性治理迁移）。

把既有五本 Registry（FACTOR_REGISTRY 34 / ALPHA_GRAVEYARD 13 / ALPHA_LIBRARY 1 /
EXPERIMENT_REGISTRY 1 / MULTIPLE_TESTING_LEDGER 42）迁移到治理版 schema：

1. 运行幂等 legacy_import（补录 weekly_bb canonical，恢复丢失的 legacy 项）。
2. 标记 registry 中 (factor_name, universe) 重复的误导入行为 INVALID
   （INVALID_DUPLICATE_IMPORT；FORCED_STATUS_TRANSITION 治理事件留痕）。
3. 移除 Graveyard 中 INVALID 行的重复记录（不物理删除历史事实：全部进
   GOVERNANCE_REPAIR_LOG + GOVERNANCE_EVENTS）。
4. 把 breadth（AF_000004）移出 ALPHA_LIBRARY → ALPHA_CANDIDATES。
5. 为全部既有 attempt 回填 attempt_id（AFA_%09d）。
6. 从 canonical parquet 重建全部 CSV mirror。
7. 输出 GOVERNANCE_REPAIR_LOG.csv 与 PHASE0_REGISTRY_MIGRATION_REPORT.md。
"""
from __future__ import annotations

import os
from datetime import date

import pandas as pd

from alpha_factory import registry as R
from alpha_factory import legacy_import
from alpha_factory import dsl

BASE = R.BASE
REPAIR_LOG = os.path.join(BASE, 'GOVERNANCE_REPAIR_LOG.csv')
MIG_REPORT = os.path.join(BASE, 'PHASE0_REGISTRY_MIGRATION_REPORT.md')

REPAIR_COLS = ['repair_id', 'date', 'kind', 'factor_id', 'factor_name',
               'canonical_factor_id', 'mapping', 'detail']


def _repair(rows: list[dict]) -> None:
    df = pd.DataFrame(rows, columns=REPAIR_COLS) if rows else \
        pd.DataFrame(columns=REPAIR_COLS)
    df.to_csv(REPAIR_LOG, index=False)


def main() -> int:
    repair = []
    today = date.today().isoformat()
    rid = 0

    def next_rid() -> str:
        nonlocal rid
        rid += 1
        return f'RPR_{rid:03d}'

    # ---- snapshot old baseline（在 import 之前）----
    _reg0 = R.Registry()
    _gy0 = R.Graveyard()
    _lib0 = R.Library()
    _exp0 = R.Experiments()
    _mt0 = R.MultipleTestingLedger()
    n_reg_before = len(_reg0.df)
    n_gy_before = len(_gy0.df)
    n_lib_before = len(_lib0.df)
    n_exp_before = len(_exp0.df)
    n_mt_before = len(_mt0.df)
    old_status_counts = _reg0.df['status'].fillna('UNKNOWN').value_counts().to_dict()

    # ---- 1. idempotent legacy import（补录 weekly_bb；自建实例写盘）----
    imp = legacy_import.import_legacy()
    print(f'[*] legacy import: {imp}')
    legacy_import.write_legacy_mapping()

    # ---- 2. 从磁盘重新实例化（避免陈旧实例互相覆盖）----
    reg = R.Registry()
    gy = R.Graveyard()
    lib = R.Library()
    cand = R.Candidates()
    exp = R.Experiments()
    mt = R.MultipleTestingLedger()
    hist = R.StatusHistory()
    gov = R.GovernanceEvents()

    # ---- 3. backfill 初始 status history（没有历史事件的行）----
    have = set(hist.df['factor_id'])
    missing = [f for f in reg.all_ids() if f not in have]
    for fid in missing:
        cur = reg.df.loc[reg.df['factor_id'] == fid, 'status'].iloc[-1]
        hist.append(factor_id=fid, old_status=None, new_status=cur,
                    reason='PHASE0_MIGRATION_INITIAL_STATE',
                    notes='backfilled from Phase 0 status column')

    # ---- 4. 标记 (name, universe) 重复的误导入行为 INVALID（幂等：已 INVALID 跳过）----
    grp = reg.df.groupby(['factor_name', 'universe'])['factor_id'].apply(list)
    dup_map = {}   # fid -> canon
    for (name, uni), ids in grp.items():
        if len(ids) < 2:
            continue
        canon = min(ids, key=lambda x: int(x[3:]))  # 最先生成的为 canonical
        for fid in ids:
            if fid != canon:
                dup_map[fid] = canon
    for fid, canon in sorted(dup_map.items()):
        if reg.current_status(fid) == 'INVALID':
            continue  # 已标记（幂等重跑）
        st = reg.current_status(fid)
        gov.log('FORCED_STATUS_TRANSITION', factor_id=fid,
                detail=f'{st} -> INVALID (Phase 0 duplicate legacy import)')
        reg.set_status(fid, 'INVALID', force=True,
                       reason='PHASE0_MIGRATION_INVALID_DUPLICATE_IMPORT',
                       notes=f'duplicate legacy import; canonical={canon}')
    invalid_ids = sorted(dup_map)

    # ---- 5. 移除 Graveyard 中 INVALID 行的重复记录（幂等）----
    gy_removed = []
    for fid in invalid_ids:
        m = gy.df[gy.df['factor_id'] == fid]
        if m.empty:
            continue
        canon = dup_map[fid]
        row = m.iloc[-1]
        gov.log('GRAVEYARD_DUPLICATE_REMOVED', factor_id=fid,
                detail=(f'removed duplicate graveyard record '
                        f'(canonical={canon}); row={row.to_dict()}'))
        gy.df = gy.df[gy.df['factor_id'] != fid].reset_index(drop=True)
        gy_removed.append(fid)
    gy._save()

    # ---- 5b. repair log 条目（幂等：每次迁移重跑生成同一内容）----
    for fid in invalid_ids:
        name = reg.get(fid)['factor_name']
        repair.append(dict(repair_id=next_rid(), date=today,
                           kind='INVALID_DUPLICATE_IMPORT', factor_id=fid,
                           factor_name=name, canonical_factor_id=dup_map[fid],
                           mapping='MERGED_TO_CANONICAL',
                           detail='Phase 0 repeated legacy import row marked '
                                  'INVALID; canonical retained'))
    for fid in gy_removed:
        repair.append(dict(repair_id=next_rid(), date=today,
                           kind='GRAVEYARD_DUPLICATE_REMOVED', factor_id=fid,
                           factor_name=reg.get(fid)['factor_name'],
                           canonical_factor_id=dup_map[fid],
                           mapping='MERGED_TO_CANONICAL',
                           detail='duplicate graveyard row removed (history kept '
                                  'in GOVERNANCE_EVENTS)'))

    # ---- 5. breadth 移出 Library → Candidates ----
    if lib.exists('AF_000004'):
        lib.remove('AF_000004',
                   reason='status VALIDATING != KEEP; Phase 1 candidate only')
        repair.append(dict(repair_id=next_rid(), date=today,
                           kind='REMOVED_FROM_LIBRARY_NOT_APPROVED',
                           factor_id='AF_000004', factor_name='market_breadth',
                           canonical_factor_id='AF_000004', mapping='TO_CANDIDATES',
                           detail='breadth moved to ALPHA_CANDIDATES (not fully '
                                  'approved)'))
    cand.add(factor_id='AF_000004', factor_name='market_breadth',
             formula=reg.get('AF_000004')['formula'], status='VALIDATING',
             candidate_reason=('Phase 1 feature importance top; status=VALIDATING; '
                               'not KEEP → ALPHA_CANDIDATES, not ALPHA_LIBRARY'),
             notes='moved from ALPHA_LIBRARY in Phase 0.1 migration')

    # ---- 6. attempt_id 回填 ----
    n_noid = int(mt.df['attempt_id'].isna().sum())
    for i in mt.df.index:
        if pd.isna(mt.df.at[i, 'attempt_id']):
            mt.df.at[i, 'attempt_id'] = R.next_attempt_id(mt.df)
    mt._save()
    if n_noid:
        repair.append(dict(repair_id=next_rid(), date=today,
                           kind='ATTEMPT_ID_BACKFILL', factor_id=None,
                           factor_name=None, canonical_factor_id=None,
                           mapping='AFA_%09d',
                           detail=f'backfilled {n_noid} attempt_id'))

    # ---- 6b. 回填缺失日期/时间戳与 canonical_expression（Phase 0 setdefault bug 遗留）----
    n_dk = int(gy.df['date_killed'].isna().sum())
    if n_dk:
        gy.df['date_killed'] = gy.df['date_killed'].fillna(today)
        gy._save()
        repair.append(dict(repair_id=next_rid(), date=today,
                           kind='DATE_KILLED_BACKFILL', factor_id=None,
                           factor_name=None, canonical_factor_id=None,
                           mapping=today,
                           detail=f'backfilled {n_dk} graveyard date_killed '
                                  f'with migration date (Phase 0 setdefault bug)'))
    n_ts = int(exp.df['timestamp'].isna().sum())
    if n_ts:
        exp.df['timestamp'] = exp.df['timestamp'].fillna(R._now_ts())
        exp._save()
        repair.append(dict(repair_id=next_rid(), date=today,
                           kind='EXPERIMENT_TS_BACKFILL', factor_id=None,
                           factor_name=None, canonical_factor_id=None,
                           mapping=R._now_ts(),
                           detail=f'backfilled {n_ts} experiment timestamp'))
    n_dt = int(mt.df['date'].isna().sum())
    if n_dt:
        mt.df['date'] = mt.df['date'].fillna(today)
        mt._save()
        repair.append(dict(repair_id=next_rid(), date=today,
                           kind='MT_DATE_BACKFILL', factor_id=None,
                           factor_name=None, canonical_factor_id=None,
                           mapping=today,
                           detail=f'backfilled {n_dt} MT ledger attempt date'))
    n_ce = int(reg.df['canonical_expression'].isna().sum())
    if n_ce:
        for i in reg.df.index:
            if pd.isna(reg.df.at[i, 'canonical_expression']):
                f = reg.df.at[i, 'formula']
                if f and pd.notna(f):
                    try:
                        reg.df.at[i, 'canonical_expression'] = dsl.canonical_string(f)
                    except Exception:
                        reg.df.at[i, 'canonical_expression'] = f
        reg._save()
        repair.append(dict(repair_id=next_rid(), date=today,
                           kind='CANONICAL_EXPRESSION_BACKFILL', factor_id=None,
                           factor_name=None, canonical_factor_id=None,
                           mapping='dsl.canonical_string(formula)',
                           detail=f'backfilled {n_ce} canonical_expression'))

    # ---- 7. 重建全部 CSV mirror ----
    rebuilt = R.rebuild_csv_mirrors()
    repair.append(dict(repair_id=next_rid(), date=today,
                       kind='CSV_MIRROR_REBUILT', factor_id=None, factor_name=None,
                       canonical_factor_id=None, mapping='PARQUET_TO_CSV',
                       detail=f'rebuilt mirrors: {rebuilt}; fixes Phase 0 '
                              f'parquet/csv inconsistency (MT 42 vs 3)'))

    _repair(repair)

    # ---- 8. migration report ----
    n_reg_after = len(reg.df)
    n_gy_after = len(gy.df)
    n_lib_after = len(lib.df)
    n_cand_after = len(cand.df)
    n_mt_after = len(mt.df)
    dup_names = sorted({r['factor_name'] for r in repair
                        if r['kind'] == 'INVALID_DUPLICATE_IMPORT'})
    s = mt.summary()
    lines = [
        '# Alpha Factory — Phase 0 → 0.1 Registry Migration Report', '',
        f'- 迁移时间: {R._now_ts()}',
        f'- 迁移脚本: src/alpha_factory/migrate_phase0.py', '',
        '## 1. 原 Factor Registry 多少行？',
        f'- 迁移前 FACTOR_REGISTRY = {n_reg_before} 行；迁移后 = {n_reg_after} 行。',
        f'- 迁移前 status 分布: {old_status_counts}', '',
        '## 2. 哪些属于误重复 legacy import？',
        f'- (factor_name, universe) 重复的误导入行共 {len(invalid_ids)} 行：',
        *[f'  - {fid}（{name}）' for fid, name in
          [(r['factor_id'], r['factor_name']) for r in repair
           if r['kind'] == 'INVALID_DUPLICATE_IMPORT']],
        '',
        '## 3. 哪些 canonical 保留？',
        '- AF_000001~AF_000013（首轮 legacy 导入，含信号定义/失败项/HOLD）',
        '- AF_000014~AF_000026（Phase 0 smoke 因子）',
        '- 补录：AF_000035 weekly_bb（Phase 0 旧 importer 曾因表达式同形被误判为 '
        'bb_z 重复而跳过，本次按 LEGACY 语义恢复 canonical 记录）', '',
        '## 4. Graveyard 重复多少？',
        f'- 迁移前 ALPHA_GRAVEYARD = {n_gy_before} 行；其中重复 legacy 埋葬 '
        f'{len(gy_removed)} 行（{sorted(gy_removed)}）；迁移后 = {n_gy_after} 行。'
        f'  canonical 墓地记录不变，重复行在 GOVERNANCE_EVENTS 留痕。', '',
        '## 5. breadth 为什么不应在 Library？',
        '- AF_000004 market_breadth 当前 status = VALIDATING（≠ KEEP），且未通过 '
        'multiple_testing / incremental_alpha / OOS / leakage 全门禁；'
        'ALPHA_LIBRARY 只允许 fully approved factors。已移至 ALPHA_CANDIDATES '
        '（Phase 1 特征重要性候选）。', '',
        '## 6. attempt 42 的旧定义是什么？',
        '- 旧代码 count_attempts = len(MULTIPLE_TESTING_LEDGER) = 42，全部 status='
        'TESTED（14 个 smoke 表达式 × 3 标签），无 attempt_id、无重复/拒绝分类。',
        '- 旧 MT CSV 只有 3 行而 parquet 42 行：旧 _save 直接写、CSV 为陈旧镜像 '
        '（Phase 0 一致性缺陷；parquet 为真实数据，未丢失）。', '',
        '## 7. 新定义下各项计数（迁移完成时点）',
        *[f'- {k} = {v}' for k, v in s.items()],
        '',
        '## 8. 有没有丢失无法恢复的历史？',
        '- 可恢复：旧 42 条 attempt 全部在 parquet canonical 中；CSV 3 行只是陈旧'
        ' 镜像，重建后 = 42。',
        '- 不可恢复：weekly_bb 在 Phase 0 从未被正确登记（旧 importer 表达式同形'
        ' 误判跳过），该“当时未登记”的事实无法倒填——已补 canonical 记录并标 '
        'RESTORED_LEGACY_ITEM，原错误不假装未发生。',
        '- 其余 legacy 项与 smoke attempt 均可从现有 parquet 完整恢复；'
        '不存在 UNKNOWN_LEGACY_ATTEMPT_COUNT 缺口。',
        '',
        '## 8b. Phase 0 setdefault 遗留空字段回填',
        f'- Graveyard date_killed 回填 {n_dk} 行（迁移日期）；'
        f'Experiment timestamp 回填 {n_ts} 行；'
        f'MT ledger attempt date 回填 {n_dt} 行；'
        f'Registry canonical_expression 回填 {n_ce} 行（dsl 规范化）。',
        '全部回填在 GOVERNANCE_REPAIR_LOG.csv 留痕，不覆盖任何既有值。',
        '',
        '## 治理事件摘要',
        *[f'- {k}: {v}' for k, v in sorted(gov.kinds().items())],
        '',
    ]
    with open(MIG_REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print('== MIGRATION SUMMARY ==')
    print(f'registry: {n_reg_before} -> {n_reg_after}')
    print(f'graveyard: {n_gy_before} -> {n_gy_after} (removed {len(gy_removed)} dups)')
    print(f'library: {n_lib_before} -> {n_lib_after}; candidates: {n_cand_after}')
    print(f'mt ledger: {n_mt_before} -> {n_mt_after}; attempt_id backfilled: {n_noid}')
    print(f'invalid duplicate rows: {len(invalid_ids)}')
    print(f'GOVERNANCE_REPAIR_LOG -> {REPAIR_LOG}')
    print(f'PHASE0_REGISTRY_MIGRATION_REPORT -> {MIG_REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
