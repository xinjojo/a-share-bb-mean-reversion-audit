"""TUSHARE INCREMENTAL UPDATER — EE15 前瞻增量数据更新器（2026-08-26 起）。

规则：
1. token 只从环境变量 TUSHARE_TOKEN 读取，绝不写入任何文件（与 data/raw/download_dividend.py 同约定）。
2. 只拉 2026-08-26 及以后（前瞻增量区）。2026-08-25 及以前 = 冻结历史，默认不覆盖；
   若 Tushare 返回的历史值与本地不同 → 写入 forward_data_revision_alert.csv，不自动覆盖。
3. 每次运行自动判断本地数据最新日期，只拉缺失交易日。
4. 输出目录：data/forward_incremental/（不动冻结历史数据）。

至少更新：
- A股 daily（open/high/low/close/pre_close/change/pct_chg/vol/amount）
- adj_factor
- stock_basic（上市/退市状态、list_date、名称）
- namechange（ST/名称变更，PIT 可交易状态）
- trade_cal（交易日历增量）
- ETF 513500 fund_daily + unit_nav
- dividend（分红送转除权除息）
"""
import os, sys, glob, json, time
import numpy as np, pandas as pd

GITHUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWCHAT = os.path.dirname(os.path.dirname(GITHUB))
DATA = os.path.join(NEWCHAT, 'data')
RAW = os.path.join(DATA, 'raw')
INC = os.path.join(DATA, 'forward_incremental')
ALERT_PATH = os.path.join(INC, 'forward_data_revision_alert.csv')

FROZEN_END = '20260825'          # 冻结历史末日（不覆盖）
FROZEN_END_TS = pd.Timestamp('2026-08-25')

DAILY_COLS = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close',
              'change', 'pct_chg', 'vol', 'amount']
ETF_TS = '513500.SH'


def get_token():
    tok = os.environ.get('TUSHARE_TOKEN', '')
    if not tok:
        print('NO TUSHARE_TOKEN: 环境变量未设置。', file=sys.stderr)
        print('请先执行 export TUSHARE_TOKEN=<你的tushare token>（不写入任何文件）。', file=sys.stderr)
        return None
    return tok


def load_local_combined_incremental():
    """本地 combined_daily.parquet 中 >2026-08-25 的已有增量（用于与 Tushare 对比/兜底）。"""
    df = pd.read_parquet(os.path.join(DATA, 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    return df[df['date'] > FROZEN_END_TS]


def revision_alerts(new_df, local_df, key, fields, source_label):
    """Tushare 新值与本地已有值对比，不同 → 写修订告警（不自动覆盖）。返回告警行数。"""
    if new_df is None or new_df.empty or local_df is None or local_df.empty:
        return 0
    merged = new_df.merge(local_df, on=key, suffixes=('_new', '_old'), how='inner')
    rows = []
    for f in fields:
        cn, co = f'{f}_new', f'{f}_old'
        if cn not in merged.columns or co not in merged.columns:
            continue
        diff = merged[merged[cn].astype(str) != merged[co].astype(str)]
        for _, r in diff.iterrows():
            rows.append(dict(date=r[key[1]] if len(key) > 1 else str(r[key[0]]),
                             ts_code=r[key[0]], field=f,
                             old_value=r[co], new_value=r[cn], source=source_label))
    if rows:
        alert = pd.DataFrame(rows)
        if os.path.exists(ALERT_PATH):
            old = pd.read_csv(ALERT_PATH, dtype=str)
            alert = pd.concat([old, alert.astype(str)], ignore_index=True).drop_duplicates()
        os.makedirs(INC, exist_ok=True)
        alert.to_csv(ALERT_PATH, index=False)
        print(f'  [WARN] {source_label}: {len(rows)} 处与本地已有值不同 → {ALERT_PATH}')
    return len(rows)


def fetch_trade_cal(pro, start=FROZEN_END, end='20261231'):
    """拉取交易所交易日历（增量）。"""
    df = pro.trade_cal(exchange='SSE', start_date=start, end_date=end)
    if df is None or df.empty:
        return pd.DataFrame(columns=['date'])
    out = df[df['is_open'] == 1]['cal_date'].astype(str).str[:8]
    return pd.DataFrame({'date': pd.to_datetime(out)})


def fetch_daily_adj(pro, trade_date):
    """拉取单日全市场 daily + adj_factor，返回 (daily, adj)。"""
    d = None
    a = None
    for attempt in range(3):
        try:
            d = pro.daily(trade_date=trade_date)
            a = pro.adj_factor(trade_date=trade_date)
            break
        except Exception as exc:
            print(f'    [retry {attempt + 1}] {trade_date}: {exc}')
            time.sleep(2)
    return d, a


def fetch_dividend_by_exdate(pro, ex_date):
    """拉取某除权除息日全市场 dividend。接口可能限流/无数据，失败返回空。"""
    try:
        return pro.dividend(ex_date=ex_date)
    except Exception:
        return pd.DataFrame()


def update_all(pro, force_from=None):
    """主流程。force_from: 强制从某日期开始（默认自动取本地最新+1 交易日）。返回 (拉取交易日数, 最新交易日)。"""
    os.makedirs(INC, exist_ok=True)
    # 1) 交易日历
    cal = fetch_trade_cal(pro)
    if cal.empty:
        print('  [ERR] trade_cal 拉取失败')
        return 0, None
    cal = cal.sort_values('date')
    # 本地已有增量（daily_{date}.parquet 文件）
    have = set()
    for f in glob.glob(os.path.join(INC, 'daily_*.parquet')):
        have.add(os.path.basename(f)[6:14])
    # 起点：force_from 或 本地已有最大+1 交易日，或 2026-08-26
    start = None
    if force_from:
        start = force_from
    else:
        pend = [d for d in cal['date'] if d > FROZEN_END_TS]
        for d in pend:
            ds = d.strftime('%Y%m%d')
            if ds not in have:
                start = ds
                break
    if start is None:
        latest = cal[cal['date'] > FROZEN_END_TS]
        if latest.empty:
            return 0, FROZEN_END_TS
        return 0, latest['date'].max()
    pending = [d for d in cal['date'] if FROZEN_END_TS < d <= pd.Timestamp('2026-12-31') and
               d.strftime('%Y%m%d') >= start]
    print(f'  待拉交易日: {len(pending)} 个（{pending[0].date()} .. {pending[-1].date()}）')

    local_inc = load_local_combined_incremental()
    n_ok = 0
    for d in pending:
        ds = d.strftime('%Y%m%d')
        f_daily = os.path.join(INC, f'daily_{ds}.parquet')
        f_adj = os.path.join(INC, f'adj_{ds}.parquet')
        if os.path.exists(f_daily) and os.path.exists(f_adj):
            n_ok += 1
            continue
        daily, adj = fetch_daily_adj(pro, ds)
        if daily is None or daily.empty:
            print(f'  [skip] {ds} daily 空（可能休市/数据未出）')
            continue
        daily.to_parquet(f_daily, index=False)
        if adj is not None and not adj.empty:
            adj.to_parquet(f_adj, index=False)
        # 修订告警：与本地 combined 增量对比（仅对比存在字段）
        if local_inc is not None and not local_inc.empty:
            loc = local_inc[local_inc['date'] == d]
            if not loc.empty:
                rv = daily.merge(loc, left_on=['ts_code', 'trade_date'], right_on=['ts_code', 'date'],
                                 suffixes=('_new', '_old'), how='inner')
                if len(rv):
                    for f in ('open', 'high', 'low', 'close', 'pre_close', 'amount'):
                        if f'_new' in rv.columns and f'_old' in rv.columns:
                            diff = rv[rv[f'{f}_new'].astype(float) != rv[f'{f}_old'].astype(float)]
                            if len(diff):
                                rows = [dict(date=ds, ts_code=r['ts_code'], field=f,
                                             old_value=r[f'{f}_old'], new_value=r[f'{f}_new'],
                                             source='tushare_daily_vs_local_combined')
                                        for _, r in diff.iterrows()]
                                alert = pd.DataFrame(rows)
                                if os.path.exists(ALERT_PATH):
                                    old = pd.read_csv(ALERT_PATH, dtype=str)
                                    alert = pd.concat([old, alert.astype(str)], ignore_index=True).drop_duplicates()
                                alert.to_csv(ALERT_PATH, index=False)
                                print(f'  [WARN] {ds}: daily {f} 与本地 combined 有 {len(diff)} 处不同 → 修订告警（未覆盖本地）')
        # 分红（除权除息日）
        dv = fetch_dividend_by_exdate(pro, ds)
        if dv is not None and not dv.empty:
            f_dv = os.path.join(INC, f'dividend_{ds}.parquet')
            dv.to_parquet(f_dv, index=False)
        n_ok += 1
        print(f'  [OK] {ds} daily/adj 已拉取')
        time.sleep(0.35)  # 限流保护
    # 2) stock_basic 全量刷新（增量覆盖：只写新文件，不动旧 raw）
    try:
        sb = pro.stock_basic(exchange='', list_status='L')
        if sb is not None and not sb.empty:
            sb.to_parquet(os.path.join(INC, 'stock_basic_forward.parquet'), index=False)
            print(f'  [OK] stock_basic 全量刷新 {len(sb)} 只（上市状态）')
    except Exception as exc:
        print(f'  [warn] stock_basic 拉取失败: {exc}')
    # 3) namechange 全量刷新（PIT ST/名称）
    try:
        nc = pro.namechange()
        if nc is not None and not nc.empty:
            nc.to_parquet(os.path.join(INC, 'namechange_forward.parquet'), index=False)
            print(f'  [OK] namechange 全量刷新 {len(nc)} 条')
    except Exception as exc:
        print(f'  [warn] namechange 拉取失败: {exc}')
    # 4) ETF 513500 fund_daily + fund_nav
    try:
        fd = pro.fund_daily(ts_code=ETF_TS, start_date='20260826', end_date='20261231')
        fn = None
        try:
            fn = pro.fund_nav(ts_code=ETF_TS, start_date='20260826', end_date='20261231')
        except Exception:
            pass
        if fd is not None and not fd.empty:
            fd.to_parquet(os.path.join(INC, 'etf_513500_forward.parquet'), index=False)
            if fn is not None and not fn.empty:
                fd = fd.merge(fn[['nav_date', 'unit_nav', 'accum_nav']],
                              left_on='trade_date', right_on='nav_date', how='left')
            fd.to_parquet(os.path.join(INC, 'etf_513500_forward.parquet'), index=False)
            print(f'  [OK] ETF 513500 fund_daily 刷新 {len(fd)} 行（至 {fd["trade_date"].max()}）')
    except Exception as exc:
        print(f'  [warn] ETF 拉取失败: {exc}')

    latest = pending[-1] if pending else None
    return n_ok, latest


def main():
    print('== TUSHARE INCREMENTAL UPDATER ==')
    tok = get_token()
    if tok is None:
        sys.exit(2)
    import tushare as ts
    pro = ts.pro_api(tok)
    n, latest = update_all(pro)
    print(f'== DONE: 拉取 {n} 个交易日数据，最新 = {latest} ==')


if __name__ == '__main__':
    main()
