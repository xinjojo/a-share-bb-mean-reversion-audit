"""RUN FORWARD DAILY — EE15 前瞻一键每日流程（用户每天只需运行本脚本）。

流程：
1. Tushare 拉最新增量（update_forward_tushare；无 token 则跳过并明确警告，使用本地数据兜底）
2. prepare_forward_data（冻结段 prepare_v51 原样 + 增量段同字段语义合并）
3. 加载 A/B state → 逐日推进新增日期 → 写 signal/order/trade/P*/equity/hash
4. 更新 FORWARD_STATUS.md 运行记录
5. 输出当天人话摘要（最新数据日期 / raw candidate / A/B 明细 / 分叉 / BACKFILLED / 修订告警）

若当天无新交易日：安全退出，不产生重复行。

禁止：修改策略 / 修改 1.5% / 新增阈值 / 重新选参。
"""
import os, sys, json, glob, hashlib
import numpy as np, pandas as pd

GITHUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWCHAT = os.path.dirname(os.path.dirname(GITHUB))
sys.path.insert(0, GITHUB)
sys.path.insert(0, os.path.join(GITHUB, 'src'))
sys.path.insert(0, NEWCHAT)

from round51_audit import prepare_v51
from forward_update import (run_forward, load_corp_map, OUT, FORWARD_START, A_MULT, B_MULT,
                            DATA_ROOT)
from prepare_forward_data import prepare_forward_data, parity_check
from forward_ext_data import FROZEN_END

INC = os.path.join(NEWCHAT, 'data', 'forward_incremental')
ALERT_PATH = os.path.join(INC, 'forward_data_revision_alert.csv')


def corp_map_with_tushare_increment():
    """冻结 corp_map（50 只重点） + Tushare dividend 增量（每股 → 每10股口径）。"""
    corp_map = load_corp_map()
    files = sorted(glob.glob(os.path.join(INC, 'dividend_*.parquet')))
    added = 0
    for f in files:
        try:
            dv = pd.read_parquet(f)
        except Exception:
            continue
        if dv.empty or 'ex_date' not in dv.columns:
            continue
        for _, r in dv.iterrows():
            try:
                ex = str(pd.Timestamp(r['ex_date']).date())
            except Exception:
                continue
            song = float(r.get('stk_div') or 0.0) * 10.0          # 每股送股 → 每10股
            zhuan = float(r.get('stk_bo_rate') or 0.0) * 10.0     # 每股转增 → 每10股
            cdiv = float(r.get('cash_div') or 0.0) * 10.0         # 每股现金 → 每10股
            if song == 0 and zhuan == 0 and cdiv == 0:
                continue
            tc = str(r['ts_code'])
            # 不覆盖冻结 50 只已有事件（以冻结为准），只新增 Tushare 增量事件
            if ex not in corp_map or all(e['ts_code'] != tc for e in corp_map[ex]):
                corp_map.setdefault(ex, []).append(dict(ts_code=tc, song=song, zhuan=zhuan, cash_div=cdiv))
                added += 1
    return corp_map, added


def load_name_map():
    nm = {}
    for p in (os.path.join(DATA_ROOT, 'stock_basic.parquet'),
              os.path.join(INC, 'stock_basic_forward.parquet')):
        if os.path.exists(p):
            try:
                sb = pd.read_parquet(p)
                nm.update(dict(zip(sb['ts_code'].astype(str), sb['name'].astype(str))))
                break
            except Exception:
                continue
    return nm


def human_summary(days, data_through, today, n_days, n_sig):
    print()
    print('================ 今日人话摘要 ================')
    print(f'最新数据日期: {data_through.date()}')
    print(f'今天日期: {today.date()}')
    print(f'本次推进交易日: {n_days} 个, 新信号: {n_sig} 条')
    for tag in ('A', 'B'):
        sp = os.path.join(OUT, f'forward_state_{tag}.json')
        if not os.path.exists(sp):
            print(f'[{tag}] state 不存在')
            continue
        st = json.load(open(sp))
        print(f'\n[{tag}] 账户状态（截至 {st["last_processed_date"]}）:')
        print(f'  现金: {st["cash"]:,.2f} 元')
        print(f'  ETF: {st["etf_sh"]:,} 份')
        if st['positions']:
            print(f'  当前持仓 {len(st["positions"])} 笔:')
            for p in st['positions']:
                print(f'    {p["ts_code"]} 第{p["levels"]}层 {p["shares"]:,}股 成本{p["total_cost"]:,.2f} 入场{p["entry_date"]}')
        else:
            print('  当前持仓: 无')
        if st.get('pending_buy'):
            print(f'  待执行买入: {len(st["pending_buy"])} 笔')
        else:
            print('  待执行买入: 无')
    # 分叉检查（如果状态推进到同一日，对比持仓集合）
    pa = json.load(open(os.path.join(OUT, 'forward_state_A.json')))
    pb = json.load(open(os.path.join(OUT, 'forward_state_B.json')))
    holdA = {p['ts_code']: p['levels'] for p in pa['positions']}
    holdB = {p['ts_code']: p['levels'] for p in pb['positions']}
    if holdA == holdB:
        print('\n[A/B 分叉] 无（持仓相同）')
    else:
        onlyA = {k for k in holdA if k not in holdB}
        onlyB = {k for k in holdB if k not in holdA}
        print('\n[A/B 分叉] 存在:')
        for k in onlyA: print(f'  A 持有 {k}（B 已退出/未持有）')
        for k in onlyB: print(f'  B 持有 {k}（A 未持有）')
    # BACKFILLED 检查
    eq = pd.read_csv(os.path.join(OUT, 'forward_daily_equity.csv'), dtype=str, keep_default_na=False) \
        if os.path.exists(os.path.join(OUT, 'forward_daily_equity.csv')) else pd.DataFrame()
    if len(eq):
        bf = set(eq['backfilled'])
        print(f'\n[BACKFILLED] 今日权益记录标记: {sorted(bf)}（0=实时, 1=补录）')
    # 修订告警
    if os.path.exists(ALERT_PATH) and os.path.getsize(ALERT_PATH) > 0:
        al = pd.read_csv(ALERT_PATH, dtype=str)
        print(f'\n[数据修订告警] {ALERT_PATH} 现有 {len(al)} 行（旧历史值不同，未自动覆盖）')
    else:
        print('\n[数据修订告警] 无')
    print('===============================================')


def main():
    print('== RUN FORWARD DAILY ==')
    today = pd.Timestamp(pd.Timestamp.now().date())

    # 1) Tushare 增量拉取（无 token 跳过）
    tok = os.environ.get('TUSHARE_TOKEN', '')
    if tok:
        print('  ① Tushare 增量拉取...')
        from update_forward_tushare import get_token, update_all
        import tushare as ts
        pro = ts.pro_api(get_token())
        n_pull, latest = update_all(pro)
        print(f'  Tushare 拉取完成: {n_pull} 个交易日, 最新 {latest}')
    else:
        print('  ① Tushare token 未设置（TUSHARE_TOKEN 环境变量缺失）→ 跳过拉取，使用本地已有数据')
        print('     （若需自动拉取：export TUSHARE_TOKEN=<token> 后重跑）')

    # 2) 数据准备（冻结段原样 + 增量段）
    print('  ② prepare_forward_data...')
    p = parity_check(None)
    print(f'  parity(扩展层 vs prepare_v51): pass={p["pass_"]} max_abs_diff={p["max_abs_diff"]} n={len(p["sample_dates"])}')
    if not p['pass_']:
        print('  [FATAL] parity 未通过，拒绝使用扩展层。')
        sys.exit(1)
    # 读本地 Tushare 增量（INC）不需要 token：token 只用于"拉取"。
    # 无 token 时也必须读到已拉好的本地增量，否则数据末日 < state 进度会触发保护性报错。
    data, src, ext_days = prepare_forward_data(prefer_tushare=True)
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = data
    data_through = max(days)
    print(f'  增量数据源: {src}')
    print(f'  数据末日: {data_through.date()}')

    # 3) 公司行为 + 名称
    corp_map, n_corp = corp_map_with_tushare_increment()
    if n_corp:
        print(f'  Tushare dividend 增量并入: {n_corp} 条新事件')
    name_map = load_name_map()

    # 4) 推进
    print('  ③ 逐日推进 A/B 状态...')
    n_days, n_sig = run_forward(days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset,
                                corp_map, OUT, data_through, today, name_map=name_map)

    # 5) 状态判定 + 人话摘要
    if data_through < FORWARD_START:
        print(f'\n== PRODUCTION NOT STARTED ==')
        print(f'  尚无 {FORWARD_START.date()} 及以后真实行情（当前止于 {data_through.date()}）。')
        print(f'  状态：FROZEN / FORWARD INFRA READY / NOT YET LIVE')
    else:
        print(f'\n== 已读取真实 {FORWARD_START.date()}+ 数据并落盘 ==')
        print(f'  状态：FORWARD OBSERVATION LIVE')
    human_summary(days, data_through, today, n_days, n_sig)


if __name__ == '__main__':
    main()
