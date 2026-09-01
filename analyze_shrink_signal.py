"""
缩量跌破布林下轨信号分析
研究问题：入场日（收盘<布林下轨）当天成交量缩到很小（相对前5/20日均量），是否是更好的底部确认信号？

基于 trades_with_volume.csv（已含入场日量比/额比），按缩量阈值分组统计，
并做完整量比分桶分析，观察收益随量比的变化趋势。
"""
import os
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    print('加载含放量指标的交易明细...', flush=True)
    df = pd.read_csv(os.path.join(PROJECT_ROOT, 'results', 'trades_with_volume.csv'))
    print(f'共 {len(df)} 笔', flush=True)

    # ============ 1. 缩量阈值分组统计 ============
    print('\n===== 缩量阈值分组统计（vol_ratio_5 前5日均量） =====', flush=True)
    rows = []
    for col, label in [('vol_ratio_5', '量比(5日均量)'), ('vol_ratio_20', '量比(20日均量)'),
                       ('amt_ratio_5', '额比(5日均额)'), ('amt_ratio_20', '额比(20日均额)')]:
        valid = df[df[col].notna()]
        for th in [1.0, 0.8, 0.6, 0.5, 0.4, 0.3]:
            sub = valid[valid[col] < th]
            if len(sub) == 0:
                continue
            rows.append({
                '指标': label, '阈值': f'<{th}x',
                '交易数': len(sub),
                '占比%': round(len(sub) / len(valid) * 100, 1),
                '平均收益%': round(sub['return_pct'].mean(), 2),
                '中位收益%': round(sub['return_pct'].median(), 2),
                '胜率%': round((sub['pnl'] > 0).mean() * 100, 1),
                '平均持仓天': round(sub['hold_days'].mean(), 1),
                '平均层数': round(sub['levels_used'].mean(), 2),
            })
    df_shrink = pd.DataFrame(rows)
    print(df_shrink.to_string(index=False), flush=True)

    # ============ 2. 完整量比分桶分析（vol_ratio_5） ============
    print('\n===== 量比分桶：收益随量比变化趋势（vol_ratio_5） =====', flush=True)
    bins = [-np.inf, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, np.inf]
    labels = ['<0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0', '1.0-1.5', '1.5-2.0', '2.0-3.0', '3.0-5.0', '>5.0']
    df['vol_bin'] = pd.cut(df['vol_ratio_5'], bins=bins, labels=labels)
    bucket = df.groupby('vol_bin', observed=True).apply(
        lambda g: pd.Series({
            '交易数': len(g),
            '占比%': round(len(g) / len(df) * 100, 1),
            '平均收益%': round(g['return_pct'].mean(), 2),
            '中位收益%': round(g['return_pct'].median(), 2),
            '胜率%': round((g['pnl'] > 0).mean() * 100, 1),
            '平均持仓天': round(g['hold_days'].mean(), 1),
        }), include_groups=False).reset_index()
    print(bucket.to_string(index=False), flush=True)

    # ============ 3. 分年份：缩量(<0.8)交易表现 ============
    print('\n===== 分年份：缩量(<0.8) vs 全部 =====', flush=True)
    df['entry_year'] = df['entry_date'].str[:4]
    y = df.groupby('entry_year').apply(
        lambda g: pd.Series({
            '交易数': len(g),
            '缩量(<0.8)占比%': round((g['vol_ratio_5'] < 0.8).mean() * 100, 1),
            '缩量交易平均收益%': round(g[g['vol_ratio_5'] < 0.8]['return_pct'].mean(), 2),
            '缩量交易胜率%': round((g[g['vol_ratio_5'] < 0.8]['pnl'] > 0).mean() * 100, 1),
            '全部平均收益%': round(g['return_pct'].mean(), 2),
            '全部胜率%': round((g['pnl'] > 0).mean() * 100, 1),
        }), include_groups=False).reset_index()
    print(y.to_string(index=False), flush=True)

    # ============ 4. 缩量 vs 放量 极端对比 ============
    print('\n===== 极端缩量 vs 极端放量 对比 =====', flush=True)
    comps = []
    for col, label in [('vol_ratio_5', '量比(5日)'), ('vol_ratio_20', '量比(20日)')]:
        v = df[df[col].notna()]
        for name, cond in [('极度缩量(<0.4)', v[col] < 0.4),
                           ('明显缩量(<0.6)', v[col] < 0.6),
                           ('轻微缩量(<0.8)', v[col] < 0.8),
                           ('温和量(0.8-1.2)', (v[col] >= 0.8) & (v[col] < 1.2)),
                           ('轻微放量(1.2-2)', (v[col] >= 1.2) & (v[col] < 2.0)),
                           ('明显放量(2-3)', (v[col] >= 2.0) & (v[col] < 3.0)),
                           ('极度放量(>3)', v[col] >= 3.0)]:
            sub = v[cond]
            comps.append({
                '指标': label, '分组': name,
                '交易数': len(sub),
                '占比%': round(len(sub) / len(v) * 100, 1),
                '平均收益%': round(sub['return_pct'].mean(), 2),
                '胜率%': round((sub['pnl'] > 0).mean() * 100, 1),
            })
    df_comp = pd.DataFrame(comps)
    print(df_comp.to_string(index=False), flush=True)

    # ============ 5. 相关性（缩量端） ============
    print('\n===== 相关性 =====', flush=True)
    for col in ['vol_ratio_5', 'vol_ratio_20']:
        s = df[['return_pct', col]].dropna()
        r = np.corrcoef(s['return_pct'], s[col])[0, 1]
        print(f'{col}: 线性相关={r:+.3f} (n={len(s)})', flush=True)

    # 保存
    df_shrink.to_csv(os.path.join(PROJECT_ROOT, 'results', 'shrink_signal_thresholds.csv'), index=False)
    bucket.to_csv(os.path.join(PROJECT_ROOT, 'results', 'shrink_signal_buckets.csv'), index=False)
    df_comp.to_csv(os.path.join(PROJECT_ROOT, 'results', 'shrink_signal_comparison.csv'), index=False)
    print(f'\n结果已保存: shrink_signal_thresholds.csv, shrink_signal_buckets.csv, shrink_signal_comparison.csv', flush=True)


if __name__ == '__main__':
    main()
