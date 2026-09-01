"""
全市场成交量放量信号分析
研究问题：入场日（收盘<布林下轨）当天成交量突然放大（相对前期N日均量），是否是更好的底部确认信号？

对95,615笔交易，计算入场日相对前5日/前20日均量的放量倍数（vol与amount两个维度），
再按收益率分层、放量阈值分组统计收益表现。
"""
import os
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    print('加载日线数据...', flush=True)
    daily = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    daily['date'] = pd.to_datetime(daily['date'])
    daily = daily.sort_values(['ts_code', 'date']).reset_index(drop=True)

    print('计算滚动均量（前5/20日，不含当日）...', flush=True)
    # 按个股分组计算前N日均量（shift(1)排除当日）
    grp = daily.groupby('ts_code')
    for n in [5, 20]:
        daily[f'vol_ma{n}_prev'] = grp['vol'].transform(lambda x: x.rolling(n).mean().shift(1))
        daily[f'amt_ma{n}_prev'] = grp['amount'].transform(lambda x: x.rolling(n).mean().shift(1))

    daily['vol_ratio_5'] = daily['vol'] / daily['vol_ma5_prev']
    daily['vol_ratio_20'] = daily['vol'] / daily['vol_ma20_prev']
    daily['amt_ratio_5'] = daily['amount'] / daily['amt_ma5_prev']
    daily['amt_ratio_20'] = daily['amount'] / daily['amt_ma20_prev']

    # 保留需要merge的列
    keep = ['ts_code', 'date', 'vol_ratio_5', 'vol_ratio_20', 'amt_ratio_5', 'amt_ratio_20']
    daily_slim = daily[keep]

    print('加载交易明细...', flush=True)
    trades = pd.read_csv(os.path.join(PROJECT_ROOT, 'results', 'trades_all_rounds_clean.csv'))
    trades['entry_date'] = pd.to_datetime(trades['entry_date'])

    print('合并入场日放量指标...', flush=True)
    df = trades.merge(daily_slim, left_on=['ts_code', 'entry_date'], right_on=['ts_code', 'date'], how='left')
    print(f'合并后 {len(df)} 笔, 有放量数据的 {df["vol_ratio_5"].notna().sum()} 笔', flush=True)

    # ============ 1. 总体放量分布 ============
    print('\n===== 入场日放量倍数分布（相对前5日均量） =====', flush=True)
    for th in [1.5, 2, 3, 5, 8]:
        n = (df['vol_ratio_5'] >= th).sum()
        print(f'vol_ratio_5 >= {th}: {n} 笔 ({n/len(df)*100:.1f}%)', flush=True)

    # ============ 2. 放量 vs 不放量 收益对比 ============
    print('\n===== 放量 vs 不放量 收益对比 =====', flush=True)
    rows = []
    for col, label in [('vol_ratio_5', '量比(5日均量)'), ('vol_ratio_20', '量比(20日均量)'),
                       ('amt_ratio_5', '额比(5日均额)'), ('amt_ratio_20', '额比(20日均额)')]:
        for th in [2, 3, 5]:
            hi = df[df[col] >= th]
            lo = df[(df[col] < th) & (df[col].notna())]
            rows.append({
                '指标': label, '阈值': f'>={th}x',
                '交易数': len(hi),
                '占比%': round(len(hi) / df[col].notna().sum() * 100, 1),
                '平均收益%': round(hi['return_pct'].mean(), 2),
                '中位收益%': round(hi['return_pct'].median(), 2),
                '胜率%': round((hi['pnl'] > 0).mean() * 100, 1),
                '平均持仓天': round(hi['hold_days'].mean(), 1),
                '对比-不放量平均收益%': round(lo['return_pct'].mean(), 2),
                '对比-不放量胜率%': round((lo['pnl'] > 0).mean() * 100, 1),
            })
    df_cmp = pd.DataFrame(rows)
    print(df_cmp.to_string(index=False), flush=True)

    # ============ 3. 收益分层看放量占比 ============
    print('\n===== 按收益率分层，各档放量(vol_ratio_5>=3)占比 =====', flush=True)
    bins = [-np.inf, -30, -10, 0, 10, 30, 50, np.inf]
    labels = ['<-30%', '-30~-10%', '-10~0%', '0~10%', '10~30%', '30~50%', '>50%']
    df['ret_bin'] = pd.cut(df['return_pct'], bins=bins, labels=labels)
    lay = df.groupby('ret_bin', observed=True).apply(
        lambda g: pd.Series({
            '交易数': len(g),
            '放量占比%': round((g['vol_ratio_5'] >= 3).mean() * 100, 1),
            '中位量比': round(g['vol_ratio_5'].median(), 2),
            '放量交易平均收益%': round(g[g['vol_ratio_5'] >= 3]['return_pct'].mean(), 2),
            '不放量交易平均收益%': round(g[g['vol_ratio_5'] < 3]['return_pct'].mean(), 2),
        }), include_groups=False).reset_index()
    print(lay.to_string(index=False), flush=True)

    # ============ 4. 相关性 ============
    print('\n===== 放量倍数与收益相关性 =====', flush=True)
    for col in ['vol_ratio_5', 'vol_ratio_20', 'amt_ratio_5', 'amt_ratio_20']:
        s = df[['return_pct', col]].dropna()
        r = np.corrcoef(s['return_pct'], s[col])[0, 1]
        # 只用对数
        r_log = np.corrcoef(s['return_pct'], np.log1p(s[col].clip(lower=0)))[0, 1]
        print(f'{col}: 线性相关={r:+.3f}, log相关={r_log:+.3f} (n={len(s)})', flush=True)

    # ============ 5. 分年份放量交易占比 ============
    print('\n===== 分年份：放量交易占比与收益 =====', flush=True)
    y = df.groupby('entry_year').apply(
        lambda g: pd.Series({
            '交易数': len(g),
            '放量(>=3x)占比%': round((g['vol_ratio_5'] >= 3).mean() * 100, 1),
            '放量交易平均收益%': round(g[g['vol_ratio_5'] >= 3]['return_pct'].mean(), 2),
            '全部平均收益%': round(g['return_pct'].mean(), 2),
        }), include_groups=False).reset_index()
    print(y.to_string(index=False), flush=True)

    # ============ 6. 高收益交易中放量情况（Top10%/收益>30%/收益>50%） ============
    print('\n===== 高收益交易中的放量情况 =====', flush=True)
    top10 = df[df['return_pct'] >= df['return_pct'].quantile(0.90)]
    hi30 = df[df['return_pct'] >= 30]
    hi50 = df[df['return_pct'] >= 50]
    for name, sub in [('Top10%收益', top10), ('收益>30%', hi30), ('收益>50%', hi50)]:
        print(f'{name}: n={len(sub)}, 放量(>=3x)占比={(sub["vol_ratio_5"]>=3).mean()*100:.1f}%, '
              f'中位量比={sub["vol_ratio_5"].median():.2f}, 平均收益={sub["return_pct"].mean():.1f}%', flush=True)

    # ============ 保存结果 ============
    df_cmp.to_csv(os.path.join(PROJECT_ROOT, 'results', 'volume_signal_comparison.csv'), index=False)
    lay.to_csv(os.path.join(PROJECT_ROOT, 'results', 'volume_signal_retbins.csv'), index=False)
    # 保存带放量指标的完整交易明细（用于后续深入分析）
    out_cols = ['ts_code', 'name', 'entry_date', 'exit_date', 'levels_used',
                'pnl', 'return_pct', 'hold_days', 'exit_type',
                'vol_ratio_5', 'vol_ratio_20', 'amt_ratio_5', 'amt_ratio_20']
    df[out_cols].to_csv(os.path.join(PROJECT_ROOT, 'results', 'trades_with_volume.csv'), index=False)
    print(f'\n结果已保存: results/volume_signal_comparison.csv, volume_signal_retbins.csv, trades_with_volume.csv', flush=True)


if __name__ == '__main__':
    main()
