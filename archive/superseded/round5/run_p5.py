"""P5: K=3 交易独立性分析 + 不泄漏未来的 K 选择 walk-forward
"""
import sys, json, os
import numpy as np, pandas as pd
sys.path.insert(0, '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat')
from round5_audit import load_and_extend, run_fast_multi_v5, full_stats

OUT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/results/round5'
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(42)

def main():
    days, D, etf_idx, etf_px, etf_open, etf_nav, df, listing = load_and_extend(limit_down_mode='old')
    eq, tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=3,
                               exit_bb_mode='current', buy_mode='close', etf_mark='close', stamp_tax_mode='flat')
    tr = tr.copy()
    tr['entry'] = pd.to_datetime(tr['entry_date'])
    tr['exit'] = pd.to_datetime(tr['exit_date'])
    n = len(tr)
    print(f"K=3 交易笔数: {n}")

    # 1. 时间重叠
    overlap_pairs = 0
    overlap_pairs_list = []
    for a in range(n):
        for b in range(a+1, n):
            if tr.iloc[a]['entry'] <= tr.iloc[b]['exit'] and tr.iloc[b]['entry'] <= tr.iloc[a]['exit']:
                overlap_pairs += 1
                overlap_pairs_list.append((tr.iloc[a]['ts_code'], tr.iloc[a]['entry'].date(),
                                           tr.iloc[b]['ts_code'], tr.iloc[b]['entry'].date()))
    print(f"时间重叠交易对: {overlap_pairs}")

    # 2. 最大同时持仓数: 逐日统计
    daily = {}
    for _, r in tr.iterrows():
        d = r['entry']
        while d <= r['exit']:
            daily[d] = daily.get(d, 0) + 1
            d += pd.Timedelta(days=1)  # 近似, 交易日粒度
    # 用交易日更准确: 用 days 序列
    day_set = {pd.Timestamp(d): i for i, d in enumerate(days)}
    holdings = np.zeros(len(days))
    for _, r in tr.iterrows():
        e = day_set.get(r['entry'])
        x = day_set.get(r['exit'])
        if e is None or x is None:
            continue
        holdings[e:x+1] += 1
    print(f"最大同时持仓数: {holdings.max()}")
    print(f"同时持仓>=2 的天数占比: {(holdings>=2).mean()*100:.1f}%")
    print(f"同时持仓>=3 的天数占比: {(holdings>=3).mean()*100:.1f}%")

    # 3. 入场日期唯一数量
    uniq_entry = tr['entry'].nunique()
    print(f"入场日期唯一数量: {uniq_entry} / {n}")
    # 4. 同日多笔入场
    entry_counts = tr['entry'].value_counts()
    multi_days = (entry_counts > 1).sum()
    print(f"同日多笔入场的天数: {multi_days}, 最多同日入场: {entry_counts.max()}")

    # 5. 入场间隔分布
    sorted_entries = sorted(tr['entry'])
    gaps = np.diff([day_set.get(pd.Timestamp(x), np.nan) for x in sorted_entries])
    gaps = gaps[~np.isnan(gaps)]
    print(f"入场间隔(交易日): mean={gaps.mean():.1f} median={np.median(gaps):.0f} p10={np.percentile(gaps,10):.0f} p90={np.percentile(gaps,90):.0f}")

    # 6. 聚类: ±3/±5/±10 交易日聚类
    entry_idx_sorted = sorted([day_set.get(pd.Timestamp(x)) for x in tr['entry'] if pd.Timestamp(x) in day_set])
    def cluster(eps):
        clusters = []
        cur = [entry_idx_sorted[0]]
        for x in entry_idx_sorted[1:]:
            if x - cur[-1] <= eps:
                cur.append(x)
            else:
                clusters.append(cur)
                cur = [x]
        clusters.append(cur)
        return clusters
    for eps in (3, 5, 10):
        cl = cluster(eps)
        print(f"±{eps}交易日聚类: {len(cl)} 个有效事件(独立簇) / {len(entry_idx_sorted)} 笔")

    # 7. 同一市场急跌窗口集中度: 用沪深300指数连续下跌>=5%的窗口
    try:
        idx = pd.read_parquet('data/index_000300.parquet')
        idx['trade_date'] = pd.to_datetime(idx['trade_date'])
        idx = idx.sort_values('trade_date').reset_index(drop=True)
        idx['ret'] = idx['close'].pct_change()
        # 急跌窗口: 5日内累计跌幅>=5%
        idx['cum5'] = idx['ret'].rolling(5).sum()
        crash_days = set(idx.loc[idx['cum5'] <= -0.05, 'trade_date'])
        # 每笔入场是否在急跌窗口内（入场日前后3日）
        in_crash = 0
        for _, r in tr.iterrows():
            e = r['entry']
            if any((e - pd.Timedelta(days=3) <= cd <= e + pd.Timedelta(days=3)) for cd in crash_days):
                in_crash += 1
        print(f"入场位于市场急跌窗口(±3日)内的交易: {in_crash}/{n} ({in_crash/n*100:.1f}%)")
    except Exception as ex:
        print("急跌窗口统计失败:", ex)

    # ---- Bootstrap ----
    pnl = tr['pnl'].to_numpy()
    stock_pnl_total = pnl.sum()
    # 1) trade bootstrap (有放回)
    B = 10000
    boot = np.array([rng.choice(pnl, size=n, replace=True).sum() for _ in range(B)])
    print(f"\n[trade bootstrap] Σpnl 5%={np.percentile(boot,5):,.0f} 25%={np.percentile(boot,25):,.0f} "
          f"50%={np.percentile(boot,50):,.0f} 75%={np.percentile(boot,75):,.0f} 95%={np.percentile(boot,95):,.0f}")
    print(f"P(Σpnl>0)={ (boot>0).mean()*100:.1f}%")
    # 2) block bootstrap (按入场排序, 块长30交易日, 覆盖时间依赖)
    order = np.argsort([day_set.get(pd.Timestamp(x), 0) for x in tr['entry']])
    pnl_sorted = pnl[order]
    block_len = 30
    nb = int(np.ceil(n / block_len))
    blocks = [pnl_sorted[i*block_len:(i+1)*block_len] for i in range(nb)]
    bb = []
    for _ in range(B):
        picks = rng.integers(0, len(blocks), size=nb)
        samp = np.concatenate([blocks[p] for p in picks])[:n]
        bb.append(samp.sum())
    bb = np.array(bb)
    print(f"[block bootstrap(30d)] P(Σpnl>0)={(bb>0).mean()*100:.1f}% 5%={np.percentile(bb,5):,.0f} 95%={np.percentile(bb,95):,.0f}")
    # 3) cluster bootstrap (按独立簇)
    cl = cluster(5)
    cl_sums = [sum(pnl[order[entry_idx_sorted.index(ci)]] if False else 0 for ci in c) for c in cl]
    # 重写: 簇内 pnl
    idx_map = {idx: i for i, idx in enumerate(entry_idx_sorted)}
    cl_pnls = []
    for c in cl:
        s = 0
        for ci in c:
            pos_in_sorted = entry_idx_sorted.index(ci)
            s += pnl_sorted[pos_in_sorted]
        cl_pnls.append(s)
    cl_pnls = np.array(cl_pnls)
    cb = []
    for _ in range(B):
        picks = rng.integers(0, len(cl_pnls), size=len(cl_pnls))
        cb.append(cl_pnls[picks].sum())
    cb = np.array(cb)
    print(f"[cluster bootstrap(±5d)] P(Σpnl>0)={(cb>0).mean()*100:.1f}% 5%={np.percentile(cb,5):,.0f} 95%={np.percentile(cb,95):,.0f}")

    # ---- 不泄漏未来的 K 选择 walk-forward ----
    dts = [d.strftime('%Y-%m-%d') for d in days]
    train_end = dts.index('2023-12-29') + 1
    test_start = train_end
    print(f"\n[K walk-forward] train_end_idx={train_end}")
    k_rows = []
    for K in (1, 2, 3, 4, 5, 8):
        eq_tr, tr_tr = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=K,
                                         exit_bb_mode='current', buy_mode='close', etf_mark='close',
                                         stamp_tax_mode='flat', day_range=(0, train_end))
        s_tr = full_stats(eq_tr, tr_tr)
        eq_te, tr_te = run_fast_multi_v5(days, D, etf_idx, etf_px, etf_open, etf_nav, listing, K=K,
                                         exit_bb_mode='current', buy_mode='close', etf_mark='close',
                                         stamp_tax_mode='flat', day_range=(test_start, len(days)))
        s_te = full_stats(eq_te, tr_te)
        k_rows.append({'K': K, 'train_total': round(s_tr['total'],2), 'train_sharpe': round(s_tr['sharpe'],3),
                       'test_total': round(s_te['total'],2), 'test_sharpe': round(s_te['sharpe'],3)})
        print(f"K={K}: train={s_tr['total']:.2f}%(shp{s_tr['sharpe']:.2f}) test={s_te['total']:.2f}%(shp{s_te['sharpe']:.2f})")
    # Train 最优 K
    best_k = max(k_rows, key=lambda r: r['train_total'])
    print(f"Train最优K={best_k['K']}(train={best_k['train_total']}%) -> Test={best_k['test_total']}%")
    print(f"对照: 全样本最优K=3在Test={[r['test_total'] for r in k_rows if r['K']==3][0]}%")

    res = {'n': int(n), 'overlap_pairs': int(overlap_pairs),
           'max_concurrent': int(holdings.max()),
           'uniq_entry_days': int(uniq_entry), 'multi_entry_days': int(multi_days),
           'entry_gap_median': float(np.median(gaps)),
           'cluster_3d': len(cluster(3)), 'cluster_5d': len(cluster(5)), 'cluster_10d': len(cluster(10)),
           'boot_trade_p_pos': round((boot>0).mean()*100,1), 'boot_block_p_pos': round((bb>0).mean()*100,1),
           'boot_cluster_p_pos': round((cb>0).mean()*100,1),
           'k_walkforward': k_rows, 'train_best_K': int(best_k['K']),
           'train_best_K_test': round(best_k['test_total'],2),
           'K3_test': round([r['test_total'] for r in k_rows if r['K']==3][0],2)}
    with open(f'{OUT}/p5_summary.json', 'w') as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    pd.DataFrame(k_rows).to_csv(f'{OUT}/p5_k_walkforward.csv', index=False)
    print('\nP5 done.')

if __name__ == '__main__':
    main()
