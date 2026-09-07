"""MONTHLY-BB-MR 统计图（8 类，PNG 输出到 results/evidence/monthly_bb/charts/）
辅助理解，不替代 CSV。中文字体回退英文。
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'monthly_bb')
DATA_DIR = os.path.abspath(DATA_DIR)
OUT = os.path.join(os.path.dirname(__file__), '..', '..', 'results', 'evidence', 'monthly_bb', 'charts')
OUT = os.path.abspath(OUT)
os.makedirs(OUT, exist_ok=True)

HORIZONS = [1, 3, 6, 12]
DEV_END = pd.Period("2024-12", freq="M")

plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'STHeiti', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def fig_hist(sig):
    """1) 1/3/6/12M forward return histogram（开发期 NEW_EPISODE）"""
    s = sig[(sig['pm'] <= DEV_END) & (sig['NEW_EPISODE'] == 1)]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    for ax, h in zip(axes.flat, HORIZONS):
        x = s[f'ret_cc_{h}m'].dropna() * 100
        ax.hist(x, bins=60, color='#5B8FF9', alpha=0.8)
        ax.axvline(x.median(), color='red', ls='--', lw=1.5, label=f'median={x.median():.1f}%')
        ax.axvline(0, color='black', lw=1)
        ax.set_title(f'{h}M forward return (close-to-close)')
        ax.set_xlabel('%'); ax.legend(fontsize=8)
    fig.suptitle('Monthly BB lower signal: forward return distribution (dev, NEW_EPISODE)')
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '01_forward_return_hist.png'), dpi=110)
    plt.close(fig)


def fig_median_path(sig):
    """2) forward median path（P25/P50/P75）"""
    s = sig[(sig['pm'] <= DEV_END) & (sig['NEW_EPISODE'] == 1)]
    pts = {}
    for h in HORIZONS:
        x = s[f'ret_cc_{h}m'].dropna() * 100
        pts[h] = dict(p25=np.percentile(x, 25), p50=np.percentile(x, 50), p75=np.percentile(x, 75))
    fig, ax = plt.subplots(figsize=(8, 5))
    hs = HORIZONS
    ax.plot(hs, [pts[h]['p25'] for h in hs], 'o--', label='P25')
    ax.plot(hs, [pts[h]['p50'] for h in hs], 'o-', label='P50')
    ax.plot(hs, [pts[h]['p75'] for h in hs], 'o--', label='P75')
    ax.axhline(0, color='black', lw=1)
    ax.set_xlabel('Horizon (months)'); ax.set_ylabel('Return %')
    ax.set_title('Forward median path (dev, NEW_EPISODE)')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '02_forward_median_path.png'), dpi=110)
    plt.close(fig)


def fig_mfe_mae(sig):
    """3) MFE/MAE percentile path"""
    s = sig[(sig['pm'] <= DEV_END) & (sig['NEW_EPISODE'] == 1)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, tag, col in [(axes[0], 'MFE', 'mfe'), (axes[1], 'MAE', 'mae')]:
        for p in (10, 25, 50, 75, 90):
            vals = [np.nanpercentile(s[f'{col}_{h}m'].dropna() * 100, p) for h in HORIZONS]
            ax.plot(HORIZONS, vals, 'o-', label=f'P{p}')
        ax.axhline(0, color='black', lw=1)
        ax.set_title(f'{tag} percentile path (signal-close basis)')
        ax.set_xlabel('Horizon (months)'); ax.set_ylabel('%')
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '03_mfe_mae_path.png'), dpi=110)
    plt.close(fig)


def fig_universe(sig):
    """4) universe comparison（12M median/mean by universe）"""
    s = sig[(sig['pm'] <= DEV_END) & (sig['NEW_EPISODE'] == 1)]
    rows = []
    for u in ['ALL_A', 'TOP500', 'TOP300', 'TOP100']:
        x = s[s['universe_clean'] == u]['ret_cc_12m'].dropna() * 100
        rows.append((u, x.mean(), x.median(), len(x)))
    df = pd.DataFrame(rows, columns=['universe', 'mean', 'median', 'n'])
    fig, ax = plt.subplots(figsize=(8, 5))
    xpos = np.arange(len(df))
    ax.bar(xpos - 0.2, df['mean'], 0.35, label='mean', color='#5B8FF9')
    ax.bar(xpos + 0.2, df['median'], 0.35, label='median', color='#F6BD16')
    ax.axhline(0, color='black', lw=1)
    ax.set_xticks(xpos); ax.set_xticklabels(df['universe'])
    for i, r in df.iterrows():
        ax.text(i, max(r['mean'], r['median']) + 0.5, f"n={r['n']}", ha='center', fontsize=9)
    ax.set_ylabel('12M return %'); ax.set_title('Universe comparison (12M, dev, NEW_EPISODE)')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '04_universe_comparison.png'), dpi=110)
    plt.close(fig)


def fig_vs_null(sig, b1):
    """5) signal vs null distribution（B1 同股随机月，6M/12M）"""
    s = sig[(sig['pm'] <= DEV_END) & (sig['NEW_EPISODE'] == 1)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, h in [(axes[0], 6), (axes[1], 12)]:
        x = s[f'ret_cc_{h}m'].dropna() * 100
        ax.hist(x, bins=50, alpha=0.6, color='#5B8FF9', label=f'signal (n={len(x)})')
        row = b1[b1['horizon'] == f'{h}M']
        if len(row):
            ax.axvline(row['obs_mean'].values[0] * 100, color='red', ls='-', lw=2,
                       label=f"signal mean={row['obs_mean'].values[0]*100:.1f}%")
            ax.axvline(row['null_mean'].values[0] * 100, color='green', ls='--', lw=2,
                       label=f"random-month mean={row['null_mean'].values[0]*100:.1f}%")
        ax.axvline(0, color='black', lw=1)
        ax.set_title(f'{h}M: signal vs same-stock random month')
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '05_signal_vs_null.png'), dpi=110)
    plt.close(fig)


def fig_decade(sig):
    """6) decade stability（6M/12M median）"""
    s = sig[sig['NEW_EPISODE'] == 1]
    rows = []
    for (d0, d1, label) in [(2005, 2009, '05-09'), (2010, 2014, '10-14'), (2015, 2019, '15-19'),
                            (2020, 2024, '20-24'), (2025, 2100, '25+')]:
        sub = s[(s['pm'].dt.year >= d0) & (s['pm'].dt.year <= d1)]
        rows.append((label, sub['ret_cc_6m'].dropna().median() * 100,
                     sub['ret_cc_12m'].dropna().median() * 100,
                     len(sub['ret_cc_12m'].dropna())))
    df = pd.DataFrame(rows, columns=['decade', 'm6', 'm12', 'n'])
    fig, ax = plt.subplots(figsize=(8, 5))
    xpos = np.arange(len(df))
    ax.bar(xpos - 0.2, df['m6'], 0.35, label='6M median', color='#5B8FF9')
    ax.bar(xpos + 0.2, df['m12'], 0.35, label='12M median', color='#F6BD16')
    ax.axhline(0, color='black', lw=1)
    ax.set_xticks(xpos); ax.set_xticklabels(df['decade'])
    for i, r in df.iterrows():
        ax.text(i, max(r['m6'], r['m12']) + 1, f"n={r['n']}", ha='center', fontsize=9)
    ax.set_ylabel('median %'); ax.set_title('Decade stability (NEW_EPISODE)')
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '06_decade_stability.png'), dpi=110)
    plt.close(fig)


def fig_bbz(sig):
    """8) BB z-score vs future return（buckets）"""
    s = sig[(sig['pm'] <= DEV_END) & (sig['NEW_EPISODE'] == 1)].copy()
    s['z_bucket'] = pd.cut(s['bb_z'], bins=[-np.inf, -4, -3, -2.5, -2, 0],
                           labels=['<-4', '-4~-3', '-3~-2.5', '-2.5~-2', '>-2'])
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, h in [(axes[0], 6), (axes[1], 12)]:
        g = s.groupby('z_bucket', observed=True)[f'ret_cc_{h}m']
        means = g.mean() * 100
        meds = g.median() * 100
        ns = g.count()
        xpos = np.arange(len(means))
        ax.bar(xpos - 0.2, means.values, 0.35, label='mean', color='#5B8FF9')
        ax.bar(xpos + 0.2, meds.values, 0.35, label='median', color='#F6BD16')
        ax.axhline(0, color='black', lw=1)
        ax.set_xticks(xpos); ax.set_xticklabels(means.index.astype(str))
        for i, n in enumerate(ns.values):
            ax.text(i, max(means.values[i], meds.values[i]) + 0.5, f'n={n}', ha='center', fontsize=8)
        ax.set_title(f'{h}M return by BB z bucket'); ax.set_ylabel('%')
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '08_bbz_vs_return.png'), dpi=110)
    plt.close(fig)


def fig_index_cases(sig_idx):
    """7) 指数信号案例：沪深300 月线 close vs bb_lower + 信号点"""
    import matplotlib.dates as mdates
    for code, name in [('000300', 'HS300'), ('000905', 'CSI500'), ('000852', 'CSI1000'),
                       ('399006', 'CYB'), ('000688', 'STAR50'), ('000016', 'SSE50')]:
        ix = pd.read_parquet(os.path.join(DATA_DIR, f'idx_{code}.parquet'))
        ix['trade_date'] = pd.to_datetime(ix['trade_date'])
        ix['date'] = ix['trade_date']
        ix = ix.sort_values('date')
        ix['close'] = ix['close'].astype(float)
        # 月线 + BB
        ix['pm'] = ix['date'].dt.to_period('M')
        m = ix.groupby('pm').agg(close=('close', 'last'),
                                 month_end_date=('date', 'max')).reset_index()
        m['close'] = m['close'].astype(float)
        m['ma'] = m['close'].rolling(20, min_periods=20).mean()
        m['sd'] = m['close'].rolling(20, min_periods=20).std(ddof=1)
        m['lower'] = m['ma'] - 2 * m['sd']
        m['sig'] = m['close'] < m['lower']
        sig_pts = m[m['sig']]
        fig, ax = plt.subplots(figsize=(13, 4.5))
        ax.plot(m['month_end_date'], m['close'], lw=0.8, color='#333', label='index close')
        ax.plot(m['month_end_date'], m['lower'], lw=0.8, color='#F6BD16', label='BB lower (20,2)')
        ax.scatter(sig_pts['month_end_date'], sig_pts['close'], color='red', s=28, zorder=5, label='signal')
        ax.set_title(f'{code} {name}: monthly close vs BB lower, signals')
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, f'07_index_cases_{code}.png'), dpi=110)
        plt.close(fig)


def main():
    print('== load ==')
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from analyze_monthly import load_mcap_map, add_universe
    sig = pd.read_parquet(os.path.join(DATA_DIR, 'monthly_signals.parquet'))
    sig['pm'] = sig['pm'].astype('period[M]')
    sig = add_universe(sig, load_mcap_map())
    b1 = pd.read_csv(os.path.join(OUT, '..', 'benchmark_same_stock_random.csv'))
    fig_hist(sig)
    fig_median_path(sig)
    fig_mfe_mae(sig)
    fig_universe(sig)
    fig_vs_null(sig, b1)
    fig_decade(sig)
    fig_bbz(sig)
    fig_index_cases(sig)
    print('DONE ->', OUT)


if __name__ == '__main__':
    main()
