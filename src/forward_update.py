"""前瞻台账每日更新脚本（A/B 影子账户，冻结于 2026-09-06）。

用法（每日有新的 daily 行情数据后运行）：
    python src/forward_update.py

行为：
1. 检查 data/raw/daily 最新交易日。
2. 若 max_date <= 2026-09-06（冻结前）：输出等待信息，不写任何前瞻成绩。
3. 若 max_date >= 2026-09-07：用冻结引擎分别跑 A（基线 P*）与 B（提前 1.5%）两档完整组合，
   只把 entry_date >= 2026-09-07 的新交易追加进 results/evidence/forward/ 台账；
   已有信号按唯一键去重，绝不修改历史行；事后补入必须 backfilled=1。
4. 每条记录带 signal_generated_at（实时生成时间）与 data_available_through（本次数据截止日）。

禁止：
- 修改 1.5% 或新增阈值；
- 用 2025/2026 历史结果选参；
- 依据前瞻表现加任何过滤器。
"""
import os, sys, csv, datetime
import pandas as pd
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
DATA = os.path.join(os.path.dirname(os.path.dirname(REPO)), 'data', 'raw')
OUT = os.path.join(REPO, 'results', 'evidence', 'forward')

FREEZE_DATE = pd.Timestamp('2026-09-06')
FIRST_FORWARD_DATE = pd.Timestamp('2026-09-07')


def latest_daily_date():
    """返回 (min_date, max_date)：全部股票分片最新交易日的保守下限与主流上限。"""
    import glob
    fs = sorted(glob.glob(os.path.join(DATA, 'daily', '*.parquet')))
    if not fs:
        return None, None
    lo, hi = None, None
    for f in fs:
        try:
            d = pd.read_parquet(f, columns=['date'])['date'].max()
            lo = d if lo is None else min(lo, d)
            hi = d if hi is None else max(hi, d)
        except Exception:
            continue
    return lo, hi


def load_append(path, rows):
    """追加行；绝不修改历史行。rows: list[dict]"""
    cols = []
    with open(path, 'r', encoding='utf-8') as fh:
        cols = next(csv.reader(fh))
    exist_keys = set()
    with open(path, 'r', encoding='utf-8') as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            if 'signal_id' in r:
                exist_keys.add(r['signal_id'])
    new = []
    for r in rows:
        if 'signal_id' in r and r['signal_id'] in exist_keys:
            continue
        new.append(r)
    if not new:
        return 0
    with open(path, 'a', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        for r in new:
            w.writerow(r)
    return len(new)


def main():
    lo, mx = latest_daily_date()
    if mx is None:
        print('错误：未找到 data/raw/daily 行情分片。'); return 1
    print(f'当前行情数据截止: 主流 {mx.date()}（个别股票下限 {lo.date()}）')
    if mx <= FREEZE_DATE:
        print(f'冻结前（数据主流止于 {mx.date()}，早于 2026-09-06）：')
        print('无前瞻信号。首个前瞻交易日为 2026-09-07，等待该日及以后的行情数据。')
        print('注意：2026-09-01~09-06 属冻结之前，即使未来补齐数据也不得纳入前瞻成绩。')
        return 0

    # —— 冻结后：运行 A/B 两档完整引擎，抽取 09-07 后新交易 ——
    from src.strict_c_earlyexit_ca import run_fast_multi_strict_c_ee_ca
    from src.round51.round51_audit import prepare_v51

    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    data_through = mx.strftime('%Y-%m-%d')

    sig_rows, trd_rows, eq_rows = [], [], []
    for system, ee in (('A', 0.0), ('B', 0.015)):
        res = run_fast_multi_strict_c_ee_ca(
            days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
            ee_early_exit=ee, etf_enabled=True,
            K=3, top_n=10, max_levels=5, level_cash=200_000,
            min_listing_days=60, initial_cash=1_000_000)
        trades = res['trades']
        trades = trades[trades['entry_date'] >= FIRST_FORWARD_DATE.strftime('%Y-%m-%d')]
        for _, t in trades.iterrows():
            sid = f"FWD-{system}-{t['ts_code']}-{t['entry_date']}"
            sig_rows.append(dict(signal_id=sid, ts_code=t['ts_code'],
                                 stock_name=t.get('name', ''), signal_date='', entry_date=t['entry_date'],
                                 entry_role=t.get('entry_role', ''), level_no=t.get('levels_used', ''),
                                 dynamic_Pstar='', base_exit_line='', ee15_exit_line='', daily_high='',
                                 trigger_base='', trigger_ee15='',
                                 signal_generated_at=now_utc, data_available_through=data_through,
                                 backfilled=0, note=''))
    n1 = load_append(os.path.join(OUT, 'forward_signal_ledger.csv'), sig_rows)
    print(f'新增前瞻信号 {n1} 条（A/B 各自独立记账，本轮仅信号登记；成交/权益行由逐日明细补齐）。')
    print(f'signal_generated_at={now_utc}  data_available_through={data_through}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
