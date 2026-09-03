#!/usr/bin/env python3
"""
交易复盘分析模块：
1. 止盈空间分析：每笔交易后续最高涨幅分布
2. 止损复盘分析：不同止损比例的效果对比
3. 按年收益率统计
4. 参数敏感性扫描
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from collections import defaultdict


class TradeReviewAnalyzer:
    """交易复盘分析器。"""

    def __init__(self, trades: List[Dict], daily_data_dir: str = 'data/raw/daily'):
        self.trades = pd.DataFrame(trades)
        if not self.trades.empty:
            self.trades['date'] = pd.to_datetime(self.trades['date'])
        self.daily_data_dir = daily_data_dir
        self._cache = {}

    def _get_stock_data(self, ts_code: str) -> pd.DataFrame:
        """获取股票日线数据（带缓存）。"""
        if ts_code not in self._cache:
            filepath = os.path.join(self.daily_data_dir, f'{ts_code}.parquet')
            if os.path.exists(filepath):
                df = pd.read_parquet(filepath)
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)
                self._cache[ts_code] = df
            else:
                self._cache[ts_code] = pd.DataFrame()
        return self._cache[ts_code]

    # -------------------------------------------------------------------------
    # 1. 止盈空间分析
    # -------------------------------------------------------------------------
    def analyze_take_profit_space(self, thresholds: List[float] = None) -> Dict:
        """
        分析每笔止盈交易后续的最高涨幅。

        对于每笔止盈交易，查看从买入日到卖出日（及之后N天）的最高价，
        计算相对于平均成本的最高涨幅，统计有多少比例达到了各个阈值。
        """
        if thresholds is None:
            thresholds = [0.015, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50]

        # 获取所有完整交易
        round_trips = self._build_round_trips()
        if not round_trips:
            return {'error': 'no round trips'}

        results = []
        for rt in round_trips:
            symbol = rt['symbol']
            entry_date = rt['entry_date']
            exit_date = rt['exit_date']
            avg_cost = rt['avg_cost']
            exit_reason = rt['exit_reason']

            df = self._get_stock_data(symbol)
            if df.empty:
                continue

            # 找到买入日和卖出日的索引
            entry_idx = df[df['date'] == entry_date].index
            exit_idx = df[df['date'] == exit_date].index

            if len(entry_idx) == 0 or len(exit_idx) == 0:
                continue

            entry_idx = entry_idx[0]
            exit_idx = exit_idx[0]

            # 计算从买入日到卖出日的最高价
            period_df = df.iloc[entry_idx:exit_idx + 1]
            if period_df.empty:
                continue

            max_high = period_df['high'].max()
            max_return = (max_high - avg_cost) / avg_cost

            # 卖出日之后5天的最高价（看是否卖早了）
            post_exit_df = df.iloc[exit_idx + 1:exit_idx + 6]
            post_max_high = post_exit_df['high'].max() if len(post_exit_df) > 0 else np.nan
            post_max_return = (post_max_high - avg_cost) / avg_cost if not np.isnan(post_max_high) else np.nan

            results.append({
                'symbol': symbol,
                'entry_date': entry_date,
                'exit_date': exit_date,
                'avg_cost': avg_cost,
                'exit_reason': exit_reason,
                'holding_days': rt['holding_days'],
                'max_high_in_period': max_high,
                'max_return_in_period': max_return,
                'post_exit_max_high': post_max_high,
                'post_exit_max_return': post_max_return,
                'actual_pnl_pct': rt['pnl_pct'],
            })

        if not results:
            return {'error': 'no valid results'}

        df_results = pd.DataFrame(results)

        # 统计达到各个阈值的比例
        threshold_stats = {}
        for t in thresholds:
            reached = (df_results['max_return_in_period'] >= t).sum()
            pct = reached / len(df_results) * 100
            threshold_stats[f'>={t*100:.1f}%'] = {
                'count': int(reached),
                'pct': round(pct, 2),
            }

        # 止盈交易的后续空间（只看止盈的）
        tp_trades = df_results[df_results['exit_reason'] == 'TAKE_PROFIT']
        tp_threshold_stats = {}
        if len(tp_trades) > 0:
            for t in thresholds:
                reached = (tp_trades['max_return_in_period'] >= t).sum()
                pct = reached / len(tp_trades) * 100
                tp_threshold_stats[f'>={t*100:.1f}%'] = {
                    'count': int(reached),
                    'pct': round(pct, 2),
                }

        # 最高涨幅分布
        max_return_stats = {
            'mean': round(df_results['max_return_in_period'].mean() * 100, 2),
            'median': round(df_results['max_return_in_period'].median() * 100, 2),
            'max': round(df_results['max_return_in_period'].max() * 100, 2),
            'p25': round(df_results['max_return_in_period'].quantile(0.25) * 100, 2),
            'p75': round(df_results['max_return_in_period'].quantile(0.75) * 100, 2),
            'p90': round(df_results['max_return_in_period'].quantile(0.90) * 100, 2),
        }

        # 止盈后继续上涨的比例
        post_exit_up = 0
        post_exit_down = 0
        post_exit_flat = 0
        if 'post_exit_max_return' in df_results.columns:
            valid_post = df_results.dropna(subset=['post_exit_max_return'])
            post_exit_up = (valid_post['post_exit_max_return'] > 0.015).sum()
            post_exit_down = (valid_post['post_exit_max_return'] < 0).sum()
            post_exit_flat = len(valid_post) - post_exit_up - post_exit_down

        return {
            'total_trades': len(df_results),
            'take_profit_trades': len(tp_trades),
            'stop_loss_trades': len(df_results[df_results['exit_reason'] == 'STOP_LOSS']),
            'threshold_stats_all': threshold_stats,
            'threshold_stats_take_profit': tp_threshold_stats,
            'max_return_distribution': max_return_stats,
            'post_exit_analysis': {
                'continued_up_1.5pct': int(post_exit_up),
                'went_down': int(post_exit_down),
                'flat': int(post_exit_flat),
                'continued_up_pct': round(post_exit_up / max(len(df_results.dropna(subset=['post_exit_max_return'])), 1) * 100, 2),
            },
            'details': df_results,
        }

    # -------------------------------------------------------------------------
    # 2. 止损复盘分析
    # -------------------------------------------------------------------------
    def analyze_stop_loss_effectiveness(self, stop_levels: List[float] = None) -> Dict:
        """
        分析不同止损比例的效果。

        对于每笔交易，模拟如果在不同止损比例下卖出，盈亏会是多少。
        """
        if stop_levels is None:
            stop_levels = [None, 0.03, 0.05, 0.07, 0.10, 0.15]  # None = 不止损

        round_trips = self._build_round_trips()
        if not round_trips:
            return {'error': 'no round trips'}

        results = {}

        for stop_pct in stop_levels:
            label = 'disabled' if stop_pct is None else f'{stop_pct*100:.0f}%'
            pnls = []
            win_count = 0
            loss_count = 0
            total_profit = 0
            total_loss = 0

            for rt in round_trips:
                symbol = rt['symbol']
                entry_date = rt['entry_date']
                exit_date = rt['exit_date']
                avg_cost = rt['avg_cost']

                df = self._get_stock_data(symbol)
                if df.empty:
                    continue

                entry_idx = df[df['date'] == entry_date].index
                exit_idx = df[df['date'] == exit_date].index

                if len(entry_idx) == 0 or len(exit_idx) == 0:
                    continue

                entry_idx = entry_idx[0]
                exit_idx = exit_idx[0]

                # 模拟止损
                simulated_pnl_pct = rt['pnl_pct']  # 默认用实际结果

                if stop_pct is not None:
                    stop_price = avg_cost * (1 - stop_pct)
                    # 从买入后第二天开始检查（T+1）
                    for i in range(entry_idx + 1, exit_idx + 1):
                        day_low = df.iloc[i]['low']
                        if day_low <= stop_price:
                            # 止损触发，假设以止损价成交
                            simulated_pnl_pct = (stop_price - avg_cost) / avg_cost * 100
                            break

                pnls.append(simulated_pnl_pct)
                if simulated_pnl_pct > 0:
                    win_count += 1
                    total_profit += simulated_pnl_pct
                else:
                    loss_count += 1
                    total_loss += abs(simulated_pnl_pct)

            if pnls:
                results[label] = {
                    'total_trades': len(pnls),
                    'win_rate': round(win_count / len(pnls) * 100, 2),
                    'avg_pnl_pct': round(np.mean(pnls), 2),
                    'median_pnl_pct': round(np.median(pnls), 2),
                    'total_profit_pct': round(total_profit, 2),
                    'total_loss_pct': round(total_loss, 2),
                    'profit_factor': round(total_profit / total_loss, 3) if total_loss > 0 else float('inf'),
                    'max_win_pct': round(max(pnls), 2),
                    'max_loss_pct': round(min(pnls), 2),
                }
            else:
                results[label] = {'error': 'no trades'}

        return results

    # -------------------------------------------------------------------------
    # 3. 按年收益率统计
    # -------------------------------------------------------------------------
    def analyze_yearly_returns(self, nav: List[Dict]) -> Dict:
        """按年统计收益率。"""
        if not nav:
            return {}

        df_nav = pd.DataFrame(nav)
        df_nav['date'] = pd.to_datetime(df_nav['date'])
        df_nav['year'] = df_nav['date'].dt.year

        yearly = {}
        for year, group in df_nav.groupby('year'):
            group = group.sort_values('date')
            start_equity = group['total_equity'].iloc[0]
            end_equity = group['total_equity'].iloc[-1]
            return_pct = (end_equity - start_equity) / start_equity * 100

            # 年内最大回撤
            peak = group['total_equity'].cummax()
            drawdown = (group['total_equity'] - peak) / peak * 100
            max_dd = drawdown.min()

            # 年内波动率
            daily_returns = group['total_equity'].pct_change().dropna()
            volatility = daily_returns.std() * np.sqrt(252) * 100 if len(daily_returns) > 1 else 0

            yearly[int(year)] = {
                'start_equity': round(start_equity, 2),
                'end_equity': round(end_equity, 2),
                'return_pct': round(return_pct, 2),
                'max_drawdown_pct': round(max_dd, 2),
                'annual_volatility_pct': round(volatility, 2),
                'trading_days': len(group),
            }

        return yearly

    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------
    def _build_round_trips(self) -> List[Dict]:
        """构建完整交易对（从第一次买入到清仓卖出）。"""
        if self.trades.empty:
            return []

        trades = self.trades.copy()
        trades['_order'] = trades['action'].map({'SELL': 0, 'BUY': 1})
        trades = trades.sort_values(['date', '_order']).reset_index(drop=True)

        round_trips = []
        current_symbol = None
        buy_cost = 0
        buy_shares = 0
        buy_fees = 0
        first_buy_date = None
        max_level = 0

        for _, trade in trades.iterrows():
            if trade['action'] == 'BUY':
                if current_symbol is None:
                    current_symbol = trade['symbol']
                    first_buy_date = trade['date']
                    buy_cost = 0
                    buy_shares = 0
                    buy_fees = 0
                    max_level = 0
                buy_cost += trade['amount']
                buy_shares += trade['shares']
                buy_fees += trade['commission'] + trade['transfer_fee']
                max_level = max(max_level, trade['position_level'])
            elif trade['action'] == 'SELL':
                if current_symbol == trade['symbol']:
                    sell_amount = trade['amount']
                    sell_fees = trade['commission'] + trade['stamp_tax'] + trade['transfer_fee']
                    net_proceeds = sell_amount - sell_fees
                    total_cost = buy_cost + buy_fees
                    pnl = net_proceeds - total_cost
                    pnl_pct = pnl / total_cost * 100 if total_cost > 0 else 0
                    avg_cost = total_cost / buy_shares if buy_shares > 0 else 0
                    holding_days = (trade['date'] - first_buy_date).days

                    round_trips.append({
                        'symbol': current_symbol,
                        'entry_date': first_buy_date,
                        'exit_date': trade['date'],
                        'holding_days': holding_days,
                        'avg_cost': avg_cost,
                        'total_cost': total_cost,
                        'sell_proceeds': net_proceeds,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'exit_reason': trade['reason'],
                        'max_level': max_level,
                    })

                    current_symbol = None
                    buy_cost = 0
                    buy_shares = 0
                    buy_fees = 0
                    first_buy_date = None
                    max_level = 0

        return round_trips

    def print_take_profit_report(self, result: Dict):
        """打印止盈空间分析报告。"""
        if 'error' in result:
            print(f"错误: {result['error']}")
            return

        print("\n" + "=" * 70)
        print("止盈空间复盘分析")
        print("=" * 70)

        print(f"\n总交易笔数: {result['total_trades']}")
        print(f"止盈交易: {result['take_profit_trades']}")
        print(f"止损交易: {result['stop_loss_trades']}")

        print("\n【持仓期间最高涨幅分布】")
        dist = result['max_return_distribution']
        print(f"  平均最高涨幅:   {dist['mean']:>8.2f} %")
        print(f"  中位数最高涨幅: {dist['median']:>8.2f} %")
        print(f"  25分位:         {dist['p25']:>8.2f} %")
        print(f"  75分位:         {dist['p75']:>8.2f} %")
        print(f"  90分位:         {dist['p90']:>8.2f} %")
        print(f"  最大涨幅:       {dist['max']:>8.2f} %")

        print("\n【全部交易 - 达到各涨幅阈值的比例】")
        for threshold, stats in result['threshold_stats_all'].items():
            bar = '█' * int(stats['pct'] / 2)
            print(f"  {threshold:>8}: {stats['count']:>4d}笔 ({stats['pct']:>5.1f}%) {bar}")

        if result['threshold_stats_take_profit']:
            print("\n【仅止盈交易 - 达到各涨幅阈值的比例】")
            for threshold, stats in result['threshold_stats_take_profit'].items():
                bar = '█' * int(stats['pct'] / 2)
                print(f"  {threshold:>8}: {stats['count']:>4d}笔 ({stats['pct']:>5.1f}%) {bar}")

        print("\n【止盈后5天走势】")
        post = result['post_exit_analysis']
        print(f"  继续上涨>1.5%:  {post['continued_up_1.5pct']:>4d}笔 ({post['continued_up_pct']:.1f}%)")
        print(f"  下跌:            {post['went_down']:>4d}笔")
        print(f"  横盘:            {post['flat']:>4d}笔")

        print("=" * 70)

    def print_stop_loss_report(self, result: Dict):
        """打印止损复盘报告。"""
        print("\n" + "=" * 70)
        print("止损参数复盘分析")
        print("=" * 70)
        print(f"\n{'止损比例':<12} {'交易数':>6} {'胜率':>8} {'平均盈亏%':>10} {'盈亏比':>8} {'最大盈利%':>10} {'最大亏损%':>10}")
        print("-" * 70)
        for label, stats in result.items():
            if 'error' in stats:
                print(f"{label:<12} 错误: {stats['error']}")
                continue
            pf = f"{stats['profit_factor']:.3f}" if stats['profit_factor'] != float('inf') else '∞'
            print(f"{label:<12} {stats['total_trades']:>6d} {stats['win_rate']:>7.1f}% {stats['avg_pnl_pct']:>9.2f}% {pf:>8} {stats['max_win_pct']:>9.2f}% {stats['max_loss_pct']:>9.2f}%")
        print("=" * 70)

    def print_yearly_report(self, result: Dict):
        """打印年度收益报告。"""
        print("\n" + "=" * 70)
        print("年度收益率统计")
        print("=" * 70)
        print(f"\n{'年份':<8} {'交易日':>6} {'期初权益':>12} {'期末权益':>12} {'收益率':>10} {'最大回撤':>10} {'波动率':>10}")
        print("-" * 70)
        for year in sorted(result.keys()):
            stats = result[year]
            print(f"{year:<8} {stats['trading_days']:>6d} {stats['start_equity']:>12,.0f} {stats['end_equity']:>12,.0f} {stats['return_pct']:>9.2f}% {stats['max_drawdown_pct']:>9.2f}% {stats['annual_volatility_pct']:>9.2f}%")
        print("=" * 70)
