"""
分析盈利交易 vs 亏损交易的特征差异
目标：找出可以用来过滤亏损交易的信号
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np
from data_loader.storage import DataStorage

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    storage = DataStorage(os.path.join(project_root, 'data', 'raw'))

    # 加载从大到小版本的交易记录（效果更好的版本）
    trades = pd.read_csv('results/trades/trades_tp2_ts20_zz500_desc_top3_p3_20260827_141934.csv')
    sell_trades = trades[trades['action']=='SELL'].copy()

    print(f"总卖出交易: {len(sell_trades)}")
    print(f"止盈交易: {(sell_trades['reason']=='TAKE_PROFIT').sum()}")
    print(f"时间止损交易: {(sell_trades['reason']=='TIME_STOP').sum()}")

    # 对每笔交易，回溯买入时的特征
    features = []
    for _, row in sell_trades.iterrows():
        ts = row['ts_code']
        sell_date = pd.to_datetime(row['date'])
        holding_trays = int(row['holding_trays'])

        # 找到对应的买入交易（同一股票，在卖出之前）
        buy_trades = trades[(trades['action']=='BUY') & (trades['ts_code']==ts) &
                            (pd.to_datetime(trades['date']) <= sell_date)]
        if len(buy_trades) == 0:
            continue
        # 取第一笔买入（初始建仓）
        first_buy = buy_trades.iloc[0]
        buy_date = pd.to_datetime(first_buy['date'])
        buy_price = first_buy['price']

        # 加载该股票数据
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

        # 找到买入日在数据中的位置
        if buy_date not in merged.index:
            continue
        buy_idx = merged.index.get_loc(buy_date)

        # 计算布林带
        merged['bb_mid'] = merged['adj_close'].rolling(20).mean()
        merged['bb_std'] = merged['adj_close'].rolling(20).std()
        merged['bb_upper'] = merged['bb_mid'] + 2 * merged['bb_std']
        merged['bb_lower'] = merged['bb_mid'] - 2 * merged['bb_std']
        merged['bb_width'] = (merged['bb_upper'] - merged['bb_lower']) / merged['bb_mid']
        merged['pct_chg'] = merged['close'].pct_change() * 100
        merged['vol_ma5'] = merged['vol'].rolling(5).mean()
        merged['vol_ratio'] = merged['vol'] / merged['vol_ma5']

        buy_row = merged.iloc[buy_idx]

        # 特征1：BB Lower偏离程度（收盘价低于下轨多少百分比）
        bb_deviation = (buy_row['adj_close'] - buy_row['bb_lower']) / buy_row['bb_lower'] * 100

        # 特征2：布林带宽度（波动率）
        bb_width = buy_row['bb_width'] * 100

        # 特征3：买入前5天涨跌幅
        if buy_idx >= 5:
            ret_5d = (merged.iloc[buy_idx]['adj_close'] / merged.iloc[buy_idx-5]['adj_close'] - 1) * 100
        else:
            ret_5d = np.nan

        # 特征4：买入前10天涨跌幅
        if buy_idx >= 10:
            ret_10d = (merged.iloc[buy_idx]['adj_close'] / merged.iloc[buy_idx-10]['adj_close'] - 1) * 100
        else:
            ret_10d = np.nan

        # 特征5：买入前5天中有几天下跌
        if buy_idx >= 5:
            down_days_5 = (merged.iloc[buy_idx-4:buy_idx+1]['pct_chg'] < 0).sum()
        else:
            down_days_5 = np.nan

        # 特征6：成交量比率（相对5日均量）
        vol_ratio = buy_row['vol_ratio']

        # 特征7：买入当天涨跌幅
        pct_chg_day = buy_row['pct_chg']

        # 特征8：买入时是否跌停附近（跌幅超过8%）
        near_limit_down = buy_row['pct_chg'] < -8

        # 特征9：持仓期间最大浮盈
        if buy_idx + holding_trays < len(merged):
            hold_data = merged.iloc[buy_idx:buy_idx+holding_trays+1]
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
            'reason': row['reason'],
            'pnl': row['pnl'],
            'pnl_pct': row['pnl'] / (row['shares'] * buy_price) * 100,
            'holding_trays': holding_trays,
            'bb_deviation': bb_deviation,
            'bb_width': bb_width,
            'ret_5d': ret_5d,
            'ret_10d': ret_10d,
            'down_days_5': down_days_5,
            'vol_ratio': vol_ratio,
            'pct_chg_day': pct_chg_day,
            'near_limit_down': near_limit_down,
            'max_gain': max_gain,
            'max_drawdown': max_drawdown,
            'day1_up': day1_up,
            'first3_max': first3_max,
        })

    df = pd.DataFrame(features)
    print(f"\n成功分析交易数: {len(df)}")

    # 分组对比
    tp = df[df['reason']=='TAKE_PROFIT']
    ts = df[df['reason']=='TIME_STOP']

    print("\n" + "="*80)
    print("盈利交易(止盈2%) vs 亏损交易(时间止损20天) 特征对比")
    print("="*80)

    feature_cols = ['bb_deviation', 'bb_width', 'ret_5d', 'ret_10d', 'down_days_5',
                    'vol_ratio', 'pct_chg_day', 'max_gain', 'max_drawdown', 'first3_max']

    print(f"\n{'特征':<18} {'止盈均值':>12} {'止损均值':>12} {'差异':>12} {'显著性':>10}")
    print("-"*80)
    for col in feature_cols:
        tp_mean = tp[col].mean()
        ts_mean = ts[col].mean()
        diff = tp_mean - ts_mean
        # 简单的t检验近似
        tp_std = tp[col].std()
        ts_std = ts[col].std()
        n_tp = len(tp)
        n_ts = len(ts)
        if tp_std > 0 and ts_std > 0:
            t_stat = diff / np.sqrt(tp_std**2/n_tp + ts_std**2/n_ts)
            sig = "***" if abs(t_stat) > 2.5 else ("**" if abs(t_stat) > 1.8 else ("*" if abs(t_stat) > 1.2 else ""))
        else:
            sig = ""
        print(f"{col:<18} {tp_mean:>12.3f} {ts_mean:>12.3f} {diff:>+12.3f} {sig:>10}")

    # 布尔特征对比
    print(f"\n{'布尔特征':<18} {'止盈占比':>12} {'止损占比':>12}")
    print("-"*50)
    for col in ['near_limit_down', 'day1_up']:
        tp_pct = tp[col].mean() * 100
        ts_pct = ts[col].mean() * 100
        print(f"{col:<18} {tp_pct:>11.1f}% {ts_pct:>11.1f}%")

    # 关键发现：前3天最大涨幅
    print(f"\n{'='*80}")
    print("关键发现：持仓前3天最大涨幅分布")
    print("="*80)
    print(f"\n止盈交易前3天最大涨幅:")
    print(f"  均值: {tp['first3_max'].mean():.2f}%")
    print(f"  中位数: {tp['first3_max'].median():.2f}%")
    print(f"  <2%的比例: {(tp['first3_max']<2).mean()*100:.1f}%")
    print(f"  >=2%的比例: {(tp['first3_max']>=2).mean()*100:.1f}%")

    print(f"\n止损交易前3天最大涨幅:")
    print(f"  均值: {ts['first3_max'].mean():.2f}%")
    print(f"  中位数: {ts['first3_max'].median():.2f}%")
    print(f"  <2%的比例: {(ts['first3_max']<2).mean()*100:.1f}%")
    print(f"  >=2%的比例: {(ts['first3_max']>=2).mean()*100:.1f}%")

    # 第1天是否上涨
    print(f"\n{'='*80}")
    print("关键发现：买入后第1天是否上涨")
    print("="*80)
    print(f"\n止盈交易: 第1天上涨比例 = {(tp['day1_up']==True).mean()*100:.1f}%")
    print(f"止损交易: 第1天上涨比例 = {(ts['day1_up']==True).mean()*100:.1f}%")

    # 买入时BB偏离程度分布
    print(f"\n{'='*80}")
    print("买入时BB Lower偏离程度分布（负值=低于下轨）")
    print("="*80)
    bins = [-999, -5, -3, -1, 0, 1, 999]
    labels = ['<-5%', '-5~-3%', '-3~-1%', '-1~0%', '0~1%', '>1%']
    tp['bb_bin'] = pd.cut(tp['bb_deviation'], bins=bins, labels=labels)
    ts['bb_bin'] = pd.cut(ts['bb_deviation'], bins=bins, labels=labels)
    print(f"\n{'偏离区间':<12} {'止盈数':>8} {'止盈占比':>10} {'止损数':>8} {'止损占比':>10}")
    print("-"*60)
    for label in labels:
        tp_cnt = (tp['bb_bin']==label).sum()
        ts_cnt = (ts['bb_bin']==label).sum()
        tp_pct = tp_cnt / len(tp) * 100 if len(tp) > 0 else 0
        ts_pct = ts_cnt / len(ts) * 100 if len(ts) > 0 else 0
        print(f"{label:<12} {tp_cnt:>8} {tp_pct:>9.1f}% {ts_cnt:>8} {ts_pct:>9.1f}%")

    # 保存特征数据
    df.to_csv('results/trade_features_analysis.csv', index=False)
    print(f"\n特征数据已保存到 results/trade_features_analysis.csv")

if __name__ == '__main__':
    main()
