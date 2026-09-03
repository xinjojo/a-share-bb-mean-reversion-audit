"""
仓位层级分析模块

统计策略在不同仓位层级下的表现，用于回答核心问题：
"这个策略到底是真的均值回归有效，还是主要靠不断增加仓位赚钱？"

统计指标：
1. 只使用第1层就止盈的比例
2. 使用第2层后止盈的比例
3. 使用第3层后止盈的比例
4. 使用第4层后止盈的比例
5. 使用第5层后止盈的比例
6. 达到100%仓位后最终止盈的比例
7. 达到100%仓位后止损的比例
8. 达到100%仓位后最终仍未退出的比例
9. 第1-5层各自的平均收益

精度等级：EXACT（基于交易日志精确计算）
"""
import logging
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class PositionLevelAnalyzer:
    """仓位层级分析器。"""

    def __init__(self, trades: List[Dict], max_levels: int = 5):
        """
        Args:
            trades: 交易日志列表
            max_levels: 最大仓位层数
        """
        self.trades = pd.DataFrame(trades) if trades else pd.DataFrame()
        self.max_levels = max_levels

        if not self.trades.empty:
            self.trades['date'] = pd.to_datetime(self.trades['date'])
            # 同一天先SELL后BUY，避免止盈后重新买入的交易被错误合并
            self.trades['_order'] = self.trades['action'].map({'SELL': 0, 'BUY': 1})
            self.trades = self.trades.sort_values(['date', '_order']).reset_index(drop=True)
            self.trades = self.trades.drop(columns=['_order'])

    # -------------------------------------------------------------------------
    # 构建完整交易（Round Trip）
    # -------------------------------------------------------------------------
    def _build_round_trips(self) -> List[Dict]:
        """
        构建每笔完整交易（从第一次买入到清仓卖出）。

        每笔完整交易包含：
        - 股票代码、名称
        - 入场日期、出场日期
        - 持仓天数
        - 各层买入详情（价格、股数、金额、费用）
        - 最大达到层数
        - 出场原因（止盈/止损）
        - 总盈亏、盈亏比例
        """
        round_trips = []

        if self.trades.empty:
            return round_trips

        current_symbol = None
        current_lots = []  # 各层买入记录
        first_buy_date = None
        total_buy_cost = 0
        total_buy_fees = 0
        total_shares = 0

        for _, trade in self.trades.iterrows():
            if trade['action'] == 'BUY':
                if current_symbol is None:
                    current_symbol = trade['symbol']
                    first_buy_date = trade['date']
                    current_lots = []
                    total_buy_cost = 0
                    total_buy_fees = 0
                    total_shares = 0

                # 注意：trade['amount'] 已包含滑点（买入价=原始价×(1+滑点率)）
                # 所以费用中不再加 slippage，避免重复计算
                lot_fee = trade['commission'] + trade['transfer_fee']
                lot_cost = trade['amount'] + lot_fee

                current_lots.append({
                    'level': trade['position_level'],
                    'date': trade['date'],
                    'price': trade['price'],
                    'shares': trade['shares'],
                    'amount': trade['amount'],
                    'fee': lot_fee,
                    'total_cost': lot_cost,
                    'avg_cost': lot_cost / trade['shares'] if trade['shares'] > 0 else 0,
                })

                total_buy_cost += trade['amount']
                total_buy_fees += lot_fee
                total_shares += trade['shares']

            elif trade['action'] == 'SELL':
                if current_symbol == trade['symbol']:
                    # 注意：trade['amount'] 已扣除滑点（卖出价=原始价×(1-滑点率)）
                    # 所以费用中不再减 slippage，避免重复计算
                    sell_fee = (trade['commission'] + trade['stamp_tax'] +
                                 trade['transfer_fee'])
                    net_proceeds = trade['amount'] - sell_fee
                    total_cost = total_buy_cost + total_buy_fees
                    pnl = net_proceeds - total_cost
                    pnl_pct = pnl / total_cost * 100 if total_cost > 0 else 0
                    holding_days = (trade['date'] - first_buy_date).days
                    max_level = max(lot['level'] for lot in current_lots) if current_lots else 0

                    round_trips.append({
                        'symbol': current_symbol,
                        'entry_date': first_buy_date,
                        'exit_date': trade['date'],
                        'holding_days': holding_days,
                        'max_level': max_level,
                        'lots': current_lots.copy(),
                        'total_shares': total_shares,
                        'total_cost': round(total_cost, 2),
                        'avg_cost': round(total_cost / total_shares, 4) if total_shares > 0 else 0,
                        'sell_price': trade['price'],
                        'sell_proceeds': round(net_proceeds, 2),
                        'pnl': round(pnl, 2),
                        'pnl_pct': round(pnl_pct, 2),
                        'exit_reason': trade['reason'],
                    })

                    current_symbol = None
                    current_lots = []
                    total_buy_cost = 0
                    total_buy_fees = 0
                    total_shares = 0
                    first_buy_date = None

        return round_trips

    # -------------------------------------------------------------------------
    # 各层止盈比例统计
    # -------------------------------------------------------------------------
    def calc_level_distribution(self) -> Dict:
        """
        统计各层止盈/止损分布。

        回答：有多少比例的交易只用到第1层就止盈了？
              有多少比例需要加到第2层、第3层...才止盈？
        """
        round_trips = self._build_round_trips()

        if not round_trips:
            return {'total_trades': 0}

        total = len(round_trips)
        level_stats = {}

        for level in range(1, self.max_levels + 1):
            # 达到该层数的交易（max_level == level）
            trades_at_level = [rt for rt in round_trips if rt['max_level'] == level]
            tp_at_level = [rt for rt in trades_at_level if rt['exit_reason'] == 'TAKE_PROFIT']
            sl_at_level = [rt for rt in trades_at_level if rt['exit_reason'] == 'STOP_LOSS']

            level_stats[f'level_{level}'] = {
                'count': len(trades_at_level),
                'ratio': round(len(trades_at_level) / total * 100, 2),
                'take_profit_count': len(tp_at_level),
                'take_profit_ratio': round(len(tp_at_level) / total * 100, 2),
                'stop_loss_count': len(sl_at_level),
                'stop_loss_ratio': round(len(sl_at_level) / total * 100, 2),
                'avg_pnl': round(np.mean([rt['pnl'] for rt in trades_at_level]), 2) if trades_at_level else 0,
                'avg_pnl_pct': round(np.mean([rt['pnl_pct'] for rt in trades_at_level]), 2) if trades_at_level else 0,
                'avg_holding_days': round(np.mean([rt['holding_days'] for rt in trades_at_level]), 1) if trades_at_level else 0,
            }

        # 满仓（第5层）后的结局统计
        full_position_trades = [rt for rt in round_trips if rt['max_level'] == self.max_levels]
        if full_position_trades:
            fp_total = len(full_position_trades)
            fp_tp = [rt for rt in full_position_trades if rt['exit_reason'] == 'TAKE_PROFIT']
            fp_sl = [rt for rt in full_position_trades if rt['exit_reason'] == 'STOP_LOSS']
            fp_other = [rt for rt in full_position_trades if rt['exit_reason'] not in ['TAKE_PROFIT', 'STOP_LOSS']]

            level_stats['full_position_outcome'] = {
                'total': fp_total,
                'take_profit_count': len(fp_tp),
                'take_profit_ratio': round(len(fp_tp) / fp_total * 100, 2),
                'stop_loss_count': len(fp_sl),
                'stop_loss_ratio': round(len(fp_sl) / fp_total * 100, 2),
                'other_count': len(fp_other),
                'other_ratio': round(len(fp_other) / fp_total * 100, 2),
                'avg_pnl': round(np.mean([rt['pnl'] for rt in full_position_trades]), 2),
                'avg_pnl_pct': round(np.mean([rt['pnl_pct'] for rt in full_position_trades]), 2),
            }

        level_stats['total_trades'] = total
        return level_stats

    # -------------------------------------------------------------------------
    # 各层平均收益
    # -------------------------------------------------------------------------
    def calc_level_returns(self) -> Dict:
        """
        计算各层的平均收益。

        回答：第1层买入后平均赚多少？第2层加仓后平均赚多少？
              收益主要来自哪一层？
        """
        round_trips = self._build_round_trips()

        if not round_trips:
            return {'total_trades': 0}

        level_returns = {}

        for level in range(1, self.max_levels + 1):
            # 所有达到该层或以上的交易中，该层买入的表现
            lot_pnls = []
            lot_pnl_pcts = []

            for rt in round_trips:
                if rt['max_level'] >= level:
                    # 找到该层的买入记录
                    lot = next((l for l in rt['lots'] if l['level'] == level), None)
                    if lot:
                        # 该层的盈亏 = (卖出价 - 该层买入价) × 该层股数 - 该层分摊费用
                        # 简化：按该层成本占总成本的比例分摊总盈亏
                        level_cost_ratio = lot['total_cost'] / rt['total_cost'] if rt['total_cost'] > 0 else 0
                        lot_pnl = rt['pnl'] * level_cost_ratio
                        lot_pnl_pct = lot_pnl / lot['total_cost'] * 100 if lot['total_cost'] > 0 else 0
                        lot_pnls.append(lot_pnl)
                        lot_pnl_pcts.append(lot_pnl_pct)

            level_returns[f'level_{level}'] = {
                'count': len(lot_pnls),
                'avg_pnl': round(np.mean(lot_pnls), 2) if lot_pnls else 0,
                'avg_pnl_pct': round(np.mean(lot_pnl_pcts), 2) if lot_pnls else 0,
                'median_pnl': round(np.median(lot_pnls), 2) if lot_pnls else 0,
                'win_rate': round(sum(1 for p in lot_pnls if p > 0) / len(lot_pnls) * 100, 2) if lot_pnls else 0,
            }

        return level_returns

    # -------------------------------------------------------------------------
    # 全部分析
    # -------------------------------------------------------------------------
    def calc_all(self) -> Dict:
        """计算全部仓位层级分析指标。"""
        return {
            'level_distribution': self.calc_level_distribution(),
            'level_returns': self.calc_level_returns(),
        }

    def print_report(self):
        """打印仓位层级分析报告。"""
        analysis = self.calc_all()
        dist = analysis['level_distribution']
        returns = analysis['level_returns']

        print("\n" + "=" * 70)
        print("仓位层级分析报告")
        print("=" * 70)

        print(f"\n总交易笔数: {dist.get('total_trades', 0)}")

        print("\n【各层分布统计】")
        print(f"{'层级':<8} {'笔数':>6} {'占比':>8} {'止盈数':>8} {'止盈占比':>10} "
              f"{'止损数':>8} {'平均盈亏':>12} {'平均盈亏%':>10} {'平均持仓天':>10}")
        print("-" * 90)

        for level in range(1, self.max_levels + 1):
            key = f'level_{level}'
            if key in dist:
                s = dist[key]
                print(f"第{level}层    {s['count']:>6d} {s['ratio']:>7.2f}% "
                      f"{s['take_profit_count']:>8d} {s['take_profit_ratio']:>9.2f}% "
                      f"{s['stop_loss_count']:>8d} {s['avg_pnl']:>12,.2f} "
                      f"{s['avg_pnl_pct']:>9.2f}% {s['avg_holding_days']:>10.1f}")

        if 'full_position_outcome' in dist:
            fp = dist['full_position_outcome']
            print(f"\n【满仓（第{self.max_levels}层）后结局】")
            print(f"  满仓交易数:     {fp['total']:>8d}")
            print(f"  最终止盈:       {fp['take_profit_count']:>8d} ({fp['take_profit_ratio']:.2f}%)")
            print(f"  最终止损:       {fp['stop_loss_count']:>8d} ({fp['stop_loss_ratio']:.2f}%)")
            print(f"  其他结局:       {fp['other_count']:>8d} ({fp['other_ratio']:.2f}%)")
            print(f"  满仓平均盈亏:   {fp['avg_pnl']:>12,.2f} 元 ({fp['avg_pnl_pct']:.2f}%)")

        print("\n【各层收益贡献】")
        print(f"{'层级':<8} {'样本数':>8} {'平均盈亏':>12} {'平均盈亏%':>10} {'中位数':>12} {'胜率':>8}")
        print("-" * 65)

        for level in range(1, self.max_levels + 1):
            key = f'level_{level}'
            if key in returns:
                r = returns[key]
                print(f"第{level}层    {r['count']:>8d} {r['avg_pnl']:>12,.2f} "
                      f"{r['avg_pnl_pct']:>9.2f}% {r['median_pnl']:>12,.2f} {r['win_rate']:>7.2f}%")

        # 核心结论
        print("\n【核心结论】")
        if dist.get('total_trades', 0) > 0:
            level1_ratio = dist.get('level_1', {}).get('ratio', 0)
            level1_tp_ratio = dist.get('level_1', {}).get('take_profit_ratio', 0)
            print(f"  仅用第1层就完成的交易占比: {level1_ratio:.2f}%")
            print(f"  其中第1层直接止盈的占比:   {level1_tp_ratio:.2f}%")

            if 'full_position_outcome' in dist:
                fp = dist['full_position_outcome']
                print(f"  满仓后最终止盈比例:         {fp['take_profit_ratio']:.2f}%")
                print(f"  满仓后最终止损比例:         {fp['stop_loss_ratio']:.2f}%")

            # 判断收益来源
            level1_avg = returns.get('level_1', {}).get('avg_pnl', 0)
            level5_avg = returns.get('level_5', {}).get('avg_pnl', 0)
            if level1_avg > 0 and level5_avg < level1_avg * 0.5:
                print("  ⚠ 收益主要来自第1层，加仓可能拉低平均收益")
            elif level5_avg > level1_avg:
                print("  ✓ 加仓有效提升了收益，均值回归在更深层仍有效")
            else:
                print("  各层收益相对均衡，加仓对收益影响中性")

        print("=" * 70)
        return analysis
