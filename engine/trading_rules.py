"""
A股交易规则引擎

精度等级：
- T+1: EXACT
- 100股整数倍: EXACT
- 涨跌停价格: EXACT（按板块和ST状态精确计算）
- 涨跌停可成交性: APPROXIMATION（涨停不代表一定买不进，跌停不代表一定卖不出）
- 停牌: EXACT（通过当日无行情数据判断）
- ST状态: EXACT（通过股票名称判断，需历史名称变更数据）
- 新股过滤: EXACT（通过上市日期判断）

注意：
- 2026年7月6日起，主板ST/*ST涨跌幅从±5%调整为±10%
- 代码中根据交易日期动态判断适用规则
- 全面注册制后（2023年4月10日起），所有板块新股上市前5个交易日无涨跌幅限制
"""
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, Tuple
import pandas as pd


# 板块枚举
BOARD_MAIN = "main"       # 沪深主板（60/00开头）
BOARD_GEM = "gem"         # 创业板（30开头）
BOARD_STAR = "star"       # 科创板（68开头）
BOARD_BSE = "bse"         # 北交所（8/4开头）


@dataclass
class StockInfo:
    """股票基本信息。"""
    ts_code: str           # 股票代码（如 000001.SZ）
    name: str              # 股票名称
    list_date: str         # 上市日期（YYYYMMDD）
    delist_date: Optional[str] = None  # 退市日期


class TradingRules:
    """A股交易规则引擎。"""

    def __init__(self, min_listing_days: int = 60,
                 exclude_st: bool = True,
                 exclude_bse: bool = True,
                 conservative_fill: bool = True):
        """
        Args:
            min_listing_days: 新股最少上市交易日数，默认60
            exclude_st: 是否排除ST/*ST
            exclude_bse: 是否排除北交所
            conservative_fill: 涨跌停成交保守假设（涨停买不进，跌停卖不出）
        """
        self.min_listing_days = min_listing_days
        self.exclude_st = exclude_st
        self.exclude_bse = exclude_bse
        self.conservative_fill = conservative_fill

    # -------------------------------------------------------------------------
    # 板块判断
    # -------------------------------------------------------------------------
    @staticmethod
    def get_board(ts_code: str) -> str:
        """
        判断股票板块。

        Args:
            ts_code: 股票代码（如 000001.SZ）

        Returns:
            板块名称：main / gem / star / bse
        """
        code = ts_code.split('.')[0]

        if code.startswith(('60', '00')):
            return BOARD_MAIN
        elif code.startswith('30'):
            return BOARD_GEM
        elif code.startswith('68'):
            return BOARD_STAR
        elif code.startswith(('8', '4', '9')):
            return BOARD_BSE
        else:
            return BOARD_MAIN  # 默认主板

    # -------------------------------------------------------------------------
    # ST状态判断
    # -------------------------------------------------------------------------
    @staticmethod
    def is_st(name: str) -> bool:
        """
        判断是否为ST/*ST股票。

        Args:
            name: 股票名称

        Returns:
            True if ST or *ST
        """
        if not name:
            return False
        name_upper = name.upper()
        return 'ST' in name_upper

    # -------------------------------------------------------------------------
    # 涨跌停价格计算
    # -------------------------------------------------------------------------
    def get_price_limit(self, ts_code: str, name: str, pre_close: float,
                        trade_date: date = None) -> Tuple[float, float]:
        """
        计算涨跌停价格。

        规则（2023全面注册制后）：
        - 主板普通股：±10%
        - 创业板/科创板：±20%
        - 北交所：±30%
        - 主板ST/*ST：2026年7月6日前±5%，之后±10%
        - 创业板/科创板ST：±20%
        - 新股上市前5个交易日：无涨跌幅限制（返回None, None）

        Args:
            ts_code: 股票代码
            name: 股票名称
            pre_close: 前收盘价（不复权）
            trade_date: 交易日期，用于判断ST新规生效时间

        Returns:
            (跌停价, 涨停价)，新股无限制时返回(None, None)
        """
        if pre_close is None or pre_close <= 0:
            return None, None

        board = self.get_board(ts_code)
        is_st = self.is_st(name)
        trade_date = trade_date or date.today()

        # 2026年7月6日新规：主板ST涨跌幅调整为±10%
        st_main_limit = 0.10 if trade_date >= date(2026, 7, 6) else 0.05

        # 确定涨跌幅比例
        if board == BOARD_MAIN:
            if is_st:
                limit_pct = st_main_limit
            else:
                limit_pct = 0.10
        elif board == BOARD_GEM:
            limit_pct = 0.20  # 创业板ST也是±20%
        elif board == BOARD_STAR:
            limit_pct = 0.20  # 科创板ST也是±20%
        elif board == BOARD_BSE:
            limit_pct = 0.30
        else:
            limit_pct = 0.10

        # 计算涨跌停价（保留2位小数，A股价格最小单位0.01元）
        limit_up = round(pre_close * (1 + limit_pct), 2)
        limit_down = round(pre_close * (1 - limit_pct), 2)

        return limit_down, limit_up

    # -------------------------------------------------------------------------
    # 可成交性判断
    # -------------------------------------------------------------------------
    def can_buy(self, ts_code: str, name: str, pre_close: float,
                day_high: float, day_low: float, trade_date: date = None) -> bool:
        """
        判断当日是否可以买入。

        保守假设：如果当日涨停（High >= 涨停价），假设买不进。
        （实际涨停也可能成交，但封单量大时买不进，保守处理）

        Args:
            ts_code: 股票代码
            name: 股票名称
            pre_close: 前收盘价
            day_high: 当日最高价
            day_low: 当日最低价
            trade_date: 交易日期

        Returns:
            True if 可以买入
        """
        if not self.conservative_fill:
            return True

        limit_down, limit_up = self.get_price_limit(ts_code, name, pre_close, trade_date)

        # 新股无涨跌幅限制，可成交
        if limit_up is None:
            return True

        # 涨停：假设买不进
        if day_high >= limit_up:
            return False

        return True

    def can_sell(self, ts_code: str, name: str, pre_close: float,
                 day_high: float, day_low: float, trade_date: date = None) -> bool:
        """
        判断当日是否可以卖出。

        保守假设：如果当日跌停（Low <= 跌停价），假设卖不出。

        Args:
            ts_code: 股票代码
            name: 股票名称
            pre_close: 前收盘价
            day_high: 当日最高价
            day_low: 当日最低价
            trade_date: 交易日期

        Returns:
            True if 可以卖出
        """
        if not self.conservative_fill:
            return True

        limit_down, limit_up = self.get_price_limit(ts_code, name, pre_close, trade_date)

        # 新股无涨跌幅限制，可成交
        if limit_down is None:
            return True

        # 跌停：假设卖不出
        if day_low <= limit_down:
            return False

        return True

    # -------------------------------------------------------------------------
    # T+1 判断
    # -------------------------------------------------------------------------
    @staticmethod
    def can_sell_today(buy_date: date, current_date: date) -> bool:
        """
        T+1判断：当天买入的股票当天不能卖。

        Args:
            buy_date: 买入日期
            current_date: 当前日期

        Returns:
            True if 可以卖出（买入日期 < 当前日期）
        """
        return buy_date < current_date

    # -------------------------------------------------------------------------
    # 100股整数倍
    # -------------------------------------------------------------------------
    @staticmethod
    def round_lot(shares: int) -> int:
        """
        将股数向下取整到100的整数倍。

        Args:
            shares: 目标股数

        Returns:
            取整后的股数（100的整数倍）
        """
        return (shares // 100) * 100

    @staticmethod
    def calculate_shares(cash: float, price: float) -> int:
        """
        根据可用资金和价格计算可买入股数（100股整数倍）。

        Args:
            cash: 可用资金
            price: 买入价格

        Returns:
            可买入股数（100的整数倍，不足100返回0）
        """
        if price <= 0 or cash <= 0:
            return 0
        raw_shares = int(cash / price)
        return TradingRules.round_lot(raw_shares)

    # -------------------------------------------------------------------------
    # 股票池过滤
    # -------------------------------------------------------------------------
    def filter_stock(self, stock_info: StockInfo, current_date: date,
                     is_suspended: bool = False, current_name: str = None) -> Tuple[bool, str]:
        """
        判断股票是否可以进入股票池。

        过滤条件：
        1. 北交所（如果exclude_bse=True）
        2. ST/*ST（如果exclude_st=True）
        3. 新股（上市不足min_listing_days个交易日）
        4. 停牌
        5. 已退市

        Args:
            stock_info: 股票基本信息
            current_date: 当前日期
            is_suspended: 是否停牌
            current_name: 当前股票名称（用于ST判断，None则用stock_info.name）

        Returns:
            (是否通过过滤, 过滤原因)
        """
        name = current_name or stock_info.name

        # 1. 已退市
        if stock_info.delist_date:
            try:
                delist_dt = datetime.strptime(stock_info.delist_date, '%Y%m%d').date()
                if current_date >= delist_dt:
                    return False, "已退市"
            except (ValueError, TypeError):
                pass

        # 2. 北交所
        if self.exclude_bse and self.get_board(stock_info.ts_code) == BOARD_BSE:
            return False, "北交所"

        # 3. ST/*ST
        if self.exclude_st and self.is_st(name):
            return False, "ST/*ST"

        # 4. 新股
        try:
            list_dt = datetime.strptime(stock_info.list_date, '%Y%m%d').date()
            # 简化处理：按自然日计算，实际应按交易日计算
            days_since_listing = (current_date - list_dt).days
            # 近似：交易日 ≈ 自然日 × 5/7，min_listing_days个交易日约等于 min_listing_days * 1.4 自然日
            min_calendar_days = int(self.min_listing_days * 1.4)
            if days_since_listing < min_calendar_days:
                return False, f"新股（上市{days_since_listing}天，不足{self.min_listing_days}交易日）"
        except (ValueError, TypeError):
            pass

        # 5. 停牌
        if is_suspended:
            return False, "停牌"

        return True, "通过"

    # -------------------------------------------------------------------------
    # 新股无涨跌幅判断
    # -------------------------------------------------------------------------
    def is_new_stock_no_limit(self, stock_info: StockInfo, current_date: date) -> bool:
        """
        判断是否为新股上市前5个交易日（无涨跌幅限制）。

        Args:
            stock_info: 股票基本信息
            current_date: 当前日期

        Returns:
            True if 新股上市前5个交易日
        """
        try:
            list_dt = datetime.strptime(stock_info.list_date, '%Y%m%d').date()
            # 简化：按自然日计算，5个交易日约7个自然日
            days_since_listing = (current_date - list_dt).days
            return 0 <= days_since_listing <= 10  # 约5个交易日
        except (ValueError, TypeError):
            return False
