"""
全市场BB下轨买/上轨卖 策略 —— 导出全部交易明细（回合级）

与 bb_lower_upper_full_market.py 使用完全相同的策略参数与交易逻辑：
- 初始资金100万，每层20万（1/5），最多5层
- 买入信号：收盘复权价 < 布林带下轨（20,2）→ 买一层
- 加仓：后续交易日再次收盘<下轨 → 加一层，最多5层
- 卖出信号：盘中复权最高价 >= 布林带上轨 → 全部卖出（T+1：买入当日不可卖）
- 跌停日不买入、100股整数倍、买不起100股跳过
- 后复权价格（close*adj_factor）计算
- 费用：佣金0.025%最低5元、印花税0.05%卖出收、过户费0.001%

本脚本仅额外输出每笔交易回合的完整进出明细，不改变任何交易判定。
输出：
  1. results/trades_all_rounds.csv          —— 全部交易回合明细（按入场日期排序）
  2. results/trades_all_rounds_summary.csv  —— 每年/每股票汇总统计
  3. 一致性校验：与 bb_lower_upper_full_market.csv 逐只对比 n_rounds / total_return
"""
import os, time
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

BB_PERIOD = 20
BB_STD = 2.0
INITIAL_CASH = 1_000_000
N_LEVELS = 5
LEVEL_CASH = INITIAL_CASH / N_LEVELS
COMMISSION_RATE = 0.00025
MIN_COMMISSION = 5.0
STAMP_TAX_RATE = 0.0005
TRANSFER_FEE_RATE = 0.00001
START_DATE = '2020-01-01'
END_DATE = '2026-08-25'


def calc_fee_buy(amount):
    commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)
    transfer = amount * TRANSFER_FEE_RATE
    return commission + transfer


def calc_fee_sell(amount):
    commission = max(amount * COMMISSION_RATE, MIN_COMMISSION)
    stamp = amount * STAMP_TAX_RATE
    transfer = amount * TRANSFER_FEE_RATE
    return commission + stamp + transfer


def _make_round(ts_code, round_no, dates, cur_buys, levels, shares, avg_cost,
                sell_idx, sell_price, sell_amount, sell_fee, proceeds, pnl, return_pct, exit_type):
    """把一个交易回合整理为一行明细"""
    first = cur_buys[0]
    add_count = levels - 1
    add_dates = ';'.join(b['date'] for b in cur_buys[1:]) if add_count > 0 else ''
    breakdown = ';'.join(f"{b['date']}@{b['price']:.2f}x{b['qty']}层{b['level']}" for b in cur_buys)
    total_buy_amount = sum(b['amount'] for b in cur_buys)
    total_buy_fee = sum(b['fee'] for b in cur_buys)
    return {
        'ts_code': ts_code,
        'round_no': round_no,
        'entry_date': first['date'],
        'entry_price': first['price'],
        'add_count': add_count,
        'add_dates': add_dates,
        'levels_used': levels,
        'total_shares': shares,
        'avg_cost': avg_cost,
        'total_buy_amount': total_buy_amount,
        'total_buy_fee': total_buy_fee,
        'buy_breakdown': breakdown,
        'exit_date': str(dates[sell_idx]),
        'exit_price': sell_price,
        'exit_type': exit_type,
        'sell_amount': sell_amount,
        'sell_fee': sell_fee,
        'net_proceeds': proceeds,
        'pnl': pnl,
        'return_pct': return_pct,
        'hold_days': sell_idx - first['idx'],
    }


def backtest_single_detailed(ts_code, df):
    """对单只股票执行BB下轨买/上轨卖策略，返回全部回合明细"""
    close_adj = (df['close'] * df['adj_factor']).values
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
    shares = 0
    avg_cost = 0.0
    levels = 0
    buy_idx = -1
    round_no = 0
    trades = []
    cur_buys = []          # 当前回合累计买入记录

    for i in range(n):
        is_limit_down = (pre_close[i] > 0) and (close_raw[i] <= pre_close[i] * 0.905)

        # ===== 卖出：持仓 + 非买入当天(T+1) + 盘中触及上轨 =====
        if shares > 0 and i > buy_idx and not np.isnan(bb_upper[i]) and high_adj[i] >= bb_upper[i]:
            sell_price = min(bb_upper[i], high_adj[i])
            amount = sell_price * shares
            fee = calc_fee_sell(amount)
            proceeds = amount - fee
            cost_amount = avg_cost * shares
            pnl = proceeds - cost_amount
            return_pct = pnl / cost_amount * 100 if cost_amount > 0 else 0.0
            trades.append(_make_round(ts_code, round_no, dates, cur_buys, levels, shares, avg_cost,
                                      i, sell_price, amount, fee, proceeds, pnl, return_pct, 'TAKE_PROFIT_UB'))
            cash += proceeds
            shares = 0
            levels = 0
            avg_cost = 0.0
            round_no += 1
            buy_idx = -1
            cur_buys = []
            continue  # 卖出当日不再买入

        # ===== 买入：收盘<下轨 + 非跌停 + 未满仓 =====
        if not np.isnan(bb_lower[i]) and close_adj[i] < bb_lower[i] and not is_limit_down:
            if levels < N_LEVELS:
                buy_price = close_adj[i]
                qty = int(LEVEL_CASH / buy_price / 100) * 100
                if qty >= 100:
                    amount = buy_price * qty
                    fee = calc_fee_buy(amount)
                    total_cost = amount + fee
                    if total_cost <= cash:
                        cash -= total_cost
                        old_cost = shares * avg_cost
                        shares += qty
                        avg_cost = (old_cost + total_cost) / shares
                        levels += 1
                        if levels == 1:   # 新回合第一次买入
                            buy_idx = i
                        cur_buys.append({'idx': i, 'date': str(dates[i]), 'price': buy_price, 'qty': qty,
                                         'amount': amount, 'fee': fee, 'level': levels})

    # ===== 未平仓按最后收盘价结算 =====
    if shares > 0:
        final_price = close_adj[-1]
        amount = final_price * shares
        fee = calc_fee_sell(amount)
        proceeds = amount - fee
        cost_amount = avg_cost * shares
        pnl = proceeds - cost_amount
        return_pct = pnl / cost_amount * 100 if cost_amount > 0 else 0.0
        trades.append(_make_round(ts_code, round_no, dates, cur_buys, levels, shares, avg_cost,
                                  n - 1, final_price, amount, fee, proceeds, pnl, return_pct, 'FINAL_SETTLE'))

    return trades


def main():
    t0 = time.time()
    print('加载数据...', flush=True)
    combined = pd.read_parquet(os.path.join(PROJECT_ROOT, 'data', 'combined_daily.parquet'))
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined[(combined['date'] >= START_DATE) & (combined['date'] <= END_DATE)]

    basic = pd.read_csv(os.path.join(PROJECT_ROOT, 'data', 'raw', 'stock_basic.csv'))
    mv = pd.read_csv(os.path.join(PROJECT_ROOT, 'data', 'raw', 'daily_basic_20241231.csv'))
    mv['total_mv_yi'] = mv['total_mv'] / 10000
    info = basic[['ts_code', 'name', 'industry', 'market', 'list_date']].merge(
        mv[['ts_code', 'total_mv_yi']], on='ts_code', how='left')
    info_map = info.set_index('ts_code').to_dict('index')

    ts_codes = sorted(combined['ts_code'].unique())
    print(f'开始回测 {len(ts_codes)} 只股票...', flush=True)
    grouped = {ts: g.sort_values('date') for ts, g in combined.groupby('ts_code')}

    all_trades = []
    stock_summary = []
    t1 = time.time()
    for idx, ts in enumerate(ts_codes):
        df = grouped[ts]
        if len(df) < BB_PERIOD + 10:
            continue
        try:
            trades = backtest_single_detailed(ts, df)
            # 汇总本股票统计
            if trades:
                pnls = np.array([t['pnl'] for t in trades])
                rets = np.array([t['return_pct'] for t in trades])
                stock_summary.append({
                    'ts_code': ts,
                    'n_rounds': len(trades),
                    'total_pnl': pnls.sum(),
                    'total_return': rets.mean(),   # 平均每回合收益率
                    'avg_ret': rets.mean(),
                    'med_ret': np.median(rets),
                    'win_rate': (pnls > 0).mean() * 100,
                })
            for t in trades:
                m = info_map.get(ts, {})
                t['name'] = m.get('name', '')
                t['industry'] = m.get('industry', '')
                t['market'] = m.get('market', '')
                t['total_mv_yi'] = m.get('total_mv_yi', np.nan)
                all_trades.append(t)
        except Exception as e:
            print(f'  {ts} 回测失败: {e}', flush=True)

        if (idx + 1) % 1000 == 0:
            print(f'  进度 {idx+1}/{len(ts_codes)}, 耗时{time.time()-t1:.0f}s', flush=True)

    print(f'回测完成, {len(all_trades)} 笔交易, 耗时{time.time()-t0:.0f}s', flush=True)

    df_trades = pd.DataFrame(all_trades)
    # 以时间为轴排序（按入场日期）
    df_trades = df_trades.sort_values(['entry_date', 'ts_code']).reset_index(drop=True)
    # 年份列
    df_trades['entry_year'] = df_trades['entry_date'].str[:4]
    df_trades['exit_year'] = df_trades['exit_date'].str[:4]

    # 列顺序整理
    cols = ['ts_code', 'name', 'industry', 'market', 'total_mv_yi',
            'round_no', 'entry_date', 'entry_price', 'entry_year',
            'add_count', 'add_dates', 'levels_used',
            'total_shares', 'avg_cost', 'total_buy_amount', 'total_buy_fee', 'buy_breakdown',
            'exit_date', 'exit_year', 'exit_price', 'exit_type',
            'sell_amount', 'sell_fee', 'net_proceeds',
            'pnl', 'return_pct', 'hold_days']
    df_trades = df_trades[cols]

    out1 = os.path.join(PROJECT_ROOT, 'results', 'trades_all_rounds.csv')
    df_trades.to_csv(out1, index=False)
    print(f'交易明细已保存: {out1}  ({len(df_trades)}行)', flush=True)

    # ===== 一致性校验：与原汇总CSV对比 =====
    print('\n===== 一致性校验 =====', flush=True)
    orig = pd.read_csv(os.path.join(PROJECT_ROOT, 'results', 'bb_lower_upper_full_market.csv'))
    merged = orig[['ts_code', 'n_rounds']].merge(
        pd.DataFrame(stock_summary)[['ts_code', 'n_rounds', 'total_return']],
        on='ts_code', how='inner', suffixes=('_orig', '_new'))
    diff_rounds = (merged['n_rounds_orig'] != merged['n_rounds_new']).sum()
    print(f'对比股票数: {len(merged)}', flush=True)
    print(f'回合数不一致的股票数: {diff_rounds}', flush=True)
    if diff_rounds > 0:
        print(merged[merged['n_rounds_orig'] != merged['n_rounds_new']].head(10).to_string(), flush=True)

    # ===== 汇总统计 =====
    print('\n===== 全市场交易汇总 =====', flush=True)
    print(f'总交易回合数: {len(df_trades)}', flush=True)
    print(f'盈利回合: {(df_trades["pnl"]>0).sum()} ({(df_trades["pnl"]>0).mean()*100:.1f}%)', flush=True)
    print(f'平均收益率: {df_trades["return_pct"].mean():+.2f}%', flush=True)
    print(f'中位数收益率: {df_trades["return_pct"].median():+.2f}%', flush=True)
    print(f'平均持仓天数: {df_trades["hold_days"].mean():.1f}', flush=True)
    print(f'平均层数: {df_trades["levels_used"].mean():.2f}', flush=True)

    # 按年份统计
    yearly = df_trades.groupby('entry_year').agg(
        交易数=('pnl', 'size'),
        胜率=('pnl', lambda x: (x > 0).mean() * 100),
        平均收益率=('return_pct', 'mean'),
        平均持仓天数=('hold_days', 'mean'),
        平均层数=('levels_used', 'mean'),
    ).reset_index()
    print('\n--- 按入场年份统计 ---', flush=True)
    print(yearly.to_string(index=False), flush=True)

    # 按退出类型统计
    print('\n--- 按退出类型统计 ---', flush=True)
    by_exit = df_trades.groupby('exit_type').agg(
        交易数=('pnl', 'size'),
        胜率=('pnl', lambda x: (x > 0).mean() * 100),
        平均收益率=('return_pct', 'mean'),
    ).reset_index()
    print(by_exit.to_string(index=False), flush=True)

    # 按层数统计
    print('\n--- 按最终层数统计 ---', flush=True)
    by_level = df_trades.groupby('levels_used').agg(
        交易数=('pnl', 'size'),
        胜率=('pnl', lambda x: (x > 0).mean() * 100),
        平均收益率=('return_pct', 'mean'),
        平均持仓天数=('hold_days', 'mean'),
    ).reset_index()
    print(by_level.to_string(index=False), flush=True)

    # 保存按年汇总
    out2 = os.path.join(PROJECT_ROOT, 'results', 'trades_all_rounds_summary.csv')
    yearly.to_csv(out2, index=False)
    print(f'\n汇总已保存: {out2}', flush=True)


if __name__ == '__main__':
    main()
