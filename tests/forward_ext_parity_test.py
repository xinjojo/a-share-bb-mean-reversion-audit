"""FORWARD EXT DATA PARITY TEST — P0-2 扩展加载层 vs prepare_v51 冻结段逐字段一致。

验证：扩展层（_build_frame + _df_to_D，combined_daily ≤2026-08-25 同公式重建）
对冻结段随机 ≥20 个 2026-07~08 交易日的 D，与 prepare_v51 原样输出逐字段机器断言一致。
通过后才允许扩展层用于 >2026-08-25 真实新增行情。
"""
import os, sys, json
import numpy as np, pandas as pd

GITHUB = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
NEWCHAT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, GITHUB)
sys.path.insert(0, NEWCHAT)
sys.path.insert(0, os.path.join(GITHUB, 'src'))

from round51_audit import prepare_v51
from forward_ext_data import parity_check, build_ext_days, merge_extended, FROZEN_END

PASS, FAIL = 0, 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  [PASS] {name} {detail}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name} {detail}')


if __name__ == '__main__':
    print('== EXT-PARITY: 扩展层 vs prepare_v51 冻结段逐字段一致 ==')
    print('  加载 prepare_v51（冻结段原样）...')
    pret = prepare_v51(limit_down_mode='correct', st_mode='pit')
    days_f, D_f, etf_idx_f, etf_px_f, etf_open_f, etf_nav_f, fei_f, off_f = pret
    print(f'  冻结段交易日 = {len(days_f)}，末日 = {days_f[-1].date()}')

    print('  扩展层代码路径重建冻结段样本日期并逐字段对比 ...')
    p = parity_check(pret, n_sample=24, seed=0)
    check('parity: 24 个 2026-07~08 样本日期全部计算成功', len(p['sample_dates']) >= 20,
          f'n={len(p["sample_dates"])}')
    check('parity: ts 顺序完全一致（字母序）', p['ts_order_ok'])
    check('parity: 全部数值字段 max_abs_diff = 0.0', p['max_abs_diff'] == 0.0,
          f'max_abs_diff={p["max_abs_diff"]}')
    check('parity: 无字段不一致计数', not p['field_mismatch_counts'],
          f'mismatch={p["field_mismatch_counts"]}')
    if p['per_field']:
        print('  per_field max_abs_diff:', json.dumps(p['per_field'], ensure_ascii=False))

    print('  扩展段加载（>2026-08-25 真实新增行情）...')
    ext_days, ext_D, fei_ext, cal_len, ext_etf = build_ext_days()
    check('EXT: 扩展段非空（combined_daily 已含 08-26~08-31）', len(ext_days) > 0,
          f'n_ext_days={len(ext_days)}')
    if ext_days:
        check('EXT: 扩展段日期全部 > 冻结末日', all(d > FROZEN_END for d in ext_days),
              f'min={ext_days[0].date()}')
        check('EXT: 扩展段字段齐全（含 bb_upper_prev/limit/adj）',
              all(k in ext_D[ext_days[0]] for k in ('ts', 'close_adj', 'bb_lower', 'bb_upper',
                                                    'bb_mid', 'limit_up_px', 'limit_down_px',
                                                    'is_st', 'adj', 'pos')))
        check('EXT: ETF 扩展非空（08-26~08-31）', ext_etf is not None and len(ext_etf['px']) > 0,
              f'n_etf={len(ext_etf["px"]) if ext_etf else 0}')
        print(f'  扩展段日期: {ext_days[0].date()} .. {ext_days[-1].date()}')

    print('  合并后全数据集（冻结段 + 扩展段）...')
    days, D, etf_idx, etf_px, etf_open, etf_nav, fei, off = merge_extended(pret)
    check('MERGE: 合并后末日 = 扩展段末日', days[-1] == (ext_days[-1] if ext_days else days_f[-1]),
          f'last={days[-1].date()}')
    check('MERGE: 冻结段结果完全不变（D 冻结日引用一致）',
          all(days_f[k] == days[k] for k in range(len(days_f))))
    check('MERGE: 冻结段 D 未被改写', all(D_f[d] is D[d] for d in days_f[:5]))

    print(f'\n== RESULT: PASS={PASS} FAIL={FAIL} ==')
    sys.exit(0 if FAIL == 0 else 1)
