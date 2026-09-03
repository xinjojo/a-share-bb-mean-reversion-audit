"""
仓位管理模块

精度等级：EXACT（严格按照实际成交股数和费用计算加权平均成本）

核心功能：
1. 5层动态仓位管理（每层20%资金）
2. 加权平均成本计算（含交易费用）
3. T+1可卖数量管理
4. 止盈价/止损价计算
5. 加仓/减仓/清仓操作
6. 层数重置（止盈/止损清仓后重新买入从第1层开始）

注意：
- 平均成本包含买入时的所有费用（佣金、过户费、滑点）
- 卖出时费用不计入成本，直接计入已实现盈亏
- T+1：当天买入的股数当天不可卖，下一交易日起可卖
"""
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Dict
from collections import defaultdict


@dataclass
class Lot:
    """一笔买入记录（一个批次）。"""
    buy_date: date          # 买入日期
    shares: int             # 买入股数
    price: float            # 买入成交价（含滑点）
    fee: float              # 买入费用（佣金+过户费）
    cost_basis: float       # 该批次成本 = price × shares + fee

    @property
    def avg_cost_per_share(self) -> float:
        """每股平均成本（含费用）。"""
        return self.cost_basis / self.shares if self.shares > 0 else 0.0


@dataclass
class Position:
    """单只股票持仓。"""
    ts_code: str                              # 股票代码
    name: str = ""                            # 股票名称
    lots: List[Lot] = field(default_factory=list)  # 买入批次列表
    current_level: int = 0                    # 当前仓位层数（0=空仓，1-5）
    max_levels: int = 5                       # 最大层数
    level_ratio: float = 0.20                 # 每层资金比例

    # 止盈止损参数
    take_profit_ratio: float = 0.015          # 止盈比例
    stop_loss_price: Optional[float] = None   # 止损价（None表示未设置）

    @property
    def total_shares(self) -> int:
        """总持仓股数。"""
        return sum(lot.shares for lot in self.lots)

    @property
    def total_cost_basis(self) -> float:
        """总持仓成本（含所有买入费用）。"""
        return sum(lot.cost_basis for lot in self.lots)

    @property
    def average_cost(self) -> float:
        """加权平均成本（每股，含费用）。"""
        if self.total_shares == 0:
            return 0.0
        return self.total_cost_basis / self.total_shares

    @property
    def take_profit_price(self) -> float:
        """止盈价 = 平均成本 × (1 + 止盈比例)。"""
        return self.average_cost * (1 + self.take_profit_ratio)

    @property
    def is_empty(self) -> bool:
        """是否空仓。"""
        return self.total_shares == 0

    @property
    def is_full(self) -> bool:
        """是否已满仓（达到最大层数）。"""
        return self.current_level >= self.max_levels

    def get_sellable_shares(self, current_date: date) -> int:
        """
        获取当前可卖出股数（T+1规则）。

        当天买入的股数当天不可卖，只有买入日期 < 当前日期的批次可卖。

        Args:
            current_date: 当前日期

        Returns:
            可卖出股数
        """
        return sum(
            lot.shares for lot in self.lots
            if lot.buy_date < current_date
        )

    def add_lot(self, buy_date: date, shares: int, price: float, fee: float) -> None:
        """
        增加一个买入批次（加仓）。

        Args:
            buy_date: 买入日期
            shares: 买入股数
            price: 买入成交价（含滑点）
            fee: 买入费用（佣金+过户费）
        """
        cost_basis = price * shares + fee
        self.lots.append(Lot(
            buy_date=buy_date,
            shares=shares,
            price=price,
            fee=fee,
            cost_basis=cost_basis
        ))
        self.current_level += 1

    def sell_shares(self, sell_date: date, shares: int, price: float,
                     fee: float) -> Dict:
        """
        卖出部分持仓。

        按照FIFO（先进先出）原则卖出批次。

        Args:
            sell_date: 卖出日期
            shares: 卖出股数
            price: 卖出成交价（含滑点）
            fee: 卖出费用（佣金+印花税+过户费）

        Returns:
            卖出结果字典，包含已实现盈亏等信息

        Raises:
            ValueError: 可卖股数不足
        """
        sellable = self.get_sellable_shares(sell_date)
        if shares > sellable:
            raise ValueError(
                f"可卖股数不足：请求卖出{shares}股，可卖{sellable}股（T+1限制）"
            )

        remaining_to_sell = shares
        total_sold_cost = 0.0
        total_sold_shares = 0
        sold_lots = []

        # FIFO：按买入日期从早到晚卖出
        self.lots.sort(key=lambda x: x.buy_date)

        for lot in self.lots:
            if remaining_to_sell <= 0:
                break
            if lot.buy_date >= sell_date:
                continue  # T+1：当天买入的不可卖

            sell_from_lot = min(lot.shares, remaining_to_sell)
            if sell_from_lot > 0:
                cost_per_share = lot.cost_basis / lot.shares
                sold_cost = cost_per_share * sell_from_lot
                total_sold_cost += sold_cost
                total_sold_shares += sell_from_lot
                sold_lots.append({
                    'buy_date': lot.buy_date,
                    'shares': sell_from_lot,
                    'cost_per_share': cost_per_share,
                })

                lot.shares -= sell_from_lot
                lot.cost_basis -= sold_cost
                remaining_to_sell -= sell_from_lot

        # 清理空批次
        self.lots = [lot for lot in self.lots if lot.shares > 0]

        # 计算已实现盈亏
        gross_proceeds = price * total_sold_shares
        net_proceeds = gross_proceeds - fee
        realized_pnl = net_proceeds - total_sold_cost

        # 如果清仓，重置层数
        if self.is_empty:
            self.current_level = 0
            self.stop_loss_price = None

        return {
            'shares_sold': total_sold_shares,
            'sell_price': price,
            'gross_proceeds': round(gross_proceeds, 2),
            'sell_fee': round(fee, 2),
            'net_proceeds': round(net_proceeds, 2),
            'cost_basis_sold': round(total_sold_cost, 2),
            'realized_pnl': round(realized_pnl, 2),
            'sold_lots': sold_lots,
            'position_closed': self.is_empty,
        }

    def get_unrealized_pnl(self, current_price: float) -> float:
        """
        计算未实现盈亏（浮盈浮亏）。

        Args:
            current_price: 当前价格

        Returns:
            未实现盈亏
        """
        if self.total_shares == 0:
            return 0.0
        market_value = current_price * self.total_shares
        return market_value - self.total_cost_basis

    def get_position_summary(self, current_price: float = None) -> Dict:
        """
        获取持仓摘要。

        Args:
            current_price: 当前价格（可选，用于计算浮盈）

        Returns:
            持仓摘要字典
        """
        summary = {
            'ts_code': self.ts_code,
            'name': self.name,
            'total_shares': self.total_shares,
            'current_level': self.current_level,
            'max_levels': self.max_levels,
            'average_cost': round(self.average_cost, 4),
            'total_cost_basis': round(self.total_cost_basis, 2),
            'take_profit_price': round(self.take_profit_price, 4),
            'stop_loss_price': round(self.stop_loss_price, 4) if self.stop_loss_price else None,
            'is_empty': self.is_empty,
            'is_full': self.is_full,
            'lots_count': len(self.lots),
        }
        if current_price is not None:
            summary['current_price'] = current_price
            summary['market_value'] = round(current_price * self.total_shares, 2)
            summary['unrealized_pnl'] = round(self.get_unrealized_pnl(current_price), 2)
            summary['unrealized_pnl_pct'] = round(
                self.get_unrealized_pnl(current_price) / self.total_cost_basis * 100, 2
            ) if self.total_cost_basis > 0 else 0.0
        return summary


class PositionManager:
    """
    仓位管理器（单股策略，同时最多持有一只股票）。

    本策略核心约束：账户同时最多只持有一只股票。
    只有当前持仓完全清仓后，才重新扫描市场寻找新的成交额Top1股票。
    """

    def __init__(self, max_levels: int = 5, level_ratio: float = 0.20,
                 take_profit_ratio: float = 0.015):
        """
        Args:
            max_levels: 最大层数，默认5
            level_ratio: 每层资金比例，默认0.20
            take_profit_ratio: 止盈比例，默认0.015
        """
        self.max_levels = max_levels
        self.level_ratio = level_ratio
        self.take_profit_ratio = take_profit_ratio
        self.current_position: Optional[Position] = None

    @property
    def has_position(self) -> bool:
        """是否有持仓。"""
        return self.current_position is not None and not self.current_position.is_empty

    @property
    def current_symbol(self) -> Optional[str]:
        """当前持仓股票代码。"""
        return self.current_position.ts_code if self.has_position else None

    def open_position(self, ts_code: str, name: str, buy_date: date,
                      shares: int, price: float, fee: float) -> Position:
        """
        开新仓（第1层）。

        必须当前空仓才能开新仓。

        Args:
            ts_code: 股票代码
            name: 股票名称
            buy_date: 买入日期
            shares: 买入股数
            price: 买入成交价
            fee: 买入费用

        Returns:
            新建的Position对象

        Raises:
            ValueError: 当前已有持仓
        """
        if self.has_position:
            raise ValueError(
                f"当前已有持仓 {self.current_symbol}，单股策略不允许同时持有多只股票"
            )

        position = Position(
            ts_code=ts_code,
            name=name,
            max_levels=self.max_levels,
            level_ratio=self.level_ratio,
            take_profit_ratio=self.take_profit_ratio,
        )
        position.add_lot(buy_date, shares, price, fee)
        self.current_position = position
        return position

    def add_to_position(self, buy_date: date, shares: int, price: float,
                        fee: float) -> Position:
        """
        加仓（下一层）。

        必须当前有持仓且未满仓才能加仓。

        Args:
            buy_date: 买入日期
            shares: 买入股数
            price: 买入成交价
            fee: 买入费用

        Returns:
            更新后的Position对象

        Raises:
            ValueError: 当前无持仓或已满仓
        """
        if not self.has_position:
            raise ValueError("当前无持仓，无法加仓")
        if self.current_position.is_full:
            raise ValueError(
                f"已达最大层数 {self.max_levels}，无法继续加仓"
            )

        self.current_position.add_lot(buy_date, shares, price, fee)
        return self.current_position

    def sell_position(self, sell_date: date, shares: int, price: float,
                      fee: float) -> Dict:
        """
        卖出持仓。

        Args:
            sell_date: 卖出日期
            shares: 卖出股数
            price: 卖出成交价
            fee: 卖出费用

        Returns:
            卖出结果字典
        """
        if not self.has_position:
            raise ValueError("当前无持仓，无法卖出")

        result = self.current_position.sell_shares(sell_date, shares, price, fee)

        # 如果清仓，释放当前持仓
        if self.current_position.is_empty:
            self.current_position = None

        return result

    def sell_all(self, sell_date: date, price: float, fee: float) -> Dict:
        """
        卖出全部可卖持仓。

        Args:
            sell_date: 卖出日期
            price: 卖出成交价
            fee: 卖出费用（按全部可卖股数计算）

        Returns:
            卖出结果字典
        """
        if not self.has_position:
            raise ValueError("当前无持仓，无法卖出")

        sellable = self.current_position.get_sellable_shares(sell_date)
        if sellable == 0:
            raise ValueError("当前无可卖股数（T+1限制）")

        return self.sell_position(sell_date, sellable, price, fee)

    def get_sellable_shares(self, current_date: date) -> int:
        """获取当前可卖股数。"""
        if not self.has_position:
            return 0
        return self.current_position.get_sellable_shares(current_date)

    def get_summary(self, current_price: float = None) -> Optional[Dict]:
        """获取当前持仓摘要。"""
        if not self.has_position:
            return None
        return self.current_position.get_position_summary(current_price)
