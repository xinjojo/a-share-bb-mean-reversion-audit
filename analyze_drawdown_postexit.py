"""
全市场单股回测：持仓期最大回撤 + 卖出后走势分析
================================================
策略（与 bb_lower_upper_full_market.py 完全一致）：
- 收盘复权价 < BB下轨(20,2) 且非跌停 → 买第1层(20万)
- 持仓期再次收盘<下轨 → 加仓(最多5层)
- 盘中复权最高价 >= BB上轨 → 全部卖出
- T+1、跌停不买、100股整数倍、后复权价计算

新增输出：
1. 每笔交易持仓期最大回撤（每日按最低价估值, 影线也算浮亏; 加仓日按加仓前状态算当天浮亏=保守口径）
2. 每笔交易卖出后20个交易日的走势 vs 成本价/卖出价（衡量"卖飞"）
"""
import os, time
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
BB_PERIOD, BB_STD = 20, 2.0
INITIAL_CASH, N_LEVELS, LEVEL_CASH = 1_000_000, 5, 200_000
COMMISSION_RATE, MIN_COMMISSION = 0.00025, 5.0
STAMP_TAX_RATE, TRANSFER_FEE_RATE = 0.0005, 0.00001
START_DATE, END_DATE = '2020-01-01', '2026-08-25'
POST_EXIT_DAYS = 20


def calc_fee_buy(amount):
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * TRANSFER_FEE_RATE


def calc_fee_sell(amount):
    return max(amount * COMMISSION_RATE, MIN_COMMISSION) + amount * STAMP_TAX_RATE + amount * TRANSFER_FEE_RATE


def backtest_single(ts_code, df):
    close_adj = (df['close'] * df['adj_factor']).values
    low_adj = (df['low'] * df['adj_factor']).values
    high_adj = (df['high'] * df['adj_factor']).values
    pre_close = df['pre_close'].values
    close_raw = df['close'].values
    dates = df['date'].values
    ma = pd.Series(close_adj).rolling(BB_PERIOD).mean().values
    std = pd.Series(close_adj).rolling(BB_PERIOD).std().values
    bb_upper = ma + BB_STD * std
    bb_lower = ma - BB_STD * std
    n = len(df)

    cash = INITIAL_CASH
    shares, avg_cost, total_cost, levels = 0, 0.0, 0.0, 0
    buy_idx = -1
    round_no = 0
    round_min_float = 0.0   # 当前回合持仓期最低浮盈率(负=浮亏)
    per_trade = []

    for i in range(n):
        is_limit_down = (pre_close[i] > 0) and (close_raw[i] <= pre_close[i] * 0.905)

        # ===== 持仓期浮盈跟踪(用加仓前状态; 卖出日也算) =====
        if shares > 0 and buy_idx >= 0:
            f = (shares * low_adj[i] - total_cost) / total_cost
            if f < round_min_float:
                round_min_float = f

        # ===== 卖出判断: T+1 + 盘中触及上轨 =====
        if shares > 0 and i > buy_idx and not np.isnan(bb_upper[i]) and high_adj[i] >= bb_upper[i]:
            sell_price = min(bb_upper[i], high_adj[i])   # 上轨成交(APPROX: 日线)
            amount = sell_price * shares
            fee = calc_fee_sell(amount)
            proceeds = amount - fee
            pnl = proceeds - total_cost
            return_pct = pnl / total_cost * 100 if total_cost > 0 else 0
            per_trade.append(dict(ts_code=ts_code, round=round_no,
                                  entry_date=str(dates[buy_idx]), exit_date=str(dates[i]),
                                  hold_days=i - buy_idx, levels_used=levels,
                                  avg_cost=avg_cost, sell_price=sell_price,
                                  pnl=pnl, return_pct=return_pct,
                                  holding_max_drawdown=round_min_float * 100,
                                  entry_i=buy_idx, exit_i=i))
            cash += proceeds
            shares, levels, avg_cost, total_cost = 0, 0, 0.0, 0.0
            round_no += 1
            buy_idx = -1
            round_min_float = 0.0
            continue

        # ===== 买入/加仓 =====
        if levels < N_LEVELS and not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] and not is_limit_down:
            buy_price = close_adj[i]
            qty = int(LEVEL_CASH / buy_price / 100) * 100
            if qty >= 100:
                amount = buy_price * qty
                fee = calc_fee_buy(amount)
                tc = amount + fee
                if tc <= cash:
                    cash -= tc
                    old_cost = shares * avg_cost
                    shares += qty
                    avg_cost = (old_cost + tc) / shares
                    total_cost += tc
                    levels += 1
                    if levels == 1:
                        buy_idx = i
                        round_min_float = 0.0

    # 未平仓按最后收盘结算
    if shares > 0:
        final_price = close_adj[-1]
        amount = final_price * shares
        fee = calc_fee_sell(amount)
        proceeds = amount - fee
        pnl = proceeds - total_cost
        return_pct = pnl / total_cost * 100 if total_cost > 0 else 0
        per_trade.append(dict(ts_code=ts_code, round=round_no,
                              entry_date=str(dates[buy_idx]), exit_date=str(dates[-1]),
                              hold_days=n - 1 - buy_idx, levels_used=levels,
                              avg_cost=avg_cost, sell_price=final_price,
                              pnl=pnl, return_pct=return_pct,
                              holding_max_drawdown=round_min_float * 100,
                              entry_i=buy_idx, exit_i=n - 1))
    return per_trade, df


def main():
    print('加载数据...', flush=True)
    combined = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined[(combined['date'] >= START_DATE) & (combined['date'] <= END_DATE)]
    grouped = {ts: g.sort_values('date') for ts, g in combined.groupby('ts_code')}
    ts_codes = sorted(grouped.keys())
    print(f'开始回测 {len(ts_codes)} 只...', flush=True)

    all_trades = []
    t0 = time.time()
    for k, ts in enumerate(ts_codes):
        df = grouped[ts]
        if len(df) < BB_PERIOD + 10:
            continue
        per_trade, df = backtest_single(ts, df)
        for t in per_trade:
            xi = t.pop('exit_i'); ei = t.pop('entry_i')
            # 卖出后走势(未来 POST_EXIT_DAYS 个交易日)
            post = df.iloc[xi + 1: xi + 1 + POST_EXIT_DAYS]
            cost, sellp = t['avg_cost'], t['sell_price']
            if len(post) > 0 and cost > 0:
                post_high = (post['high'] * post['adj_factor']).max()
                post_close_last = (post['close'] * post['adj_factor']).iloc[-1]
                post_min_low = (post['low'] * post['adj_factor']).min()
                t['post_high_vs_cost_pct'] = (post_high / cost - 1) * 100
                t['post_close_vs_cost_pct'] = (post_close_last / cost - 1) * 100
                t['post_below_cost'] = int(post_min_low < cost)
                t['post_high_vs_sell_pct'] = (post_high / sellp - 1) * 100 if sellp > 0 else np.nan
            else:
                t['post_high_vs_cost_pct'] = np.nan
                t['post_close_vs_cost_pct'] = np.nan
                t['post_below_cost'] = np.nan
                t['post_high_vs_sell_pct'] = np.nan
            all_trades.append(t)
        if (k + 1) % 1000 == 0:
            print(f'  {k+1}/{len(ts_codes)} {time.time()-t0:.0f}s', flush=True)

    tr = pd.DataFrame(all_trades)
    out = os.path.join(PROJECT_ROOT, 'results', 'drawdown_postexit_per_trade.csv')
    tr.to_csv(out, index=False)
    print(f'\n共 {len(tr)} 笔交易, 已存 {out}', flush=True)

    # ===== 统计1: 持仓期最大回撤分布 =====
    dd = tr['holding_max_drawdown'].dropna()
    print('\n===== 1. 持仓期最大回撤分布(每笔交易, 最低价口径) =====')
    print(f'交易笔数: {len(dd)}')
    print(f'均值: {dd.mean():.2f}% | 中位数: {dd.median():.2f}% | 标准差: {dd.std():.2f}%')
    print(f'最小值: {dd.min():.2f}% | 最大值: {dd.max():.2f}%')
    print('百分位: ' + ' | '.join(f'p{p}={dd.quantile(p/100):.2f}%' for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]))
    print(f'全程无浮亏(回撤>=0)的笔数: {(dd>=0).sum()} ({(dd>=0).mean()*100:.1f}%)')

    print('\n--- 按持仓期最大回撤分档 ---')
    bins = [-1e9, -30, -20, -10, -5, -2, 0, 1e9]
    labels = ['<-30%', '-30~-20%', '-20~-10%', '-10~-5%', '-5~-2%', '-2~0%', '>=0']
    tr['dd_bucket'] = pd.cut(tr['holding_max_drawdown'], bins=bins, labels=labels)
    grp = tr.groupby('dd_bucket', observed=True).agg(
        笔数=('pnl', 'size'), 占比=('pnl', lambda x: len(x) / len(tr) * 100),
        平均收益_pct=('return_pct', 'mean'), 胜率=('return_pct', lambda x: (x > 0).mean() * 100),
        平均持仓天=('hold_days', 'mean'))
    print(grp.round(2).to_string())

    print('\n--- 按最终层数分类 ---')
    grp2 = tr.groupby('levels_used').agg(
        笔数=('pnl', 'size'), 占比=('pnl', lambda x: len(x) / len(tr) * 100),
        平均回撤=('holding_max_drawdown', 'mean'), 回撤中位数=('holding_max_drawdown', 'median'),
        平均收益_pct=('return_pct', 'mean'), 胜率=('return_pct', lambda x: (x > 0).mean() * 100),
        平均持仓天=('hold_days', 'mean'))
    print(grp2.round(2).to_string())

    print('\n--- 按持仓天数分类 ---')
    bins2 = [-1, 1, 2, 3, 5, 10, 20, 50, 1e9]
    labels2 = ['1天', '2天', '3天', '4-5天', '6-10天', '11-20天', '21-50天', '>50天']
    tr['hd_bucket'] = pd.cut(tr['hold_days'], bins=bins2, labels=labels2)
    grp3 = tr.groupby('hd_bucket', observed=True).agg(
        笔数=('pnl', 'size'), 平均回撤=('holding_max_drawdown', 'mean'),
        平均收益_pct=('return_pct', 'mean'), 胜率=('return_pct', lambda x: (x > 0).mean() * 100))
    print(grp3.round(2).to_string())

    # ===== 统计2: 卖出后走势 =====
    print('\n===== 2. 卖出后20个交易日走势 vs 成本价/卖出价 =====')
    pv = tr['post_high_vs_cost_pct'].dropna()
    sv = tr['post_high_vs_sell_pct'].dropna()
    print(f'有效样本: {len(pv)} (不足20日观察窗口的已剔除)')
    print(f'卖出后20日最高相对成本: 均值{pv.mean():.1f}% 中位数{pv.median():.1f}% '
          f'p25={pv.quantile(.25):.1f}% p75={pv.quantile(.75):.1f}% p95={pv.quantile(.95):.1f}%')
    print(f'卖出后最高超过卖出价(卖飞)比例: {(sv>0).mean()*100:.1f}%')
    print(f'卖出后最高相对成本>5%: {(pv>5).mean()*100:.1f}% | >10%: {(pv>10).mean()*100:.1f}% | >20%: {(pv>20).mean()*100:.1f}% | >30%: {(pv>30).mean()*100:.1f}%')
    print(f'卖出后曾跌破成本价比例: {tr["post_below_cost"].dropna().mean()*100:.1f}%')

    print('\n--- 卖出后20日最高相对成本分档 ---')
    bins3 = [-1e9, 0, 5, 10, 20, 30, 1e9]
    labels3 = ['未超过成本', '0~5%', '5~10%', '10~20%', '20~30%', '>30%']
    tr['post_bucket'] = pd.cut(tr['post_high_vs_cost_pct'], bins=bins3, labels=labels3)
    valid = tr.dropna(subset=['post_high_vs_cost_pct'])
    grp4 = valid.groupby('post_bucket', observed=True).agg(
        笔数=('pnl', 'size'), 占比=('pnl', lambda x: len(x) / len(valid) * 100),
        平均收益_pct=('return_pct', 'mean'), 卖飞比例=('post_high_vs_sell_pct', lambda x: (x > 0).mean() * 100))
    print(grp4.round(2).to_string())


if __name__ == '__main__':
    main()
