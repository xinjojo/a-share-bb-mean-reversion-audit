"""
大样本特征分析：合并所有带pnl的交易记录
分析盈利交易 vs 亏损交易的特征差异
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
from data_loader.storage import DataStorage

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    storage = DataStorage(os.path.join(project_root, 'data', 'raw'))

    # 所有带pnl字段的交易记录文件
    pnl_files = [
        'trades_bearish_exit_20260827_014116.csv',
        'trades_multi_zz500_asc_top3_p3_20260827_131402.csv',
        'trades_multi_zz500_desc_top3_p3_20260827_132952.csv',
        'trades_opt_min5_drop1_trail3_max30_20260827_092638.csv',
        'trades_tp2_ts20_zz500_asc_top3_p3_20260827_140401.csv',
        'trades_tp2_ts20_zz500_desc_top3_p3_20260827_141934.csv',
    ]

    # 合并所有卖出交易
    all_sells = []
    for f in pnl_files:
        path = os.path.join(project_root, 'results', 'trades', f)
        if not os.path.exists(path):
            print(f"文件不存在: {f}")
            continue
        df = pd.read_csv(path)
        sells = df[df['action']=='SELL'].copy()
        sells['source_file'] = f
        all_sells.append(sells)

    all_sells = pd.concat(all_sells, ignore_index=True)
    print(f"合并卖出交易总数: {len(all_sells)}")
    print(f"盈利交易: {(all_sells['pnl']>0).sum()} ({(all_sells['pnl']>0).mean()*100:.1f}%)")
    print(f"亏损交易: {(all_sells['pnl']<=0).sum()} ({(all_sells['pnl']<=0).mean()*100:.1f}%)")

    # 去重（同一股票同一天同一策略可能重复）
    all_sells['key'] = all_sells['ts_code'] + '_' + all_sells['date'].astype(str) + '_' + all_sells['source_file']
    all_sells = all_sells.drop_duplicates(subset='key')
    print(f"去重后交易数: {len(all_sells)}")

    # 对每笔交易提取特征
    print("\n提取交易特征...")
    features = []
    cache = {}  # 缓存股票数据

    for idx, row in all_sells.iterrows():
        if idx % 100 == 0:
            print(f"  处理进度: {idx}/{len(all_sells)}")

        ts = row['ts_code']
        sell_date = pd.to_datetime(row['date'])

        # 找到对应的买入交易（同一股票，在卖出之前，取最近的一笔初始买入）
        source = row['source_file']
        source_df = pd.read_csv(os.path.join(project_root, 'results', 'trades', source))
        buy_trades = source_df[(source_df['action']=='BUY') &
                                (source_df['ts_code']==ts) &
                                (pd.to_datetime(source_df['date']) < sell_date) &
                                (source_df['reason']=='INITIAL_ENTRY')]
        if len(buy_trades) == 0:
            continue
        first_buy = buy_trades.iloc[-1]  # 取最近的一笔初始买入
        buy_date = pd.to_datetime(first_buy['date'])
        buy_price = first_buy['price']

        # 加载股票数据（带缓存）
        if ts not in cache:
            daily = storage.load_daily(ts)
            adj = storage.load_adj_factor(ts)
            if daily.empty or adj.empty:
                continue
            daily = daily.sort_values('date').reset_index(drop=True)
            daily['date'] = pd.to_datetime(daily['date'])
            adj = adj.sort_values('date').reset_index(drop=True)
            adj['date'] = pd.to_datetime(adj['date'])
            merged = pd.merge(daily[['date','open','high','low','close','vol','amount','pre_close']],
                              adj[['date','adj_factor']], on='date', how='inner')
            merged = merged.set_index('date')
            merged['adj_close'] = merged['close'] * merged['adj_factor']
            merged['bb_mid'] = merged['adj_close'].rolling(20).mean()
            merged['bb_std'] = merged['adj_close'].rolling(20).std()
            merged['bb_upper'] = merged['bb_mid'] + 2 * merged['bb_std']
            merged['bb_lower'] = merged['bb_mid'] - 2 * merged['bb_std']
            merged['bb_width'] = (merged['bb_upper'] - merged['bb_lower']) / merged['bb_mid'] * 100
            merged['pct_chg'] = merged['close'].pct_change() * 100
            merged['vol_ma5'] = merged['vol'].rolling(5).mean()
            merged['vol_ratio'] = merged['vol'] / merged['vol_ma5']
            cache[ts] = merged

        merged = cache[ts]
        if buy_date not in merged.index:
            continue
        buy_idx = merged.index.get_loc(buy_date)
        buy_row = merged.iloc[buy_idx]

        # 特征1：BB Lower偏离程度
        bb_deviation = (buy_row['adj_close'] - buy_row['bb_lower']) / buy_row['bb_lower'] * 100 if buy_row['bb_lower'] > 0 else np.nan

        # 特征2：布林带宽度
        bb_width = buy_row['bb_width']

        # 特征3：买入前5天/10天涨跌幅
        ret_5d = (merged.iloc[buy_idx]['adj_close'] / merged.iloc[buy_idx-5]['adj_close'] - 1) * 100 if buy_idx >= 5 else np.nan
        ret_10d = (merged.iloc[buy_idx]['adj_close'] / merged.iloc[buy_idx-10]['adj_close'] - 1) * 100 if buy_idx >= 10 else np.nan

        # 特征4：买入前5天下跌天数
        down_days_5 = (merged.iloc[buy_idx-4:buy_idx+1]['pct_chg'] < 0).sum() if buy_idx >= 4 else np.nan

        # 特征5：成交量比率
        vol_ratio = buy_row['vol_ratio']

        # 特征6：买入当天涨跌幅
        pct_chg_day = buy_row['pct_chg']

        # 特征7：持仓天数
        if 'holding_trays' in row and not pd.isna(row['holding_trays']):
            holding_days = row['holding_trays']
        elif 'days_held' in row and not pd.isna(row['days_held']):
            holding_days = row['days_held']
        else:
            holding_days = (sell_date - buy_date).days

        # 特征8：持仓期间最大浮盈/浮亏
        sell_idx = merged.index.get_loc(sell_date) if sell_date in merged.index else min(buy_idx + int(holding_days), len(merged)-1)
        hold_data = merged.iloc[buy_idx:min(sell_idx+1, len(merged))]
        if len(hold_data) > 1:
            max_gain = (hold_data['high'].max() / buy_price - 1) * 100
            max_drawdown = (hold_data['low'].min() / buy_price - 1) * 100
            # 第1天是否上涨
            day1_up = hold_data.iloc[1]['close'] > buy_price if len(hold_data) > 1 else np.nan
            # 前3天最大涨幅
            first3_max = (hold_data.iloc[1:min(4, len(hold_data))]['high'].max() / buy_price - 1) * 100 if len(hold_data) > 1 else np.nan
        else:
            max_gain = max_drawdown = day1_up = first3_max = np.nan

        features.append({
            'ts_code': ts,
            'buy_date': buy_date,
            'sell_date': sell_date,
            'pnl': row['pnl'],
            'pnl_pct': row['pnl'] / (row['shares'] * buy_price) * 100 if row['shares'] * buy_price > 0 else np.nan,
            'holding_days': holding_days,
            'bb_deviation': bb_deviation,
            'bb_width': bb_width,
            'ret_5d': ret_5d,
            'ret_10d': ret_10d,
            'down_days_5': down_days_5,
            'vol_ratio': vol_ratio,
            'pct_chg_day': pct_chg_day,
            'max_gain': max_gain,
            'max_drawdown': max_drawdown,
            'day1_up': day1_up,
            'first3_max': first3_max,
            'source': source,
        })

    df = pd.DataFrame(features)
    print(f"\n成功分析交易数: {len(df)}")
    print(f"盈利交易: {(df['pnl']>0).sum()} ({(df['pnl']>0).mean()*100:.1f}%)")
    print(f"亏损交易: {(df['pnl']<=0).sum()} ({(df['pnl']<=0).mean()*100:.1f}%)")

    # 分组对比
    win = df[df['pnl']>0]
    lose = df[df['pnl']<=0]

    print("\n" + "="*90)
    print(f"大样本分析：盈利交易({len(win)}) vs 亏损交易({len(lose)}) 特征对比")
    print("="*90)

    feature_cols = ['bb_deviation', 'bb_width', 'ret_5d', 'ret_10d', 'down_days_5',
                    'vol_ratio', 'pct_chg_day', 'max_gain', 'max_drawdown', 'first3_max',
                    'holding_days']

    print(f"\n{'特征':<18} {'盈利均值':>12} {'亏损均值':>12} {'差异':>12} {'t值':>10} {'显著性':>8}")
    print("-"*90)
    for col in feature_cols:
        w_mean = win[col].mean()
        l_mean = lose[col].mean()
        diff = w_mean - l_mean
        w_std = win[col].std()
        l_std = lose[col].std()
        n_w = len(win)
        n_l = len(lose)
        if w_std > 0 and l_std > 0:
            t_stat = diff / np.sqrt(w_std**2/n_w + l_std**2/n_l)
            sig = "***" if abs(t_stat) > 2.5 else ("**" if abs(t_stat) > 1.8 else ("*" if abs(t_stat) > 1.2 else ""))
        else:
            t_stat = 0
            sig = ""
        print(f"{col:<18} {w_mean:>12.3f} {l_mean:>12.3f} {diff:>+12.3f} {t_stat:>10.2f} {sig:>8}")

    # 布尔特征
    print(f"\n{'布尔特征':<18} {'盈利占比':>12} {'亏损占比':>12} {'差异':>12}")
    print("-"*60)
    for col in ['day1_up']:
        w_pct = win[col].mean() * 100
        l_pct = lose[col].mean() * 100
        print(f"{col:<18} {w_pct:>11.1f}% {l_pct:>11.1f}% {w_pct-l_pct:>+11.1f}%")

    # 关键发现：第1天上涨的预测能力
    print(f"\n{'='*90}")
    print("关键发现1：买入后第1天是否上涨")
    print("="*90)
    print(f"\n盈利交易中第1天上涨比例: {win['day1_up'].mean()*100:.1f}%")
    print(f"亏损交易中第1天上涨比例: {lose['day1_up'].mean()*100:.1f}%")

    # 第1天上涨/下跌后的胜率
    day1_win = df[df['day1_up']==True]
    day1_lose = df[df['day1_up']==False]
    print(f"\n第1天上涨的交易: {len(day1_win)}笔, 最终胜率={(day1_win['pnl']>0).mean()*100:.1f}%, 平均盈亏={day1_win['pnl_pct'].mean():.2f}%")
    print(f"第1天下跌的交易: {len(day1_lose)}笔, 最终胜率={(day1_lose['pnl']>0).mean()*100:.1f}%, 平均盈亏={day1_lose['pnl_pct'].mean():.2f}%")

    # 关键发现2：前3天最大涨幅
    print(f"\n{'='*90}")
    print("关键发现2：持仓前3天最大涨幅")
    print("="*90)
    print(f"\n盈利交易前3天最大涨幅: 均值={win['first3_max'].mean():.2f}%, 中位数={win['first3_max'].median():.2f}%")
    print(f"亏损交易前3天最大涨幅: 均值={lose['first3_max'].mean():.2f}%, 中位数={lose['first3_max'].median():.2f}%")

    # 前3天涨幅阈值分析
    for threshold in [1, 2, 3, 5]:
        above = df[df['first3_max']>=threshold]
        below = df[df['first3_max']<threshold]
        if len(above) > 0 and len(below) > 0:
            print(f"\n前3天涨>={threshold}%: {len(above)}笔, 胜率={(above['pnl']>0).mean()*100:.1f}%, 平均盈亏={above['pnl_pct'].mean():.2f}%")
            print(f"前3天涨<{threshold}%:  {len(below)}笔, 胜率={(below['pnl']>0).mean()*100:.1f}%, 平均盈亏={below['pnl_pct'].mean():.2f}%")

    # 关键发现3：买入前10天跌幅
    print(f"\n{'='*90}")
    print("关键发现3：买入前10天跌幅")
    print("="*90)
    for threshold in [-5, -10, -15]:
        below = df[df['ret_10d']<=threshold]
        above = df[df['ret_10d']>threshold]
        if len(below) > 0 and len(above) > 0:
            print(f"\n前10天跌<={threshold}%: {len(below)}笔, 胜率={(below['pnl']>0).mean()*100:.1f}%, 平均盈亏={below['pnl_pct'].mean():.2f}%")
            print(f"前10天跌>{threshold}%:  {len(above)}笔, 胜率={(above['pnl']>0).mean()*100:.1f}%, 平均盈亏={above['pnl_pct'].mean():.2f}%")

    # 关键发现4：布林带宽度
    print(f"\n{'='*90}")
    print("关键发现4：买入时布林带宽度（波动率）")
    print("="*90)
    for threshold in [10, 15, 20]:
        above = df[df['bb_width']>=threshold]
        below = df[df['bb_width']<threshold]
        if len(above) > 0 and len(below) > 0:
            print(f"\n布林带宽度>={threshold}%: {len(above)}笔, 胜率={(above['pnl']>0).mean()*100:.1f}%, 平均盈亏={above['pnl_pct'].mean():.2f}%")
            print(f"布林带宽度<{threshold}%:  {len(below)}笔, 胜率={(below['pnl']>0).mean()*100:.1f}%, 平均盈亏={below['pnl_pct'].mean():.2f}%")

    # 保存
    df.to_csv('results/trade_features_large_sample.csv', index=False)
    print(f"\n大样本特征数据已保存到 results/trade_features_large_sample.csv")

if __name__ == '__main__':
    main()
