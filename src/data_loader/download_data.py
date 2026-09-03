#!/usr/bin/env python3
"""
数据下载入口脚本

用法：
    python -m data_loader.download_data --source tushare --start 20200101 --end 20241231
    python -m data_loader.download_data --source akshare --start 20200101 --end 20241231

环境变量：
    TUSHARE_TOKEN: Tushare Pro token（使用tushare数据源时必需）
"""
import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.loader import load_config
from data_loader.storage import DataStorage
from data_loader.tushare_loader import TushareLoader
from data_loader.akshare_loader import AKShareLoader


def setup_logging():
    """配置日志。"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    parser = argparse.ArgumentParser(description='A股历史数据下载')
    parser.add_argument('--source', type=str, default='tushare',
                        choices=['tushare', 'akshare'],
                        help='数据源（默认 tushare）')
    parser.add_argument('--start', type=str, default='20200101',
                        help='开始日期 YYYYMMDD（默认 20200101）')
    parser.add_argument('--end', type=str, default='20241231',
                        help='结束日期 YYYYMMDD（默认 20241231）')
    parser.add_argument('--force', action='store_true',
                        help='强制重新下载（覆盖已有数据）')
    parser.add_argument('--config', type=str, default=None,
                        help='配置文件路径')

    args = parser.parse_args()
    setup_logging()
    logger = logging.getLogger(__name__)

    # 加载配置
    config = load_config(args.config)
    raw_dir = config['project']['raw_dir']

    # 初始化存储
    storage = DataStorage(raw_dir=raw_dir)

    logger.info("=" * 60)
    logger.info(f"数据源: {args.source}")
    logger.info(f"日期范围: {args.start} ~ {args.end}")
    logger.info(f"数据目录: {raw_dir}")
    logger.info(f"强制重下: {args.force}")
    logger.info("=" * 60)

    if args.source == 'tushare':
        token = config['data_source']['tushare']['token']
        if not token:
            logger.error(
                "Tushare token 为空！请设置环境变量 TUSHARE_TOKEN，"
                "或在 config/config.yaml 中配置 token。\n"
                "注册地址：https://tushare.pro/register"
            )
            sys.exit(1)

        loader = TushareLoader(token=token, storage=storage)
        results = loader.download_all(
            start_date=args.start,
            end_date=args.end,
            skip_existing=not args.force
        )

    elif args.source == 'akshare':
        loader = AKShareLoader(storage=storage)

        # AKShare 分步下载
        logger.info("步骤1: 下载股票基本信息...")
        stock_basic = loader.download_stock_basic()

        if stock_basic.empty:
            logger.error("股票基本信息为空，无法继续")
            sys.exit(1)

        symbols = stock_basic[
            ~stock_basic['ts_code'].str.startswith(('8', '4', '9'))
        ]['ts_code'].tolist()

        logger.info(f"步骤2: 下载 {len(symbols)} 只股票的日线行情...")
        daily_success, daily_failed = loader.download_daily(
            symbols, args.start, args.end, force=args.force
        )

        logger.info("步骤3: 推算复权因子...")
        adj_success, adj_failed = loader.download_adj_factor(
            symbols, args.start, args.end, force=args.force
        )

        results = {
            'stock_basic': len(stock_basic),
            'daily_success': daily_success,
            'daily_failed': daily_failed,
            'adj_factor_success': adj_success,
            'adj_factor_failed': adj_failed,
        }

    # 输出统计
    logger.info("\n" + "=" * 60)
    logger.info("下载完成统计：")
    for k, v in results.items():
        logger.info(f"  {k}: {v}")

    stats = storage.get_stats()
    logger.info(f"\n本地数据统计：")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
