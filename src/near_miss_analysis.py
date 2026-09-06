"""NEAR-MISS FORWARD OUTCOME — 任务B: "差一点没卖"以后发生了什么
对每个未触发持仓日 (high < threshold), 若 gap_pct = (P*-High)/P* 很小:
  独立复算该股票后续 20 个有效交易日每日动态 P* (19日滚动 close_adj + analytic root + tick),
  记录: 后续是否触发 / 何时触发 / 触发收益 vs 当日提前卖收益 / 后续 max high / min low / close ret /
        5/10/20日深跌标记 / 最终该笔交易实际结果。
"""
import sys, os
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'audit_package', 'github_repo', 'src'))
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE
from run_strict_c_math import analytic_Pstar

OUT = os.path.join(ROOT, 'audit_package', 'github_repo', 'results', 'evidence', 'ee_audit')
days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
    limit_down_mode='correct', st_mode='pit')
day_idx = {d: i for i, d in enumerate(days)}

# 每只股票有效交易日 (有数据的日期)
stock_days = {}
for i, d in enumerate(days):
    for tc in D[d]['ts']:
        stock_days.setdefault(tc, []).append(i)

def pstar_for(ts, day_i, use_tick=True):
    """计算 day_i (含) 的动态 P*. 窗口 = day_i 前19个该股有效交易日 (不含自身) + 自身 close_adj"""
    idxs = stock_days.get(ts, [])
    pos = day_i  # 该股在全局索引? 需要 map
    return None

# 预先构建: tc -> list of global day indices (有序)
# 对给定全局交易日 gi, 该股当日若有效, 计算窗口 = 该日及前19个有效日 close_adj
tc_days = {}
for i, d in enumerate(days):
    for tc in D[d]['ts']:
        tc_days.setdefault(tc, []).append(i)

def calc_pstar(ts, gi):
    """gi 为全局交易日索引 (该日该股有数据). 返回 (Pstar_adj, Pstar_raw, threshold_raw, 窗口长度)"""
    arr = tc_days[ts]
    k = np.searchsorted(arr, gi)
    if k < 19:
        return np.nan, np.nan, np.nan, k
    win = []
    for j in range(k - 19, k + 1):
        dj = days[arr[j]]
        posj = D[dj]['pos'][ts]
        win.append(float(D[dj]['close_adj'][posj]))
    x = np.array(win[-19:], dtype=float)  # 前19个 (不含当日)
    P_adj = analytic_Pstar(x)
    if P_adj is None or not np.isfinite(P_adj):
        return np.nan, np.nan, np.nan, 19
    dj = days[gi]
    adjT = float(D[dj]['adj'][D[dj]['pos'][ts]])
    P_raw = P_adj / adjT
    thr = np.ceil(P_raw / 0.01) * 0.01
    return float(P_adj), float(P_raw), float(thr), 19

# 读取持仓日距离表
dp = pd.read_csv(os.path.join(OUT, 'all_holding_days_pstar_distance.csv'))
dp['date'] = dp['date'].astype(str)
# 未触发日
unt = dp[~dp['triggered']].copy()
print('total holding-days:', len(dp), 'untouched days:', len(unt))
print('untouched gap_pct_legal stats:', unt['pct_legal'].describe().to_string())
# 分布统计
bins = [0, 0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.05, 1.0]
labels = ['0~0.1%', '0.1~0.2%', '0.2~0.3%', '0.3~0.5%', '0.5~0.75%', '0.75~1%', '1~1.5%', '1.5~2%', '2~3%', '3~5%', '>5%']
unt['b'] = pd.cut(unt['pct_legal'], bins=bins, labels=labels, right=False)
dist = unt.groupby('b', observed=False).agg(days=('pct_legal', 'size'),
                                            pct_days=('pct_legal', lambda x: len(x) / len(unt) * 100))
dist = dist.reindex(labels).reset_index()
dist.columns = ['gap_bucket', 'holding_days', 'pct_of_untouched']
# 涉及交易数
tr_map = dp[['ts_code', 'entry_date']].drop_duplicates()
unt2 = unt.merge(tr_map, on=['ts_code', 'entry_date'])
trades_per_bucket = unt2.groupby('b', observed=False)['entry_date'].nunique().reindex(labels).reset_index()
trades_per_bucket.columns = ['gap_bucket', 'trades_covered']
dist = dist.merge(trades_per_bucket, on='gap_bucket')
dist.to_csv(os.path.join(OUT, 'pstar_distance_distribution.csv'), index=False)
print('\n=== pstar_distance_distribution ===')
print(dist.to_string(index=False))
# 基础分布统计
stat = unt['pct_legal'].describe(percentiles=[.1, .25, .5, .75, .9, .95, .99]).to_dict()
stat_df = pd.DataFrame([stat])
stat_df.to_csv(os.path.join(OUT, 'pstar_distance_desc_stats.csv'), index=False)

# ===== NEAR-MISS FORWARD =====
# 阈值: 未触发 & pct_legal <= 2%
near = unt[unt['pct_legal'] <= 0.02].copy()
print('\nnear-miss (<=2%):', len(near))
rows = []
tr = pd.read_csv(os.path.join(OUT, 'base_trades.csv'))
tr['entry_date'] = tr['entry_date'].astype(str)
tr_ret = dict(zip(zip(tr['ts_code'], tr['entry_date']), tr['return_pct']))
tr_exit = dict(zip(zip(tr['ts_code'], tr['entry_date']), tr['exit_date']))
for _, r in near.iterrows():
    ts = r['ts_code']
    gi = day_idx.get(pd.Timestamp(r['date']))
    if gi is None:
        continue
    if ts not in tc_days or gi not in tc_days[ts]:
        continue
    k = np.searchsorted(tc_days[ts], gi)
    fut = tc_days[ts][k + 1: k + 21]  # 后续最多20个有效交易日
    entry_cost = r['avg_cost']
    entry_gi = day_idx.get(pd.Timestamp(r['entry_date']))
    # 该日浮盈亏 (close vs avg_cost)
    fl_now = r['float_pnl']
    # 提前卖收入估算 (当日 threshold × (1-slip))
    slip = 0.001
    early_proceeds_est = r['eff_threshold'] * (1 - slip)  # 每股
    # 后续路径
    trig_day = None; trig_n = None; trig_ret = None
    max_high = -1e9; min_low = 1e9
    close_rets = {}
    for n, gi2 in enumerate(fut, start=1):
        P_adj, P_raw, thr, _ = calc_pstar(ts, gi2)
        dj = days[gi2]; j = D[dj]['pos'][ts]
        high = float(D[dj]['high'][j]); low = float(D[dj]['low'][j])
        close = float(D[dj]['close'][j])
        max_high = max(max_high, high); min_low = min(min_low, low)
        close_rets[n] = close / entry_cost - 1
        if n in (5, 10, 20):
            pass
        if not np.isnan(thr):
            if high >= thr:
                trig_day = str(dj.date()); trig_n = n; trig_ret = close / entry_cost - 1
                break
    key = (ts, r['entry_date'])
    rows.append(dict(
        ts_code=ts, date=r['date'], entry_date=r['entry_date'], level=r['level'],
        avg_cost=round(r['avg_cost'], 4), pstar_raw=round(r['pstar_raw'], 4),
        threshold=round(r['eff_threshold'], 4), high_raw=round(r['high_raw'], 4),
        gap_yuan=round(r['gap_eff'], 4), gap_pct=round(r['pct_eff'] if not np.isnan(r['pct_eff']) else r['pct_legal'], 6),
        hold_days=int(r['hold_days']),
        float_pnl_day=round(float(r['float_pnl']), 2),
        early_exit_proceeds_per_share=round(early_proceeds_est, 4),
        trigger_1d=int(trig_n == 1), trigger_3d=int(trig_n is not None and trig_n <= 3),
        trigger_5d=int(trig_n is not None and trig_n <= 5),
        trigger_10d=int(trig_n is not None and trig_n <= 10),
        trigger_20d=int(trig_n is not None),
        first_trigger_day=trig_day if trig_day else '', first_trigger_n=trig_n if trig_n else '',
        trigger_close_ret=round(trig_ret, 4) if trig_ret is not None else '',
        max_high_fwd20=round(max_high, 4), min_low_fwd20=round(min_low, 4),
        max_high_ret_fwd20=round(max_high / entry_cost - 1, 4) if max_high > -1e8 else '',
        min_low_ret_fwd20=round(min_low / entry_cost - 1, 4) if min_low < 1e8 else '',
        close_ret_5d=round(close_rets.get(5, np.nan), 4), close_ret_10d=round(close_rets.get(10, np.nan), 4),
        close_ret_20d=round(close_rets.get(20, np.nan), 4),
        drop5_5d=int(close_rets.get(5, 0) <= -0.05), drop5_10d=int(close_rets.get(10, 0) <= -0.05),
        drop10_20d=int(close_rets.get(20, 0) <= -0.10),
        final_trade_ret=tr_ret.get(key, np.nan), final_exit_date=tr_exit.get(key, '')))
nm = pd.DataFrame(rows)
nm.to_csv(os.path.join(OUT, 'near_miss_forward_outcomes.csv'), index=False)
print('near-miss rows:', len(nm))
# 汇总: 按 gap 桶 (0.1/0.2/0.3/0.5/0.75/1/1.5/2%) 后续触发率 & 深跌率 & 亏损率
print('\n=== near-miss summary by threshold ===')
for lim in [0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015, 0.02]:
    sub = nm[nm['gap_pct'] < lim]
    if len(sub) == 0:
        continue
    trig5 = sub['trigger_5d'].mean() * 100
    trig20 = sub['trigger_20d'].mean() * 100
    drop5_5 = sub['drop5_5d'].mean() * 100
    drop5_10 = sub['drop5_10d'].mean() * 100
    drop10_20 = sub['drop10_20d'].mean() * 100
    lose = (sub['final_trade_ret'] < 0).mean() * 100
    win = (sub['final_trade_ret'] > 0).mean() * 100
    print(f"  <= {lim*100:.2f}%: n={len(sub):4d}  5d触发率={trig5:5.1f}%  20d触发率={trig20:5.1f}%  "
          f"5d后跌>5%={drop5_5:5.1f}%  10d后跌>5%={drop5_10:5.1f}%  20d后跌>10%={drop10_20:5.1f}%  "
          f"最终亏={lose:5.1f}%  最终盈={win:5.1f}%")
print('NEAR-MISS DONE')
