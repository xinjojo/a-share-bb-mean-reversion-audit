"""
绩效分析模块

计算策略回测的核心绩效指标：
- 累计收益率、年化收益率
- 最大回撤
- 年化波动率、Sharpe、Sortino、Calmar
- 胜率、平均盈利、平均亏损、盈亏比、Profit Factor
- 交易次数、平均持仓天数、最大持仓天数、最大连续亏损
- 最大资金占用、最大仓位
- 手续费、印花税、过户费、滑点损失总额

精度等级：EXACT（基于交易日志和净值曲线精确计算）
"""
import logging
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """绩效分析器。"""

    def __init__(self, trades: List[Dict], daily_nav: List[Dict],
                 initial_cash: float = 1000000.0, risk_free_rate: float = 0.02):
        """
        Args:
            trades: 交易日志列表
            daily_nav: 每日净值列表
            initial_cash: 初始资金
            risk_free_rate: 无风险利率（年化），用于Sharpe计算
        """
        self.trades = pd.DataFrame(trades) if trades else pd.DataFrame()
        self.daily_nav = pd.DataFrame(daily_nav) if daily_nav else pd.DataFrame()
        self.initial_cash = initial_cash
        self.risk_free_rate = risk_free_rate

        if not self.daily_nav.empty:
            self.daily_nav['date'] = pd.to_datetime(self.daily_nav['date'])
            self.daily_nav = self.daily_nav.sort_values('date').reset_index(drop=True)

        if not self.trades.empty:
            self.trades['date'] = pd.to_datetime(self.trades['date'])
            # 同一天先SELL后BUY，避免止盈后重新买入的交易被错误合并
            self.trades['_order'] = self.trades['action'].map({'SELL': 0, 'BUY': 1})
            self.trades = self.trades.sort_values(['date', '_order']).reset_index(drop=True)
            self.trades = self.trades.drop(columns=['_order'])

    # -------------------------------------------------------------------------
    # 收益指标
    # -------------------------------------------------------------------------
    def calc_returns(self) -> Dict:
        """计算收益指标。"""
        if self.daily_nav.empty:
            return {'total_return': 0, 'annual_return': 0, 'total_days': 0}

        final_equity = self.daily_nav['total_equity'].iloc[-1]
        total_return = (final_equity - self.initial_cash) / self.initial_cash

        # 年化收益率
        total_days = len(self.daily_nav)
        years = total_days / 252.0  # 假设每年252个交易日
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

        return {
            'total_return': round(total_return * 100, 2),
            'annual_return': round(annual_return * 100, 2),
            'final_equity': round(final_equity, 2),
            'total_trading_days': total_days,
        }

    # -------------------------------------------------------------------------
    # 风险指标
    # -------------------------------------------------------------------------
    def calc_risk(self) -> Dict:
        """计算风险指标。"""
        if self.daily_nav.empty:
            return {'max_drawdown': 0, 'annual_volatility': 0, 'sharpe': 0,
                    'sortino': 0, 'calmar': 0}

        # 日收益率
        self.daily_nav['daily_return'] = self.daily_nav['total_equity'].pct_change()
        daily_returns = self.daily_nav['daily_return'].dropna()

        # 最大回撤
        peak = self.daily_nav['total_equity'].cummax()
        drawdown = (self.daily_nav['total_equity'] - peak) / peak
        max_drawdown = drawdown.min()

        # 年化波动率
        annual_volatility = daily_returns.std() * np.sqrt(252)

        # Sharpe比率
        excess_returns = daily_returns - self.risk_free_rate / 252
        sharpe = (excess_returns.mean() / daily_returns.std() * np.sqrt(252)
                  if daily_returns.std() > 0 else 0)

        # Sortino比率（只考虑下行波动率）
        downside_returns = daily_returns[daily_returns < 0]
        downside_vol = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        sortino = (excess_returns.mean() * 252 / downside_vol
                    if downside_vol > 0 else 0)

        # Calmar比率 = 年化收益 / 最大回撤绝对值
        returns = self.calc_returns()
        calmar = (returns['annual_return'] / 100 / abs(max_drawdown)
                  if max_drawdown < 0 else 0)

        return {
            'max_drawdown': round(max_drawdown * 100, 2),
            'annual_volatility': round(annual_volatility * 100, 2),
            'sharpe_ratio': round(sharpe, 3),
            'sortino_ratio': round(sortino, 3),
            'calmar_ratio': round(calmar, 3),
        }

    # -------------------------------------------------------------------------
    # 交易统计
    # -------------------------------------------------------------------------
    def calc_trade_stats(self) -> Dict:
        """计算交易统计指标。"""
        if self.trades.empty:
            return {'total_trades': 0, 'win_rate': 0, 'avg_profit': 0,
                    'avg_loss': 0, 'profit_loss_ratio': 0, 'profit_factor': 0,
                    'avg_holding_days': 0, 'max_holding_days': 0,
                    'max_consecutive_losses': 0}

        sell_trades = self.trades[self.trades['action'] == 'SELL'].copy()
        buy_trades = self.trades[self.trades['action'] == 'BUY'].copy()

        if sell_trades.empty:
            return {'total_trades': 0, 'win_rate': 0, 'avg_profit': 0,
                    'avg_loss': 0, 'profit_loss_ratio': 0, 'profit_factor': 0,
                    'avg_holding_days': 0, 'max_holding_days': 0,
                    'max_consecutive_losses': 0}

        # 计算每笔完整交易的盈亏（从第一次买入到卖出）
        round_trips = self._calculate_round_trips()

        if not round_trips:
            return {'total_trades': 0, 'win_rate': 0, 'avg_profit': 0,
                    'avg_loss': 0, 'profit_loss_ratio': 0, 'profit_factor': 0,
                    'avg_holding_days': 0, 'max_holding_days': 0,
                    'max_consecutive_losses': 0}

        pnls = [rt['pnl'] for rt in round_trips]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        win_rate = len(wins) / len(pnls) if pnls else 0
        avg_profit = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        profit_loss_ratio = abs(avg_profit / avg_loss) if avg_loss != 0 else float('inf')
        profit_factor = abs(sum(wins) / sum(losses)) if sum(losses) != 0 else float('inf')

        # 持仓天数
        holding_days = [rt['holding_days'] for rt in round_trips]
        avg_holding_days = np.mean(holding_days) if holding_days else 0
        max_holding_days = max(holding_days) if holding_days else 0

        # 最大连续亏损
        max_consecutive_losses = self._calc_max_consecutive_losses(pnls)

        return {
            'total_round_trips': len(round_trips),
            'total_buy_trades': len(buy_trades),
            'total_sell_trades': len(sell_trades),
            'win_rate': round(win_rate * 100, 2),
            'avg_profit': round(avg_profit, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_loss_ratio': round(profit_loss_ratio, 3),
            'profit_factor': round(profit_factor, 3),
            'avg_holding_days': round(avg_holding_days, 1),
            'max_holding_days': max_holding_days,
            'max_consecutive_losses': max_consecutive_losses,
        }

    def _calculate_round_trips(self) -> List[Dict]:
        """
        计算每笔完整交易（从第一次买入到清仓卖出）。

        由于策略是单股策略，每次清仓后才会买新股票，
        所以可以按股票分组，每组内第一次买入到最后一次卖出为一笔完整交易。
        """
        round_trips = []

        if self.trades.empty:
            return round_trips

        # 按时间顺序遍历，识别完整交易
        current_symbol = None
        buy_cost = 0
        buy_shares = 0
        buy_fees = 0
        first_buy_date = None

        for _, trade in self.trades.iterrows():
            if trade['action'] == 'BUY':
                if current_symbol is None:
                    current_symbol = trade['symbol']
                    first_buy_date = trade['date']
                    buy_cost = 0
                    buy_shares = 0
                    buy_fees = 0
                buy_cost += trade['amount']
                buy_shares += trade['shares']
                # 注意：trade['amount'] 已包含滑点，费用中不再加 slippage
                buy_fees += trade['commission'] + trade['transfer_fee']
            elif trade['action'] == 'SELL':
                if current_symbol == trade['symbol']:
                    sell_amount = trade['amount']
                    # 注意：trade['amount'] 已扣除滑点，费用中不再减 slippage
                    sell_fees = trade['commission'] + trade['stamp_tax'] + trade['transfer_fee']
                    net_proceeds = sell_amount - sell_fees
                    total_cost = buy_cost + buy_fees
                    pnl = net_proceeds - total_cost
                    holding_days = (trade['date'] - first_buy_date).days

                    round_trips.append({
                        'symbol': current_symbol,
                        'entry_date': first_buy_date,
                        'exit_date': trade['date'],
                        'holding_days': holding_days,
                        'buy_cost': round(total_cost, 2),
                        'sell_proceeds': round(net_proceeds, 2),
                        'pnl': round(pnl, 2),
                        'pnl_pct': round(pnl / total_cost * 100, 2) if total_cost > 0 else 0,
                        'exit_reason': trade['reason'],
                        'max_level': trade['position_level'],
                    })

                    current_symbol = None
                    buy_cost = 0
                    buy_shares = 0
                    buy_fees = 0
                    first_buy_date = None

        return round_trips

    def _calc_max_consecutive_losses(self, pnls: List[float]) -> int:
        """计算最大连续亏损次数。"""
        max_losses = 0
        current_losses = 0
        for pnl in pnls:
            if pnl <= 0:
                current_losses += 1
                max_losses = max(max_losses, current_losses)
            else:
                current_losses = 0
        return max_losses

    # -------------------------------------------------------------------------
    # 仓位与资金占用
    # -------------------------------------------------------------------------
    def calc_position_stats(self) -> Dict:
        """计算仓位和资金占用统计。"""
        if self.daily_nav.empty:
            return {'max_position_pct': 0, 'max_cash_usage': 0,
                    'avg_position_pct': 0, 'position_days': 0, 'empty_days': 0}

        # 仓位比例 = 持仓市值 / 总权益
        self.daily_nav['position_pct'] = (
            self.daily_nav['market_value'] / self.daily_nav['total_equity'] * 100
        )
        self.daily_nav['cash_usage'] = (
            (self.initial_cash - self.daily_nav['cash']) / self.initial_cash * 100
        )

        max_position_pct = self.daily_nav['position_pct'].max()
        max_cash_usage = self.daily_nav['cash_usage'].max()
        avg_position_pct = self.daily_nav['position_pct'].mean()
        position_days = (self.daily_nav['position_level'] > 0).sum()
        empty_days = (self.daily_nav['position_level'] == 0).sum()

        return {
            'max_position_pct': round(max_position_pct, 2),
            'max_cash_usage': round(max_cash_usage, 2),
            'avg_position_pct': round(avg_position_pct, 2),
            'position_days': int(position_days),
            'empty_days': int(empty_days),
            'position_ratio': round(position_days / len(self.daily_nav) * 100, 2),
        }

    # -------------------------------------------------------------------------
    # 费用统计
    # -------------------------------------------------------------------------
    def calc_fee_stats(self) -> Dict:
        """计算交易费用统计。"""
        if self.trades.empty:
            return {'total_commission': 0, 'total_stamp_tax': 0,
                    'total_transfer_fee': 0, 'total_slippage': 0,
                    'total_fees': 0, 'fee_ratio': 0}

        total_commission = self.trades['commission'].sum()
        total_stamp_tax = self.trades['stamp_tax'].sum()
        total_transfer_fee = self.trades['transfer_fee'].sum()
        total_slippage = self.trades['slippage'].sum()
        total_fees = total_commission + total_stamp_tax + total_transfer_fee + total_slippage

        returns = self.calc_returns()
        fee_ratio = total_fees / self.initial_cash * 100

        return {
            'total_commission': round(total_commission, 2),
            'total_stamp_tax': round(total_stamp_tax, 2),
            'total_transfer_fee': round(total_transfer_fee, 2),
            'total_slippage': round(total_slippage, 2),
            'total_fees': round(total_fees, 2),
            'fee_ratio_to_initial': round(fee_ratio, 4),
        }

    # -------------------------------------------------------------------------
    # 全部指标
    # -------------------------------------------------------------------------
    def calc_all(self) -> Dict:
        """计算全部绩效指标。"""
        results = {}
        results.update(self.calc_returns())
        results.update(self.calc_risk())
        results.update(self.calc_trade_stats())
        results.update(self.calc_position_stats())
        results.update(self.calc_fee_stats())
        return results

    def print_report(self):
        """打印绩效报告。"""
        metrics = self.calc_all()

        print("\n" + "=" * 70)
        print("策略绩效报告")
        print("=" * 70)

        print("\n【收益指标】")
        print(f"  累计收益率:     {metrics['total_return']:>10.2f} %")
        print(f"  年化收益率:     {metrics['annual_return']:>10.2f} %")
        print(f"  最终权益:       {metrics['final_equity']:>12,.2f} 元")
        print(f"  交易天数:       {metrics['total_trading_days']:>10d} 天")

        print("\n【风险指标】")
        print(f"  最大回撤:       {metrics['max_drawdown']:>10.2f} %")
        print(f"  年化波动率:     {metrics['annual_volatility']:>10.2f} %")
        print(f"  Sharpe比率:     {metrics['sharpe_ratio']:>10.3f}")
        print(f"  Sortino比率:    {metrics['sortino_ratio']:>10.3f}")
        print(f"  Calmar比率:     {metrics['calmar_ratio']:>10.3f}")

        print("\n【交易统计】")
        print(f"  完整交易笔数:   {metrics['total_round_trips']:>10d}")
        print(f"  买入笔数:       {metrics['total_buy_trades']:>10d}")
        print(f"  卖出笔数:       {metrics['total_sell_trades']:>10d}")
        print(f"  胜率:           {metrics['win_rate']:>10.2f} %")
        print(f"  平均盈利:       {metrics['avg_profit']:>12,.2f} 元")
        print(f"  平均亏损:       {metrics['avg_loss']:>12,.2f} 元")
        print(f"  盈亏比:         {metrics['profit_loss_ratio']:>10.3f}")
        print(f"  Profit Factor:  {metrics['profit_factor']:>10.3f}")
        print(f"  平均持仓天数:   {metrics['avg_holding_days']:>10.1f} 天")
        print(f"  最大持仓天数:   {metrics['max_holding_days']:>10d} 天")
        print(f"  最大连续亏损:   {metrics['max_consecutive_losses']:>10d} 次")

        print("\n【仓位统计】")
        print(f"  最大仓位比例:   {metrics['max_position_pct']:>10.2f} %")
        print(f"  平均仓位比例:   {metrics['avg_position_pct']:>10.2f} %")
        print(f"  最大资金占用:   {metrics['max_cash_usage']:>10.2f} %")
        print(f"  持仓天数:       {metrics['position_days']:>10d} 天")
        print(f"  空仓天数:       {metrics['empty_days']:>10d} 天")
        print(f"  持仓占比:       {metrics['position_ratio']:>10.2f} %")

        print("\n【费用统计】")
        print(f"  手续费总额:     {metrics['total_commission']:>12,.2f} 元")
        print(f"  印花税总额:     {metrics['total_stamp_tax']:>12,.2f} 元")
        print(f"  过户费总额:     {metrics['total_transfer_fee']:>12,.2f} 元")
        print(f"  滑点损失:       {metrics['total_slippage']:>12,.2f} 元")
        print(f"  费用合计:       {metrics['total_fees']:>12,.2f} 元")
        print(f"  费用/初始资金:  {metrics['fee_ratio_to_initial']:>10.4f} %")

        print("=" * 70)
        return metrics
