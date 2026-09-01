"""
数据存储层
负责将下载的数据保存为 Parquet 格式，并提供 DuckDB 查询接口。

数据组织方式：
- data/raw/daily/{symbol}.parquet      — 每只股票的日线行情
- data/raw/adj_factor/{symbol}.parquet — 每只股票的复权因子
- data/raw/stock_basic.parquet          — 股票基本信息列表
- data/raw/trade_cal.parquet            — 交易日历
- data/raw/daily_all.parquet            — 全市场日线（按日期分区，可选）
"""
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from typing import Optional, List, Dict
import duckdb


class DataStorage:
    """数据存储管理器，负责 Parquet 读写和 DuckDB 查询。"""

    def __init__(self, raw_dir: str, processed_dir: str = None):
        """
        Args:
            raw_dir: 原始数据存储目录
            processed_dir: 处理后数据存储目录（可选）
        """
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir) if processed_dir else self.raw_dir / 'processed'

        # 创建子目录
        self._daily_dir = self.raw_dir / 'daily'
        self._adj_factor_dir = self.raw_dir / 'adj_factor'
        self._daily_dir.mkdir(parents=True, exist_ok=True)
        self._adj_factor_dir.mkdir(parents=True, exist_ok=True)

        # DuckDB 连接（懒加载）
        self._con = None

    @property
    def con(self) -> duckdb.DuckDBPyConnection:
        """获取 DuckDB 连接（懒加载）。"""
        if self._con is None:
            self._con = duckdb.connect()
        return self._con

    # -------------------------------------------------------------------------
    # 日线行情
    # -------------------------------------------------------------------------
    def save_daily(self, symbol: str, df: pd.DataFrame) -> None:
        """
        保存单只股票的日线行情。

        Args:
            symbol: 股票代码（如 000001.SZ）
            df: 日线数据，必须包含 date 列
        """
        if df.empty:
            return

        filepath = self._daily_dir / f'{symbol}.parquet'
        df = df.copy()
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)

        table = pa.Table.from_pandas(df)
        pq.write_table(table, filepath, compression='snappy')

    def load_daily(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        加载单只股票的日线行情。

        Args:
            symbol: 股票代码
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            日线数据 DataFrame
        """
        filepath = self._daily_dir / f'{symbol}.parquet'
        if not filepath.exists():
            return pd.DataFrame()

        df = pq.read_table(filepath).to_pandas()
        df['date'] = pd.to_datetime(df['date'])

        if start_date:
            df = df[df['date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['date'] <= pd.to_datetime(end_date)]

        return df.sort_values('date').reset_index(drop=True)

    def has_daily(self, symbol: str) -> bool:
        """检查某只股票的日线数据是否存在。"""
        return (self._daily_dir / f'{symbol}.parquet').exists()

    def list_daily_symbols(self) -> List[str]:
        """列出所有已下载日线数据的股票代码。"""
        return [f.stem for f in self._daily_dir.glob('*.parquet')]

    # -------------------------------------------------------------------------
    # 复权因子
    # -------------------------------------------------------------------------
    def save_adj_factor(self, symbol: str, df: pd.DataFrame) -> None:
        """保存单只股票的复权因子。"""
        if df.empty:
            return

        filepath = self._adj_factor_dir / f'{symbol}.parquet'
        df = df.copy()
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)

        table = pa.Table.from_pandas(df)
        pq.write_table(table, filepath, compression='snappy')

    def load_adj_factor(self, symbol: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """加载单只股票的复权因子。"""
        filepath = self._adj_factor_dir / f'{symbol}.parquet'
        if not filepath.exists():
            return pd.DataFrame()

        df = pq.read_table(filepath).to_pandas()
        df['date'] = pd.to_datetime(df['date'])

        if start_date:
            df = df[df['date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['date'] <= pd.to_datetime(end_date)]

        return df.sort_values('date').reset_index(drop=True)

    # -------------------------------------------------------------------------
    # 股票基本信息
    # -------------------------------------------------------------------------
    def save_stock_basic(self, df: pd.DataFrame) -> None:
        """保存股票基本信息列表。"""
        filepath = self.raw_dir / 'stock_basic.parquet'
        table = pa.Table.from_pandas(df)
        pq.write_table(table, filepath, compression='snappy')

    def load_stock_basic(self) -> pd.DataFrame:
        """加载股票基本信息列表。"""
        filepath = self.raw_dir / 'stock_basic.parquet'
        if not filepath.exists():
            return pd.DataFrame()
        return pq.read_table(filepath).to_pandas()

    # -------------------------------------------------------------------------
    # 交易日历
    # -------------------------------------------------------------------------
    def save_trade_cal(self, df: pd.DataFrame) -> None:
        """保存交易日历。"""
        filepath = self.raw_dir / 'trade_cal.parquet'
        table = pa.Table.from_pandas(df)
        pq.write_table(table, filepath, compression='snappy')

    def load_trade_cal(self) -> pd.DataFrame:
        """加载交易日历。"""
        filepath = self.raw_dir / 'trade_cal.parquet'
        if not filepath.exists():
            return pd.DataFrame()
        return pq.read_table(filepath).to_pandas()

    # -------------------------------------------------------------------------
    # 全市场查询（通过 DuckDB）
    # -------------------------------------------------------------------------
    def query_daily_by_date(self, date: str, columns: List[str] = None) -> pd.DataFrame:
        """
        查询某一交易日的全市场日线数据。

        Args:
            date: 日期（YYYY-MM-DD）
            columns: 需要的列名列表，None 表示全部列

        Returns:
            该日期全市场股票的日线数据
        """
        # 使用 DuckDB 查询所有 parquet 文件
        glob_pattern = str(self._daily_dir / '*.parquet')
        cols = ', '.join(columns) if columns else '*'

        query = f"""
            SELECT {cols}
            FROM read_parquet('{glob_pattern}', hive_partitioning=false)
            WHERE date = TIMESTAMP '{date}'
            ORDER BY amount DESC
        """
        try:
            return self.con.execute(query).fetchdf()
        except Exception:
            # 如果 DuckDB 查询失败，退回到逐文件读取
            return self._query_daily_by_date_fallback(date, columns)

    def _query_daily_by_date_fallback(self, date: str, columns: List[str] = None) -> pd.DataFrame:
        """DuckDB 查询失败时的回退方案：逐文件读取。"""
        date_ts = pd.to_datetime(date)
        all_data = []

        for filepath in self._daily_dir.glob('*.parquet'):
            try:
                df = pq.read_table(filepath).to_pandas()
                df['date'] = pd.to_datetime(df['date'])
                df = df[df['date'] == date_ts]
                if not df.empty:
                    if columns:
                        df = df[columns]
                    all_data.append(df)
            except Exception:
                continue

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        if 'amount' in result.columns:
            result = result.sort_values('amount', ascending=False).reset_index(drop=True)
        return result

    def get_top_n_by_amount(self, date: str, n: int = 1,
                             exclude_st: bool = True,
                             exclude_suspended: bool = True) -> pd.DataFrame:
        """
        获取某交易日成交额排名前 N 的股票。

        Args:
            date: 日期
            n: 排名数量
            exclude_st: 是否排除 ST/*ST
            exclude_suspended: 是否排除停牌股

        Returns:
            前 N 名股票的日线数据
        """
        df = self.query_daily_by_date(date)
        if df.empty:
            return df

        # 排除停牌股（成交额为0或NaN）
        if exclude_suspended and 'amount' in df.columns:
            df = df[df['amount'].notna() & (df['amount'] > 0)]

        # 排除 ST/*ST（需要股票基本信息）
        if exclude_st:
            stock_basic = self.load_stock_basic()
            if not stock_basic.empty and 'name' in stock_basic.columns:
                st_symbols = stock_basic[
                    stock_basic['name'].str.contains('ST', na=False)
                ]['ts_code'].tolist()
                df = df[~df['ts_code'].isin(st_symbols)]

        return df.head(n).reset_index(drop=True)

    # -------------------------------------------------------------------------
    # 统计信息
    # -------------------------------------------------------------------------
    def get_stats(self) -> Dict:
        """获取数据存储统计信息。"""
        daily_files = list(self._daily_dir.glob('*.parquet'))
        adj_files = list(self._adj_factor_dir.glob('*.parquet'))

        return {
            'daily_symbols': len(daily_files),
            'adj_factor_symbols': len(adj_files),
            'stock_basic_exists': (self.raw_dir / 'stock_basic.parquet').exists(),
            'trade_cal_exists': (self.raw_dir / 'trade_cal.parquet').exists(),
            'daily_dir': str(self._daily_dir),
        }
