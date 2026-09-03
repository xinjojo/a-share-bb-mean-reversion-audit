#!/usr/bin/env python3
"""持仓时间分析：持仓天数分布、与胜率/盈亏比的关系、时间止损评估。"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from analysis.trade_review import TradeReviewAnalyzer


def analyze_holding_period(trades_path: str):
    trades = pd.read_csv(trades_path).to_dict('records')
    reviewer = TradeReviewAnalyzer(trades)
    round_trips = reviewer._build_round_trips()

    print(f"总完整交易数: {len(round_trips)}")
    print("=" * 100)

    # 1. 持仓时间分布
    holding_days = [rt['holding_days'] for rt in round_trips]
    print("\n【持仓时间分布】")
    print(f"  平均持仓: {np.mean(holding_days):.1f} 天")
    print(f"  中位数持仓: {np.median(holding_days):.1f} 天")
    print(f"  最短: {min(holding_days)} 天")
    print(f"  最长: {max(holding_days)} 天")
    print(f"  标准差: {np.std(holding_days):.1f} 天")

    # 按区间分布
    bins = [(1, 3), (4, 7), (8, 14), (15, 30), (31, 60), (61, 999)]
    print(f"\n  {'持仓区间':<12} {'交易数':>6} {'占比':>8} {'胜率':>8} {'平均盈亏%':>10} {'盈亏比':>8}")
    print("  " + "-" * 70)
    for lo, hi in bins:
        group = [rt for rt in round_trips if lo <= rt['holding_days'] <= hi]
        if not group:
            continue
        wins = [rt for rt in group if rt['pnl'] > 0]
        losses = [rt for rt in group if rt['pnl'] <= 0]
        win_rate = len(wins) / len(group) * 100
        avg_pnl = np.mean([rt['pnl_pct'] for rt in group])
        avg_win = np.mean([rt['pnl_pct'] for rt in wins]) if wins else 0
        avg_loss = np.mean([rt['pnl_pct'] for rt in losses]) if losses else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        label = f"{lo}-{hi}天" if hi < 999 else f"{lo}天以上"
        print(f"  {label:<12} {len(group):>6} {len(group)/len(round_trips)*100:>7.1f}% "
              f"{win_rate:>7.1f}% {avg_pnl:>+9.2f}% {profit_factor:>7.2f}")

    # 2. 持仓时间 vs 盈亏散点（按区间详细）
    print("\n" + "=" * 100)
    print("【持仓时间 vs 盈亏详细分析】")
    print("=" * 100)

    # 按持仓天数精确分组
    day_groups = {}
    for rt in round_trips:
        d = rt['holding_days']
        if d not in day_groups:
            day_groups[d] = []
        day_groups[d].append(rt)

    print(f"\n  {'持仓天数':>8} {'交易数':>6} {'胜率':>8} {'平均盈亏%':>10} {'平均盈利%':>10} {'平均亏损%':>10}")
    print("  " + "-" * 70)
    for d in sorted(day_groups.keys()):
        group = day_groups[d]
        wins = [rt for rt in group if rt['pnl'] > 0]
        losses = [rt for rt in group if rt['pnl'] <= 0]
        win_rate = len(wins) / len(group) * 100
        avg_pnl = np.mean([rt['pnl_pct'] for rt in group])
        avg_win = np.mean([rt['pnl_pct'] for rt in wins]) if wins else 0
        avg_loss = np.mean([rt['pnl_pct'] for rt in losses]) if losses else 0
        print(f"  {d:>8} {len(group):>6} {win_rate:>7.1f}% {avg_pnl:>+9.2f}% "
              f"{avg_win:>+9.2f}% {avg_loss:>+9.2f}%")

    # 3. 时间止损模拟
    print("\n" + "=" * 100)
    print("【时间止损模拟】")
    print("=" * 100)
    print("假设：持仓超过N天后，如果还没止盈，就在第N天收盘价强制卖出")
    print()

    for max_days in [5, 7, 10, 14, 20, 30]:
        # 模拟：持仓<=max_days的交易不变，持仓>max_days的交易在第max_days天卖出
        # 由于我们没有每天的价格数据，这里用近似：假设超过max_days的交易盈亏按比例缩减
        # 更准确的做法是重新回测，但这里先做近似分析

        affected = [rt for rt in round_trips if rt['holding_days'] > max_days]
        not_affected = [rt for rt in round_trips if rt['holding_days'] <= max_days]

        if not affected:
            print(f"  时间止损={max_days}天: 无交易受影响")
            continue

        # 近似：假设超过max_days的交易，在第max_days天时的盈亏 = 总盈亏 × (max_days / holding_days)
        # 这是一个粗略近似，实际需要重新回测
        simulated_pnl = []
        for rt in not_affected:
            simulated_pnl.append(rt['pnl'])
        for rt in affected:
            # 近似：线性插值
            approx_pnl = rt['pnl'] * (max_days / rt['holding_days'])
            simulated_pnl.append(approx_pnl)

        total_pnl = sum(simulated_pnl)
        wins_sim = [p for p in simulated_pnl if p > 0]
        losses_sim = [p for p in simulated_pnl if p <= 0]
        win_rate_sim = len(wins_sim) / len(simulated_pnl) * 100 if simulated_pnl else 0

        print(f"  时间止损={max_days:>2}天: 影响{len(affected):>3}笔交易 "
              f"({len(affected)/len(round_trips)*100:.1f}%) "
              f"模拟总盈亏{total_pnl:+,.0f}元 胜率{win_rate_sim:.1f}% "
              f"(原总盈亏{sum(rt['pnl'] for rt in round_trips):+,.0f}元)")

    # 4. 资金利用率分析
    print("\n" + "=" * 100)
    print("【资金利用率分析】")
    print("=" * 100)

    total_holding_days = sum(holding_days)
    total_calendar_days = 1611  # 2020-2026交易日数
    avg_position_per_trade = np.mean([rt.get('max_level', 1) for rt in round_trips])

    # 资金占用 = 每笔交易持仓天数 × 平均仓位
    total_capital_days = sum(rt['holding_days'] * rt.get('max_level', 1) * 0.2 for rt in round_trips)
    capital_utilization = total_capital_days / total_calendar_days * 100

    print(f"  总交易日数: {total_calendar_days}")
    print(f"  总持仓天数(所有交易累加): {total_holding_days}")
    print(f"  平均每笔持仓: {np.mean(holding_days):.1f} 天")
    print(f"  平均加仓层数: {avg_position_per_trade:.1f} 层")
    print(f"  资金占用(仓位×天数): {total_capital_days:.0f} 仓位·天")
    print(f"  资金利用率: {capital_utilization:.1f}%")
    print(f"  空仓时间占比: {100 - capital_utilization:.1f}%")

    # 5. 长持仓交易明细（持仓>14天）
    print("\n" + "=" * 100)
    print("【长持仓交易明细（持仓>14天）】")
    print("=" * 100)
    long_holds = [rt for rt in round_trips if rt['holding_days'] > 14]
    long_holds.sort(key=lambda x: x['holding_days'], reverse=True)
    print(f"  共{len(long_holds)}笔交易持仓超过14天")
    print(f"\n  {'排名':>4} {'股票':<12} {'买入日期':<12} {'卖出日期':<12} {'持仓天数':>8} "
          f"{'层数':>4} {'盈亏%':>8} {'盈亏金额':>10} {'退出原因':<15}")
    print("  " + "-" * 110)
    for i, rt in enumerate(long_holds[:20], 1):
        print(f"  {i:>4} {rt['symbol']:<12} {str(rt['entry_date'].date()):<12} "
              f"{str(rt['exit_date'].date()):<12} {rt['holding_days']:>8} "
              f"{rt.get('max_level', 1):>4} {rt['pnl_pct']:>+7.2f}% "
              f"{rt['pnl']:>+9,.0f} {rt.get('exit_reason', 'N/A'):<15}")

    return round_trips


if __name__ == '__main__':
    trades_path = 'results/trades/trades_20260826_011422.csv'
    analyze_holding_period(trades_path)
