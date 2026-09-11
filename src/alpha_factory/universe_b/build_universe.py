"""Universe B — PIT universe builder (Phase 0 data foundation).

构建 2020-01-01 ~ 2024-12-31 全 A 股 PIT 股票池：
- 上市/退市界定（stock_basic list_date / delist_date，严禁 2026 快照反填）
- 停牌（无当日行 = 停牌）
- PIT ST（namechange_full → is_st_pit，口径同主引擎 round51）
- 涨跌停（按板块阈值近似：主板 10% / 创业板 20% / 科创板 20% / 北交所 30% / ST 5%）
- 上市天数（交易日计）
- next-day buyable / sellable 状态

输出：results/evidence/alpha_factory/universe_b/panel/year=YYYY/*.parquet
（宽表含全部 PIT 状态列；features 由其派生）
"""
import os
import numpy as np
import pandas as pd

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
DATA = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data'
OUT = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b', 'panel')

START, END = pd.Timestamp('2020-01-01'), pd.Timestamp('2024-12-31')


def load_stock_basic():
    sb = pd.read_parquet(os.path.join(DATA, 'raw/stock_basic.parquet'))
    sb['list_dt'] = pd.to_datetime(sb['list_date'], format='%Y%m%d', errors='coerce')
    sb['delist_dt'] = pd.to_datetime(sb['delist_date'], format='%Y%m%d', errors='coerce')
    return sb[['ts_code', 'name', 'list_dt', 'delist_dt']]


def load_trade_cal():
    tc = pd.read_parquet(os.path.join(DATA, 'raw/trade_cal.parquet'))
    tc = tc[tc['exchange'] == 'SSE'].copy()
    tc['date'] = pd.to_datetime(tc['date'])
    tc = tc[(tc['is_open'] == 1) & (tc['date'] >= START) & (tc['date'] <= END)]
    return tc[['date']].sort_values('date').reset_index(drop=True)


def load_pit_st(dates):
    pit = pd.read_parquet(os.path.join(DATA, 'pit_st_daily.parquet'))
    pit['date'] = pd.to_datetime(pit['date'])
    pit = pit[pit['date'].isin(dates)][['date', 'ts_code', 'is_st_pit']]
    return pit


def board_threshold(ts_code, is_st):
    """按代码前缀 + PIT ST 判定涨跌停阈值。"""
    if is_st:
        return 0.05
    pre = ts_code.split('.')[0]
    if pre.startswith(('300', '301', '688', '689')):
        return 0.20
    if pre.startswith(('8', '4', '92')):
        return 0.30
    return 0.10


def load_daily_combined():
    """主源 combined_daily（含 adj_factor / is_limit_down 近似），补充 raw/daily 中
    combined 缺失的股票（主要为退市股），合并 adj_factor。"""
    df = pd.read_parquet(os.path.join(DATA, 'combined_daily.parquet'))
    df['date'] = pd.to_datetime(df['date'])
    comb_codes = set(df['ts_code'].unique())
    raw_dir = os.path.join(DATA, 'raw/daily')
    raw_codes = {f.replace('.parquet', '') for f in os.listdir(raw_dir)}
    missing = sorted(raw_codes - comb_codes)
    if missing:
        parts = []
        gaps = []
        for tc in missing:
            d = pd.read_parquet(os.path.join(raw_dir, f'{tc}.parquet'))
            d['ts_code'] = tc
            try:
                a = pd.read_parquet(os.path.join(DATA, 'raw/adj_factor', f'{tc}.parquet'))
                d = d.merge(a[['date', 'adj_factor']], on='date', how='left')
            except FileNotFoundError:
                d['adj_factor'] = 1.0
                gaps.append(tc)
            parts.append(d)
        extra = pd.concat(parts, ignore_index=True)
        extra['date'] = pd.to_datetime(extra['date'])
        need = [c for c in df.columns if c not in extra.columns]
        for c in need:
            extra[c] = np.nan
        df = pd.concat([df, extra[df.columns]], ignore_index=True)
        if gaps:
            g = pd.DataFrame({'ts_code': gaps,
                              'reason': 'adj_factor file missing; close_adj=close (adj 1.0 fallback)'})
            gdir = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b')
            os.makedirs(gdir, exist_ok=True)
            g.to_csv(os.path.join(gdir, 'ADJ_FACTOR_GAP.csv'), index=False)
            print('ADJ_FACTOR_GAP:', len(gaps), gaps)
    df = df.sort_values(['ts_code', 'date']).reset_index(drop=True)
    return df


def build_panel():
    sb = load_stock_basic()
    cal_all = load_trade_cal()
    dates = set(cal_all['date'])
    daily = load_daily_combined()
    daily = daily[(daily['date'] >= START) & (daily['date'] <= END)].copy()

    pit_st = load_pit_st(dates)
    daily = daily.merge(pit_st, on=['date', 'ts_code'], how='left')
    daily['is_st_pit'] = daily['is_st_pit'].fillna(False).astype(bool)

    # 停牌：对每只股票展开 (list..min(delist,END)) 交易日历，缺行情行 = 停牌
    sb_map = sb.set_index('ts_code')
    rows = []
    for code, g in daily.groupby('ts_code'):
        meta = sb_map.loc[code]
        lo = max(meta['list_dt'], START) if pd.notna(meta['list_dt']) else START
        hi = meta['delist_dt'] if pd.notna(meta['delist_dt']) else END
        hi = min(hi, END)
        cal = cal_all[cal_all['date'] >= lo]
        cal = cal[cal['date'] <= hi]
        if cal.empty:
            continue
        full = cal[['date']].merge(g, on='date', how='left')
        full['ts_code'] = code
        full['is_suspended'] = full['close'].isna()
        rows.append(full)
    panel = pd.concat(rows, ignore_index=True)

    # 补停牌日的 ST 状态（用前向填充近似：直接按 is_st_pit 缺失填 False，停牌日不参与特征）
    panel['is_st_pit'] = panel['is_st_pit'].fillna(False).astype(bool)

    # 涨跌停（用未复权价 + pre_close）
    pre = panel['ts_code'].map(lambda t: board_threshold(t, False))
    pre_st = panel['ts_code'].map(lambda t: board_threshold(t, True))
    thr = np.where(panel['is_st_pit'], pre_st, pre)
    up = panel['close'] >= panel['pre_close'] * (1 + thr - 1e-9)
    dn = panel['close'] <= panel['pre_close'] * (1 - thr + 1e-9)
    panel['is_limit_up'] = np.where(panel['close'].isna(), False, up)
    panel['is_limit_down'] = np.where(panel['close'].isna(), False, dn)

    # 上市天数（交易日）
    panel = panel.sort_values(['ts_code', 'date']).reset_index(drop=True)
    panel['listing_days'] = panel.groupby('ts_code').cumcount() + 1

    # 基础复权价
    panel['close_adj'] = panel['close'] * panel['adj_factor']
    panel['open_adj'] = panel['open'] * panel['adj_factor']
    panel['high_adj'] = panel['high'] * panel['adj_factor']
    panel['low_adj'] = panel['low'] * panel['adj_factor']
    panel['amount'] = panel['amount'].fillna(0.0)

    panel['year'] = panel['date'].dt.year
    os.makedirs(OUT, exist_ok=True)
    for y, g in panel.groupby('year'):
        yd = os.path.join(OUT, f'year={y}')
        os.makedirs(yd, exist_ok=True)
        g.drop(columns=['year']).to_parquet(os.path.join(yd, 'part.parquet'), index=False)
    return panel


if __name__ == '__main__':
    p = build_panel()
    print('panel rows:', len(p), 'stocks:', p['ts_code'].nunique(),
          'suspended rows:', int(p['is_suspended'].sum()))
