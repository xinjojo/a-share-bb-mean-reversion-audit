"""
Tushare Pro 数据下载模块

核心接口：
- stock_basic: 股票基本信息（含上市/退市日期，用于避免幸存者偏差）
- trade_cal:   交易日历
- daily:       日线行情（未复权，含 amount 成交额）
- adj_factor:  复权因子（独立下载，避免前复权的未来函数问题）

注意事项：
- 本策略核心需求：daily(含amount) + adj_factor + stock_basic + trade_cal
- Tushare 基础积分即可获取以上接口
- daily 接口返回未复权行情，复权需结合 adj_factor 自行计算
- 绝不使用 pro_bar 的 qfq 模式（前复权会随未来分红调整历史价格，引入未来函数）
"""
import time
import logging
import pandas as pd
import tushare as ts
from pathlib import Path
from typing import List, Optional, Tuple
from tqdm import tqdm

from .storage import DataStorage

logger = logging.getLogger(__name__)


class TushareLoader:
    """Tushare Pro 数据下载器。"""

    def __init__(self, token: str, storage: DataStorage,
                 call_delay: float = 0.12, max_retries: int = 3):
        """
        Args:
            token: Tushare Pro token
            storage: DataStorage 实例
            call_delay: 每次API调用间隔（秒），基础积分每分钟约500次限制
            max_retries: 最大重试次数
        """
        if not token:
            raise ValueError(
                "Tushare token 为空。请设置环境变量 TUSHARE_TOKEN，"
                "或在 config.yaml 中配置 token。\n"
                "注册地址：https://tushare.pro/register"
            )

        ts.set_token(token)
        self.pro = ts.pro_api()
        self.storage = storage
        self.call_delay = call_delay
        self.max_retries = max_retries

    def _call_with_retry(self, func, **kwargs) -> pd.DataFrame:
        """带重试和延迟的 API 调用。"""
        for attempt in range(self.max_retries):
            try:
                time.sleep(self.call_delay)
                df = func(**kwargs)
                return df
            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait = (attempt + 1) * 2
                    logger.warning(f"API调用失败（第{attempt+1}次），{wait}秒后重试: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"API调用失败（已重试{self.max_retries}次）: {e}")
                    raise

    # -------------------------------------------------------------------------
    # 股票基本信息（含退市股，避免幸存者偏差）
    # -------------------------------------------------------------------------
    def download_stock_basic(self, force: bool = False) -> pd.DataFrame:
        """
        下载股票基本信息列表。

        包含：当前上市股票 + 已退市股票 + 暂停上市股票
        这是避免幸存者偏差的关键：必须包含历史退市股票。

        Returns:
            股票基本信息 DataFrame
        """
        filepath = self.storage.raw_dir / 'stock_basic.parquet'
        if filepath.exists() and not force:
            logger.info("股票基本信息已存在，跳过下载（force=True可强制更新）")
            return self.storage.load_stock_basic()

        logger.info("正在下载股票基本信息（含退市股）...")

        # 上市状态：L-上市，D-退市，P-暂停上市
        all_stocks = []
        for list_status in ['L', 'D', 'P']:
            df = self._call_with_retry(
                self.pro.stock_basic,
                exchange='',
                list_status=list_status,
                fields='ts_code,symbol,name,area,industry,fullname,enname,'
                       'cnspell,market,exchange,curr_type,list_date,delist_date,'
                       'is_hs'
            )
            if not df.empty:
                df['list_status'] = list_status
                all_stocks.append(df)
                logger.info(f"  上市状态 {list_status}: {len(df)} 只")

        if all_stocks:
            stock_basic = pd.concat(all_stocks, ignore_index=True)
            stock_basic = stock_basic.drop_duplicates(subset=['ts_code'], keep='first')
            self.storage.save_stock_basic(stock_basic)
            logger.info(f"股票基本信息下载完成：共 {len(stock_basic)} 只（含退市股）")
            return stock_basic
        else:
            logger.error("股票基本信息下载失败")
            return pd.DataFrame()

    # -------------------------------------------------------------------------
    # 交易日历
    # -------------------------------------------------------------------------
    def download_trade_cal(self, start_date: str, end_date: str,
                           force: bool = False) -> pd.DataFrame:
        """
        下载交易日历。

        Args:
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）

        Returns:
            交易日历 DataFrame
        """
        filepath = self.storage.raw_dir / 'trade_cal.parquet'
        if filepath.exists() and not force:
            logger.info("交易日历已存在，跳过下载")
            return self.storage.load_trade_cal()

        logger.info(f"正在下载交易日历：{start_date} ~ {end_date}")
        df = self._call_with_retry(
            self.pro.trade_cal,
            exchange='SSE',
            start_date=start_date,
            end_date=end_date
        )

        if not df.empty:
            df['cal_date'] = pd.to_datetime(df['cal_date'])
            df = df.sort_values('cal_date').reset_index(drop=True)
            self.storage.save_trade_cal(df)
            trade_days = df[df['is_open'] == 1]
            logger.info(f"交易日历下载完成：共 {len(df)} 天，其中交易日 {len(trade_days)} 天")
        else:
            logger.error("交易日历下载失败")

        return df

    # -------------------------------------------------------------------------
    # 日线行情（未复权，含成交额 amount）
    # -------------------------------------------------------------------------
    def download_daily(self, symbols: List[str], start_date: str, end_date: str,
                       force: bool = False) -> Tuple[int, int]:
        """
        下载日线行情（未复权，含 amount 成交额）。

        Tushare daily 接口字段：
            ts_code, trade_date, open, high, low, close, pre_close,
            change, pct_chg, vol, amount
        注意：vol 单位是手（100股），amount 单位是千元

        Args:
            symbols: 股票代码列表
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）
            force: 是否强制重新下载

        Returns:
            (成功数量, 失败数量)
        """
        success = 0
        failed = 0
        failed_symbols = []

        logger.info(f"开始下载日线行情：{len(symbols)} 只股票，{start_date} ~ {end_date}")

        for symbol in tqdm(symbols, desc="下载日线行情"):
            try:
                # 检查是否已下载（非强制模式下跳过）
                if not force and self.storage.has_daily(symbol):
                    existing = self.storage.load_daily(symbol)
                    if not existing.empty:
                        # 检查数据覆盖范围
                        existing_min = existing['date'].min().strftime('%Y%m%d')
                        existing_max = existing['date'].max().strftime('%Y%m%d')
                        if existing_min <= start_date and existing_max >= end_date:
                            success += 1
                            continue

                df = self._call_with_retry(
                    self.pro.daily,
                    ts_code=symbol,
                    start_date=start_date,
                    end_date=end_date
                )

                if df.empty:
                    logger.debug(f"  {symbol}: 无数据（可能已退市或区间内未上市）")
                    success += 1
                    continue

                # 标准化列名和格式
                df = df.rename(columns={'trade_date': 'date'})
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)

                # 确保关键列存在
                required_cols = ['ts_code', 'date', 'open', 'high', 'low', 'close',
                                 'pre_close', 'change', 'pct_chg', 'vol', 'amount']
                for col in required_cols:
                    if col not in df.columns:
                        df[col] = None

                self.storage.save_daily(symbol, df)
                success += 1

            except Exception as e:
                failed += 1
                failed_symbols.append(symbol)
                logger.warning(f"  {symbol} 下载失败: {e}")

        logger.info(f"日线行情下载完成：成功 {success}，失败 {failed}")
        if failed_symbols:
            logger.warning(f"失败股票列表（前20）: {failed_symbols[:20]}")

        return success, failed

    # -------------------------------------------------------------------------
    # 复权因子（独立下载，避免前复权的未来函数）
    # -------------------------------------------------------------------------
    def download_adj_factor(self, symbols: List[str], start_date: str, end_date: str,
                            force: bool = False) -> Tuple[int, int]:
        """
        下载复权因子。

        Tushare adj_factor 接口字段：
            ts_code, trade_date, adj_factor
        复权因子 = 后复权价格 / 不复权价格
        后复权价格 = 不复权价格 × adj_factor

        关键：使用独立的复权因子，而不是接口内的前复权数据，
        因为前复权价格会随未来分红调整历史价格，引入未来函数。

        Args:
            symbols: 股票代码列表
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）

        Returns:
            (成功数量, 失败数量)
        """
        success = 0
        failed = 0

        logger.info(f"开始下载复权因子：{len(symbols)} 只股票")

        for symbol in tqdm(symbols, desc="下载复权因子"):
            try:
                df = self._call_with_retry(
                    self.pro.adj_factor,
                    ts_code=symbol,
                    start_date=start_date,
                    end_date=end_date
                )

                if df.empty:
                    success += 1
                    continue

                df = df.rename(columns={'trade_date': 'date'})
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date').reset_index(drop=True)

                self.storage.save_adj_factor(symbol, df)
                success += 1

            except Exception as e:
                failed += 1
                logger.warning(f"  {symbol} 复权因子下载失败: {e}")

        logger.info(f"复权因子下载完成：成功 {success}，失败 {failed}")
        return success, failed

    # -------------------------------------------------------------------------
    # 一键下载全部数据
    # -------------------------------------------------------------------------
    def download_all(self, start_date: str, end_date: str,
                     skip_existing: bool = True) -> dict:
        """
        一键下载回测所需全部数据。

        下载顺序：
        1. 股票基本信息（含退市股）
        2. 交易日历
        3. 日线行情（含成交额）
        4. 复权因子

        Args:
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）
            skip_existing: 是否跳过已下载的股票

        Returns:
            下载结果统计
        """
        results = {
            'stock_basic': 0,
            'trade_cal': 0,
            'daily_success': 0,
            'daily_failed': 0,
            'adj_factor_success': 0,
            'adj_factor_failed': 0,
        }

        # 1. 股票基本信息
        stock_basic = self.download_stock_basic(force=not skip_existing)
        results['stock_basic'] = len(stock_basic)

        if stock_basic.empty:
            logger.error("股票基本信息为空，无法继续下载")
            return results

        # 过滤股票池（根据配置）
        symbols = self._filter_symbols(stock_basic)
        logger.info(f"待下载股票数量：{len(symbols)}（已过滤北交所等）")

        # 2. 交易日历
        trade_cal = self.download_trade_cal(start_date, end_date, force=not skip_existing)
        results['trade_cal'] = len(trade_cal)

        # 3. 日线行情
        daily_success, daily_failed = self.download_daily(
            symbols, start_date, end_date, force=not skip_existing
        )
        results['daily_success'] = daily_success
        results['daily_failed'] = daily_failed

        # 4. 复权因子
        adj_success, adj_failed = self.download_adj_factor(
            symbols, start_date, end_date, force=not skip_existing
        )
        results['adj_factor_success'] = adj_success
        results['adj_factor_failed'] = adj_failed

        logger.info("=" * 60)
        logger.info("全部数据下载完成，统计：")
        for k, v in results.items():
            logger.info(f"  {k}: {v}")
        logger.info("=" * 60)

        return results

    def _filter_symbols(self, stock_basic: pd.DataFrame) -> List[str]:
        """
        过滤股票池。

        默认排除：
        - 北交所（8/4开头，流动性和涨跌幅规则差异大）
        - 保留：沪深主板（60/00开头）、创业板（30开头）、科创板（68开头）

        注意：ST/*ST 和新股在回测时动态过滤，下载阶段保留全部。
        """
        df = stock_basic.copy()

        # 排除北交所
        df = df[~df['ts_code'].str.startswith(('8', '4', '9'))]

        # 只保留 A 股（排除 B 股等）
        df = df[df['ts_code'].str.endswith(('.SH', '.SZ'))]

        return df['ts_code'].tolist()
