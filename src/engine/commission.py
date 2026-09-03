"""
A股交易费用模型

精度等级：EXACT（严格按照2025-2026最新规则计算）

费用项目：
1. 佣金：买卖双向，max(成交金额 × 费率, 最低5元)
2. 印花税：仅卖出，成交金额 × 0.05%（万5，2023年8月28日减半）
3. 过户费：买卖双向，成交金额 × 0.001%（万0.1，2024年起沪深统一）
4. 滑点：买入抬高，卖出压低

注意：
- 佣金最低5元仅适用于主板/创业板，北交所无此限制（本策略排除北交所）
- 印花税仅卖出时收取
- 过户费2024年前深市免收，回测历史数据时需根据日期动态调整
  （第一版2020-2024区间，2020-2023深市无过户费，2024起统一）
  为简化，第一版统一按万0.1计算，差异极小（10万交易仅差1元）
"""
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class FeeConfig:
    """费用配置。"""
    # 佣金
    commission_rate: float = 0.00025    # 万2.5
    commission_min: float = 5.0          # 最低5元

    # 印花税（仅卖出）
    stamp_tax_rate: float = 0.0005       # 万5

    # 过户费（买卖双向）
    transfer_fee_rate: float = 0.00001    # 万0.1

    # 滑点
    slippage_enabled: bool = True
    slippage_mode: str = "percent"        # "percent" / "fixed"
    slippage_rate: float = 0.0001         # 万1
    slippage_fixed: float = 0.01          # 0.01元


@dataclass
class FeeResult:
    """单笔交易费用结果。"""
    price: float              # 实际成交价（含滑点）
    amount: float             # 成交金额 = price × shares
    commission: float         # 佣金
    stamp_tax: float          # 印花税
    transfer_fee: float       # 过户费
    slippage_cost: float      # 滑点损失（相对无滑点成交价的差额）
    total_fee: float          # 总费用
    net_cash_flow: float      # 净现金流（买入为负，卖出为正）


class FeeCalculator:
    """A股交易费用计算器。"""

    def __init__(self, config: FeeConfig = None):
        """
        Args:
            config: 费用配置，None则使用默认值
        """
        self.config = config or FeeConfig()

    def calculate(self, side: str, raw_price: float, shares: int) -> FeeResult:
        """
        计算单笔交易费用。

        Args:
            side: "buy" 或 "sell"
            raw_price: 信号价格（未含滑点）
            shares: 成交股数

        Returns:
            FeeResult 费用结果
        """
        cfg = self.config

        # 1. 计算滑点后的实际成交价
        if cfg.slippage_enabled:
            if cfg.slippage_mode == "percent":
                if side == "buy":
                    price = raw_price * (1 + cfg.slippage_rate)
                else:
                    price = raw_price * (1 - cfg.slippage_rate)
            else:  # fixed
                if side == "buy":
                    price = raw_price + cfg.slippage_fixed
                else:
                    price = raw_price - cfg.slippage_fixed
        else:
            price = raw_price

        # 2. 成交金额
        amount = price * shares

        # 3. 滑点损失（相对无滑点成交价）
        slippage_cost = abs(price - raw_price) * shares

        # 4. 佣金（买卖双向，最低5元）
        commission = max(amount * cfg.commission_rate, cfg.commission_min)

        # 5. 印花税（仅卖出）
        if side == "sell":
            stamp_tax = amount * cfg.stamp_tax_rate
        else:
            stamp_tax = 0.0

        # 6. 过户费（买卖双向）
        transfer_fee = amount * cfg.transfer_fee_rate

        # 7. 总费用
        total_fee = commission + stamp_tax + transfer_fee

        # 8. 净现金流
        if side == "buy":
            net_cash_flow = -(amount + total_fee)
        else:
            net_cash_flow = amount - total_fee

        return FeeResult(
            price=round(price, 4),
            amount=round(amount, 2),
            commission=round(commission, 2),
            stamp_tax=round(stamp_tax, 2),
            transfer_fee=round(transfer_fee, 2),
            slippage_cost=round(slippage_cost, 2),
            total_fee=round(total_fee, 2),
            net_cash_flow=round(net_cash_flow, 2),
        )

    def calculate_buy(self, raw_price: float, shares: int) -> FeeResult:
        """计算买入费用。"""
        return self.calculate("buy", raw_price, shares)

    def calculate_sell(self, raw_price: float, shares: int) -> FeeResult:
        """计算卖出费用。"""
        return self.calculate("sell", raw_price, shares)

    @classmethod
    def from_config_dict(cls, config_dict: dict) -> "FeeCalculator":
        """
        从配置字典创建费用计算器。

        Args:
            config_dict: config.yaml 中的 fees 配置段

        Returns:
            FeeCalculator 实例
        """
        cfg = FeeConfig(
            commission_rate=config_dict.get('commission', {}).get('rate', 0.00025),
            commission_min=config_dict.get('commission', {}).get('min', 5.0),
            stamp_tax_rate=config_dict.get('stamp_tax', {}).get('rate', 0.0005),
            transfer_fee_rate=config_dict.get('transfer_fee', {}).get('rate', 0.00001),
            slippage_enabled=config_dict.get('slippage', {}).get('enabled', True),
            slippage_mode=config_dict.get('slippage', {}).get('mode', 'percent'),
            slippage_rate=config_dict.get('slippage', {}).get('rate', 0.0001),
            slippage_fixed=config_dict.get('slippage', {}).get('fixed', 0.01),
        )
        return cls(cfg)
