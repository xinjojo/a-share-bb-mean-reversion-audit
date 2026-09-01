"""
AKShare 备用数据加载模块

AKShare 是完全免费的开源财经数据接口库，数据源为东方财富、新浪等网站爬虫。

注意事项：
- AKShare 没有独立的复权因子接口，复权在接口内处理
- 前复权价格会随未来分红调整，存在未来函数风险
- 退市股支持需验证
- 接口可能因上游网站改版而失效
- 作为 Tushare 的备用数据源，不建议作为主数据源
"""
import time
import logging
import pandas as pd
import akshare as ak
from typing import List, Tuple
from tqdm import tqdm

from .storage import DataStorage

logger = logging.getLogger(__name__)


class AKShareLoader:
    """AKShare 备用数据加载器。"""

    def __init__(self, storage: DataStorage, call_delay: float = 0.5,
                 max_retries: int = 3):
        """
        Args:
            storage: DataStorage 实例
            call_delay: 每次调用间隔（秒），避免被封IP
            max_retries: 最大重试次数
        """
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
                    wait = (attempt + 1) * 3
                    logger.warning(f"AKShare调用失败（第{attempt+1}次），{wait}秒后重试: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"AKShare调用失败（已重试{self.max_retries}次）: {e}")
                    raise

    def download_stock_basic(self) -> pd.DataFrame:
        """
        下载股票基本信息。

        注意：AKShare 的股票列表只包含当前上市股票，不包含已退市股票。
        存在幸存者偏差风险，仅作为备用。
        """
        logger.info("正在通过AKShare下载股票基本信息...")

        # 沪市A股
        sh_df = self._call_with_retry(ak.stock_info_sh_name_code, symbol="主板A股")
        # 深市A股
        sz_df = self._call_with_retry(ak.stock_info_sz_name_code, indicator="A股列表")

        all_stocks = []

        if not sh_df.empty:
            sh_df = sh_df.rename(columns={
                '证券代码': 'symbol',
                '证券简称': 'name',
                '上市日期': 'list_date'
            })
            sh_df['ts_code'] = sh_df['symbol'] + '.SH'
            sh_df['exchange'] = 'SH'
            sh_df['list_status'] = 'L'
            all_stocks.append(sh_df[['ts_code', 'symbol', 'name', 'exchange',
                                      'list_date', 'list_status']])

        if not sz_df.empty:
            sz_df = sz_df.rename(columns={
                'A股代码': 'symbol',
                'A股简称': 'name',
                'A股上市日期': 'list_date'
            })
            sz_df['ts_code'] = sz_df['symbol'] + '.SZ'
            sz_df['exchange'] = 'SZ'
            sz_df['list_status'] = 'L'
            all_stocks.append(sz_df[['ts_code', 'symbol', 'name', 'exchange',
                                      'list_date', 'list_status']])

        if all_stocks:
            stock_basic = pd.concat(all_stocks, ignore_index=True)
            stock_basic = stock_basic.drop_duplicates(subset=['ts_code'])
            self.storage.save_stock_basic(stock_basic)
            logger.info(f"股票基本信息下载完成：共 {len(stock_basic)} 只（仅当前上市，无退市股）")
            return stock_basic

        return pd.DataFrame()

    def download_daily(self, symbols: List[str], start_date: str, end_date: str,
                       force: bool = False) -> Tuple[int, int]:
        """
        下载日线行情（不复权，含成交额）。

        AKShare stock_zh_a_hist 接口字段：
            日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率
        """
        success = 0
        failed = 0

        logger.info(f"开始通过AKShare下载日线行情：{len(symbols)} 只股票")

        for symbol in tqdm(symbols, desc="AKShare下载日线"):
            try:
                if not force and self.storage.has_daily(symbol):
                    success += 1
                    continue

                # AKShare 使用纯数字代码，不带后缀
                code = symbol.split('.')[0]

                df = self._call_with_retry(
                    ak.stock_zh_a_hist,
                    symbol=code,
                    period="daily",
                    start_date=start_date.replace('-', ''),
                    end_date=end_date.replace('-', ''),
                    adjust=""  # 不复权
                )

                if df.empty:
                    success += 1
                    continue

                # 标准化列名
                df = df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '最高': 'high',
                    '最低': 'low',
                    '收盘': 'close',
                    '成交量': 'vol',
                    '成交额': 'amount',
                    '涨跌幅': 'pct_chg',
                    '涨跌额': 'change',
                    '换手率': 'turnover',
                    '振幅': 'amplitude'
                })

                df['ts_code'] = symbol
                df['date'] = pd.to_datetime(df['date'])
                df['pre_close'] = df['close'] - df['change']
                df = df.sort_values('date').reset_index(drop=True)

                self.storage.save_daily(symbol, df)
                success += 1

            except Exception as e:
                failed += 1
                logger.warning(f"  {symbol} 下载失败: {e}")

        logger.info(f"AKShare日线下载完成：成功 {success}，失败 {failed}")
        return success, failed

    def download_adj_factor(self, symbols: List[str], start_date: str, end_date: str,
                             force: bool = False) -> Tuple[int, int]:
        """
        下载复权因子。

        AKShare 没有独立复权因子接口，通过对比不复权和后复权价格推算：
            adj_factor = hfq_close / raw_close

        注意：这种推算方式可能存在精度问题，仅作为备用。
        """
        success = 0
        failed = 0

        logger.info(f"开始通过AKShare推算复权因子：{len(symbols)} 只股票")

        for symbol in tqdm(symbols, desc="AKShare推算复权因子"):
            try:
                code = symbol.split('.')[0]

                # 获取后复权价格
                df_hfq = self._call_with_retry(
                    ak.stock_zh_a_hist,
                    symbol=code,
                    period="daily",
                    start_date=start_date.replace('-', ''),
                    end_date=end_date.replace('-', ''),
                    adjust="hfq"
                )

                # 获取不复权价格
                df_raw = self.storage.load_daily(symbol, start_date, end_date)

                if df_hfq.empty or df_raw.empty:
                    success += 1
                    continue

                df_hfq = df_hfq.rename(columns={'日期': 'date', '收盘': 'close_hfq'})
                df_hfq['date'] = pd.to_datetime(df_hfq['date'])

                merged = pd.merge(df_raw[['date', 'close']], df_hfq[['date', 'close_hfq']],
                                  on='date', how='inner')

                if merged.empty:
                    success += 1
                    continue

                merged['adj_factor'] = merged['close_hfq'] / merged['close']
                merged['ts_code'] = symbol
                merged = merged[['ts_code', 'date', 'adj_factor']]
                merged = merged.sort_values('date').reset_index(drop=True)

                self.storage.save_adj_factor(symbol, merged)
                success += 1

            except Exception as e:
                failed += 1
                logger.warning(f"  {symbol} 复权因子推算失败: {e}")

        logger.info(f"AKShare复权因子推算完成：成功 {success}，失败 {failed}")
        return success, failed
