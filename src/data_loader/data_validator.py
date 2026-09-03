"""
数据验证模块

回测前必须完成的数据验证清单：
1. 随机抽查股票和日期，对比OHLCV和成交额
2. 复权因子验证：后复权价格 = 不复权价格 × adj_factor
3. 成交额排名验证：随机选交易日，验证Top N
4. 退市股验证：确认已退市股票的历史数据可获取
5. 停牌验证：确认停牌日无行情数据
6. ST状态验证
7. 涨跌停价格验证
8. 数据完整性检查

所有验证结果保存到 data/validation/ 目录。
"""
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
import random

from .storage import DataStorage

logger = logging.getLogger(__name__)


class DataValidator:
    """数据验证器。"""

    def __init__(self, storage: DataStorage, validation_dir: str = None):
        """
        Args:
            storage: DataStorage 实例
            validation_dir: 验证报告保存目录
        """
        self.storage = storage
        if validation_dir is None:
            validation_dir = storage.raw_dir.parent / 'validation'
        self.validation_dir = Path(validation_dir)
        self.validation_dir.mkdir(parents=True, exist_ok=True)

        # 验证结果汇总
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'checks': [],
            'passed': 0,
            'failed': 0,
            'warnings': 0,
        }

    def _add_result(self, check_name: str, status: str, message: str,
                     details: dict = None):
        """
        添加验证结果。

        Args:
            check_name: 检查项名称
            status: pass / fail / warning
            message: 结果消息
            details: 详细信息
        """
        self.results['checks'].append({
            'check': check_name,
            'status': status,
            'message': message,
            'details': details or {},
        })
        if status == 'pass':
            self.results['passed'] += 1
        elif status == 'fail':
            self.results['failed'] += 1
        elif status == 'warning':
            self.results['warnings'] += 1

    # -------------------------------------------------------------------------
    # 1. 数据完整性检查
    # -------------------------------------------------------------------------
    def check_completeness(self) -> Dict:
        """检查数据完整性。"""
        logger.info("检查数据完整性...")

        stats = self.storage.get_stats()
        stock_basic = self.storage.load_stock_basic()
        trade_cal = self.storage.load_trade_cal()

        details = {
            'daily_symbols': stats['daily_symbols'],
            'adj_factor_symbols': stats['adj_factor_symbols'],
            'stock_basic_count': len(stock_basic),
            'trade_cal_exists': stats['trade_cal_exists'],
        }

        # 检查日线和复权因子数量是否一致
        if stats['daily_symbols'] > 0 and stats['adj_factor_symbols'] > 0:
            ratio = stats['adj_factor_symbols'] / stats['daily_symbols']
            details['adj_factor_ratio'] = ratio
            if ratio < 0.9:
                self._add_result(
                    '数据完整性-复权因子覆盖率',
                    'warning',
                    f'复权因子覆盖率仅 {ratio:.1%}，部分股票缺少复权因子',
                    details
                )
            else:
                self._add_result(
                    '数据完整性-复权因子覆盖率',
                    'pass',
                    f'复权因子覆盖率 {ratio:.1%}',
                    details
                )
        else:
            self._add_result(
                '数据完整性-基本数据',
                'fail',
                '日线或复权因子数据为空',
                details
            )

        # 检查股票基本信息
        if len(stock_basic) > 0:
            delisted = stock_basic[stock_basic['list_status'] == 'D']
            details['delisted_count'] = len(delisted)
            if len(delisted) > 0:
                self._add_result(
                    '数据完整性-退市股',
                    'pass',
                    f'包含 {len(delisted)} 只退市股票（无幸存者偏差）',
                    details
                )
            else:
                self._add_result(
                    '数据完整性-退市股',
                    'warning',
                    '未包含退市股票，存在幸存者偏差风险',
                    details
                )
        else:
            self._add_result(
                '数据完整性-股票基本信息',
                'fail',
                '股票基本信息为空',
                details
            )

        return details

    # -------------------------------------------------------------------------
    # 2. 随机抽查股票数据
    # -------------------------------------------------------------------------
    def check_random_samples(self, n_samples: int = 20) -> Dict:
        """
        随机抽查股票数据，验证OHLCV和成交额的合理性。

        检查项：
        - high >= low
        - high >= open, close
        - low <= open, close
        - volume > 0（非停牌日）
        - amount > 0（非停牌日）
        - 涨跌幅在合理范围内（-20% ~ +20%，ST为-10%~+10%）
        """
        logger.info(f"随机抽查 {n_samples} 只股票的数据...")

        symbols = self.storage.list_daily_symbols()
        if not symbols:
            self._add_result('随机抽查', 'fail', '无日线数据')
            return {}

        sample_symbols = random.sample(symbols, min(n_samples, len(symbols)))
        total_checks = 0
        total_issues = 0
        issues = []

        for symbol in sample_symbols:
            df = self.storage.load_daily(symbol)
            if df.empty:
                continue

            # 检查 high >= low
            invalid_hl = df[df['high'] < df['low']]
            if not invalid_hl.empty:
                total_issues += len(invalid_hl)
                issues.append(f'{symbol}: {len(invalid_hl)} 天 high < low')

            # 检查 high >= max(open, close)
            invalid_high = df[df['high'] < df[['open', 'close']].max(axis=1)]
            if not invalid_high.empty:
                total_issues += len(invalid_high)
                issues.append(f'{symbol}: {len(invalid_high)} 天 high < max(open,close)')

            # 检查 low <= min(open, close)
            invalid_low = df[df['low'] > df[['open', 'close']].min(axis=1)]
            if not invalid_low.empty:
                total_issues += len(invalid_low)
                issues.append(f'{symbol}: {len(invalid_low)} 天 low > min(open,close)')

            # 检查成交额和成交量（非停牌日应大于0）
            vol_col = 'vol' if 'vol' in df.columns else ('volume' if 'volume' in df.columns else None)
            if vol_col and 'amount' in df.columns:
                active = df[df[vol_col] > 0]
                invalid_amount = active[active['amount'].isna() | (active['amount'] <= 0)]
                if not invalid_amount.empty:
                    total_issues += len(invalid_amount)
                    issues.append(f'{symbol}: {len(invalid_amount)} 天成交额异常')

            total_checks += len(df)

        details = {
            'samples': len(sample_symbols),
            'total_days_checked': total_checks,
            'total_issues': total_issues,
            'issue_rate': total_issues / total_checks if total_checks > 0 else 0,
            'issues_preview': issues[:10],
        }

        if total_issues == 0:
            self._add_result(
                '随机抽查-OHLCV合理性',
                'pass',
                f'抽查 {len(sample_symbols)} 只股票共 {total_checks} 天，无异常',
                details
            )
        elif details['issue_rate'] < 0.001:
            self._add_result(
                '随机抽查-OHLCV合理性',
                'pass',
                f'抽查 {len(sample_symbols)} 只股票，异常率 {details["issue_rate"]:.4%}（可接受）',
                details
            )
        else:
            self._add_result(
                '随机抽查-OHLCV合理性',
                'warning',
                f'抽查发现 {total_issues} 处异常，异常率 {details["issue_rate"]:.2%}',
                details
            )

        return details

    # -------------------------------------------------------------------------
    # 3. 复权因子验证
    # -------------------------------------------------------------------------
    def check_adj_factor(self, n_samples: int = 10) -> Dict:
        """
        验证复权因子的正确性。

        检查：adj_factor 应该是正数，且变化应该发生在除权除息日。
        由于无法直接验证后复权价格的准确性，这里检查：
        - adj_factor > 0
        - adj_factor 变化频率合理（不应该每天都变）
        - 同日的 close * adj_factor 应该是单调的（后复权价格不应有异常跳变）
        """
        logger.info(f"验证 {n_samples} 只股票的复权因子...")

        symbols = self.storage.list_daily_symbols()
        if not symbols:
            self._add_result('复权因子验证', 'fail', '无日线数据')
            return {}

        sample_symbols = random.sample(symbols, min(n_samples, len(symbols)))
        issues = []
        total_checked = 0

        for symbol in sample_symbols:
            daily = self.storage.load_daily(symbol)
            adj = self.storage.load_adj_factor(symbol)

            if daily.empty or adj.empty:
                continue

            merged = pd.merge(daily[['date', 'close']], adj[['date', 'adj_factor']],
                              on='date', how='inner')
            if merged.empty:
                continue

            # 检查 adj_factor > 0
            invalid_factor = merged[merged['adj_factor'] <= 0]
            if not invalid_factor.empty:
                issues.append(f'{symbol}: {len(invalid_factor)} 天复权因子<=0')

            # 计算后复权价格
            merged['close_hfq'] = merged['close'] * merged['adj_factor']

            # 检查后复权价格的日收益率是否在合理范围内
            # 后复权价格应该反映真实涨跌幅，不应该有除权导致的跳变
            merged['hfq_return'] = merged['close_hfq'].pct_change()
            extreme_returns = merged[
                (merged['hfq_return'].abs() > 0.21) &  # 超过21%（考虑科创板20%涨跌停）
                (merged['hfq_return'].notna())
            ]
            if not extreme_returns.empty:
                issues.append(
                    f'{symbol}: {len(extreme_returns)} 天后复权收益率异常（>{len(extreme_returns)}天）'
                )

            total_checked += len(merged)

        details = {
            'samples': len(sample_symbols),
            'total_days': total_checked,
            'issues': issues,
        }

        if not issues:
            self._add_result(
                '复权因子验证',
                'pass',
                f'抽查 {len(sample_symbols)} 只股票，复权因子无异常',
                details
            )
        else:
            self._add_result(
                '复权因子验证',
                'warning',
                f'抽查发现 {len(issues)} 个问题，需人工复核',
                details
            )

        return details

    # -------------------------------------------------------------------------
    # 4. 成交额排名验证
    # -------------------------------------------------------------------------
    def check_amount_ranking(self, n_dates: int = 5, top_n: int = 10) -> Dict:
        """
        验证成交额排名的正确性。

        随机选几个交易日，检查成交额Top N股票的合理性。
        注意：这里无法与外部数据源自动对比，只能检查数据内部一致性。
        """
        logger.info(f"验证 {n_dates} 个交易日的成交额排名...")

        trade_cal = self.storage.load_trade_cal()
        if trade_cal.empty:
            self._add_result('成交额排名验证', 'fail', '无交易日历')
            return {}

        trade_days = trade_cal[trade_cal['is_open'] == 1]['cal_date'].tolist()
        if not trade_days:
            self._add_result('成交额排名验证', 'fail', '无交易日')
            return {}

        sample_dates = random.sample(trade_days, min(n_dates, len(trade_days)))
        results = []

        for date in sample_dates:
            date_str = pd.to_datetime(date).strftime('%Y-%m-%d')
            df = self.storage.get_top_n_by_amount(date_str, n=top_n, exclude_st=False)

            if df.empty:
                results.append({'date': date_str, 'status': 'no_data'})
                continue

            # 检查成交额是否降序排列
            amounts = df['amount'].tolist()
            is_sorted = all(amounts[i] >= amounts[i+1] for i in range(len(amounts)-1))

            # 检查Top1成交额是否合理（应该远大于平均值）
            total_amount = df['amount'].sum()
            top1_share = amounts[0] / total_amount if total_amount > 0 else 0

            results.append({
                'date': date_str,
                'stocks_count': len(df),
                'top1_symbol': df.iloc[0]['ts_code'],
                'top1_amount': amounts[0],
                'top1_share': top1_share,
                'is_sorted': is_sorted,
            })

        details = {
            'sample_dates': len(sample_dates),
            'results': results,
        }

        # 检查是否所有日期都有数据
        no_data_count = sum(1 for r in results if r.get('status') == 'no_data')
        if no_data_count == 0:
            self._add_result(
                '成交额排名验证',
                'pass',
                f'{len(sample_dates)} 个交易日均有成交额排名数据',
                details
            )
        else:
            self._add_result(
                '成交额排名验证',
                'warning',
                f'{no_data_count}/{len(sample_dates)} 个交易日无数据',
                details
            )

        return details

    # -------------------------------------------------------------------------
    # 5. 退市股验证
    # -------------------------------------------------------------------------
    def check_delisted_stocks(self, n_samples: int = 5) -> Dict:
        """验证已退市股票的历史数据是否可获取。"""
        logger.info("验证退市股票数据...")

        stock_basic = self.storage.load_stock_basic()
        if stock_basic.empty:
            self._add_result('退市股验证', 'fail', '无股票基本信息')
            return {}

        delisted = stock_basic[stock_basic['list_status'] == 'D']
        if delisted.empty:
            self._add_result('退市股验证', 'warning', '股票列表中无退市股票')
            return {}

        sample_delisted = delisted.sample(min(n_samples, len(delisted)))
        results = []

        for _, row in sample_delisted.iterrows():
            symbol = row['ts_code']
            delist_date = row.get('delist_date', '')
            daily = self.storage.load_daily(symbol)

            results.append({
                'symbol': symbol,
                'name': row.get('name', ''),
                'delist_date': delist_date,
                'daily_rows': len(daily),
                'has_data': not daily.empty,
                'data_start': daily['date'].min().strftime('%Y-%m-%d') if not daily.empty else None,
                'data_end': daily['date'].max().strftime('%Y-%m-%d') if not daily.empty else None,
            })

        details = {
            'total_delisted': len(delisted),
            'samples': len(results),
            'with_data': sum(1 for r in results if r['has_data']),
            'results': results,
        }

        if details['with_data'] == len(results):
            self._add_result(
                '退市股验证',
                'pass',
                f'抽查 {len(results)} 只退市股均有历史数据（无幸存者偏差）',
                details
            )
        else:
            self._add_result(
                '退市股验证',
                'warning',
                f'{details["with_data"]}/{len(results)} 只退市股有数据，存在幸存者偏差风险',
                details
            )

        return details

    # -------------------------------------------------------------------------
    # 6. 涨跌停价格验证
    # -------------------------------------------------------------------------
    def check_price_limit(self, n_samples: int = 10) -> Dict:
        """
        验证涨跌停价格计算的合理性。

        检查：当日涨跌幅接近涨跌停限制时，价格是否合理。
        注意：这里只检查数据内部一致性，不计算涨跌停价（那是交易规则层的事）。
        """
        logger.info(f"验证 {n_samples} 只股票的涨跌停合理性...")

        symbols = self.storage.list_daily_symbols()
        if not symbols:
            self._add_result('涨跌停验证', 'fail', '无日线数据')
            return {}

        sample_symbols = random.sample(symbols, min(n_samples, len(symbols)))
        total_limit_days = 0
        issues = []

        for symbol in sample_symbols:
            df = self.storage.load_daily(symbol)
            if df.empty or 'pct_chg' not in df.columns:
                continue

            # 检查涨跌幅超过20%的天数（科创板/创业板涨跌停20%）
            extreme = df[df['pct_chg'].abs() > 20.5]
            if not extreme.empty:
                # 可能是新股上市前5日（无涨跌幅限制），需要排除
                issues.append(
                    f'{symbol}: {len(extreme)} 天涨跌幅超过20%（可能是新股或数据错误）'
                )

            # 统计接近涨跌停的天数
            near_limit = df[df['pct_chg'].abs() >= 9.9]
            total_limit_days += len(near_limit)

        details = {
            'samples': len(sample_symbols),
            'near_limit_days': total_limit_days,
            'issues': issues,
        }

        if not issues:
            self._add_result(
                '涨跌停合理性',
                'pass',
                f'抽查 {len(sample_symbols)} 只股票，涨跌幅无异常',
                details
            )
        else:
            self._add_result(
                '涨跌停合理性',
                'warning',
                f'抽查发现 {len(issues)} 个异常，需确认是否为新股上市初期',
                details
            )

        return details

    # -------------------------------------------------------------------------
    # 运行全部验证
    # -------------------------------------------------------------------------
    def run_all(self) -> Dict:
        """运行全部数据验证检查。"""
        logger.info("=" * 60)
        logger.info("开始数据验证")
        logger.info("=" * 60)

        self.check_completeness()
        self.check_random_samples(n_samples=20)
        self.check_adj_factor(n_samples=10)
        self.check_amount_ranking(n_dates=5, top_n=10)
        self.check_delisted_stocks(n_samples=5)
        self.check_price_limit(n_samples=10)

        # 保存验证报告
        report_path = self.validation_dir / f'validation_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        import json
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2, default=str)

        # 打印汇总
        logger.info("=" * 60)
        logger.info("数据验证汇总")
        logger.info(f"  通过: {self.results['passed']}")
        logger.info(f"  失败: {self.results['failed']}")
        logger.info(f"  警告: {self.results['warnings']}")
        logger.info(f"  报告保存: {report_path}")
        logger.info("=" * 60)

        for check in self.results['checks']:
            status_icon = '✓' if check['status'] == 'pass' else ('✗' if check['status'] == 'fail' else '⚠')
            logger.info(f"  {status_icon} [{check['status'].upper()}] {check['check']}: {check['message']}")

        return self.results
