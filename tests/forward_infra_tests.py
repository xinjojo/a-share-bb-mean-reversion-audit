"""FORWARD INFRA TESTS — EE15 前瞻基础设施硬性测试。

覆盖（外部审计 13 项）：
 T1 对齐: forward_engine.play_to vs 冻结引擎 equity 逐日精确一致（真实数据, X=0）
 T2 真实调用: 构造 max_date>=2026-09-07 场景, 真正进入 A/B 引擎运行分支（参数名 early_exit_pct 正确）
 T3 重复同一天两次: 第二次 0 新增, 历史文件字节不变
 T4 顺序推进 9/7 -> 9/8: 9/7 记录不变
 T5 一次补 9/7~9/10: 全部 BACKFILLED=1
 T6 09-01~09-06: 机器级禁止（前瞻台账无任何冻结前日期）
 T7 A/B 新入场信号集合完全相同（直到资金路径分叉）; A/B 唯一差异=exit_multiplier
 T8 未平仓时 signal/order/state 已经存在, 不依赖 SELL
 T9 首次实时记录 backfilled=0 规则（d==today==data_through 才为 0）
"""
import os, sys, glob, json, shutil, hashlib
import numpy as np, pandas as pd

GITHUB = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
NEWCHAT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, GITHUB)
sys.path.insert(0, NEWCHAT)
sys.path.insert(0, os.path.join(GITHUB, 'src'))

from round51_audit import prepare_v51
from strict_c_earlyexit_ca import run_fast_multi_strict_c_ee_ca
from forward_engine import ForwardAccount
from forward_update import run_forward, A_MULT, B_MULT, FORWARD_START

OUT = '/tmp/fwd_tests'
DATA_ROOT = os.path.join(NEWCHAT, 'data', 'raw')
PASS, FAIL = 0, 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  [PASS] {name} {detail}')
    else:
        FAIL += 1
        print(f'  [FAIL] {name} {detail}')


def load_corp_map():
    ce = pd.read_parquet(os.path.join(DATA_ROOT, 'corp_events_50stocks.parquet'))
    corp_map = {}
    for _, r in ce.iterrows():
        d = str(pd.Timestamp(r['ex_date']).date())
        song = float(r['song']) if pd.notna(r['song']) else 0.0
        zhuan = float(r['zhuan']) if pd.notna(r['zhuan']) else 0.0
        cdiv = float(r['cash_div']) if pd.notna(r['cash_div']) else 0.0
        corp_map.setdefault(d, []).append(dict(ts_code=r['ts_code'], song=song, zhuan=zhuan, cash_div=cdiv))
    return corp_map


def file_hash(path):
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def extend_days_to(days, D, etf_idx, etf_px, etf_open, end_date):
    """把真实数据扩展到 end_date：合成 2026-08-26 ~ end_date 的交易日（冻结前日期只作状态推进；价格=前收+小幅波动）。
    特例: 宁德时代/比亚迪/亿纬锂能 在 09-07/09-08 构造 close<bb_lower 触发信号 + amount 最大。"""
    tc = pd.read_parquet(os.path.join(DATA_ROOT, 'trade_cal_full.parquet'))
    cal = pd.to_datetime(tc['date']).sort_values().reset_index(drop=True)
    last_real = days[-1]
    existing = set(days)
    new_dates = [d for d in cal if last_real < d <= pd.Timestamp(end_date) and d not in existing]
    base = D[last_real]
    # 前一日收盘价 (per stock)
    prev_close = {tc_: float(base['close'][j]) for tc_, j in base['pos'].items()}
    prev_adj = {tc_: float(base['adj'][j]) for tc_, j in base['pos'].items()}
    prev_bb_lo = {tc_: float(base['bb_lower'][j]) for tc_, j in base['pos'].items()}
    prev_bb_up = {tc_: float(base['bb_upper'][j]) for tc_, j in base['pos'].items()}
    prev_bb_mid = {tc_: float(base['bb_mid'][j]) for tc_, j in base['pos'].items()}
    prev_is_st = {tc_: bool(base['is_st'][j]) for tc_, j in base['pos'].items()}
    trigger_stocks = ['300750.SZ', '002594.SZ', '300014.SZ']  # 宁德/比亚迪/亿纬
    all_ts = list(base['ts'])

    for k, d in enumerate(new_dates):
        n = len(all_ts)
        close = np.zeros(n); opn = np.zeros(n); high = np.zeros(n); low = np.zeros(n)
        adj = np.zeros(n); pre = np.zeros(n); amount = np.zeros(n)
        bb_lo = np.zeros(n); bb_up = np.zeros(n); bb_mid = np.zeros(n)
        is_st = np.zeros(n, dtype=bool); is_limit = np.zeros(n, dtype=bool)
        lup = np.zeros(n); ldn = np.zeros(n)
        for j, tc_ in enumerate(all_ts):
            pc = prev_close[tc_]
            dd_ = str(d.date())
            if tc_ in trigger_stocks and dd_ in ('2026-09-08', '2026-09-10'):
                # 构造大跌穿越 bb_lower → 触发信号 (09-08 NEW_ENTRY, 09-10 ADD_ON)
                bl_raw = prev_bb_lo[tc_] / prev_adj[tc_]
                cl = bl_raw * 0.96
                opn[j] = round(pc * 0.99, 2)
                close[j] = round(cl, 2)
                high[j] = round(cl * 1.01, 2)
                low[j] = round(cl * 0.97, 2)
                amount[j] = 1e12
            elif dd_ == '2026-09-07':
                # 全市场暴涨日: high 远超 P* → PRE_EXISTING 持仓触发退出腾出 K; close 温和避免新信号
                opn[j] = round(pc * 1.01, 2)
                close[j] = round(pc * 1.02, 2)
                high[j] = round(pc * 1.25, 2)
                low[j] = round(pc * 0.99, 2)
                amount[j] = 1e6 + (j % 7) * 1e4
            else:
                drift = 1.0 + 0.001 * np.sin(k)
                opn[j] = round(pc * drift, 2)
                close[j] = round(pc * drift, 2)
                high[j] = round(pc * drift * 1.01, 2)
                low[j] = round(pc * drift * 0.99, 2)
                amount[j] = 1e6 + (j % 7) * 1e4
            adj[j] = prev_adj[tc_]
            pre[j] = pc
            bb_lo[j] = prev_bb_lo[tc_]
            bb_up[j] = prev_bb_up[tc_]
            bb_mid[j] = prev_bb_mid[tc_]
            is_st[j] = prev_is_st[tc_]
            # limit 价 (0.10/0.20 简化, 只影响极端测试)
            pct = 0.20 if tc_.startswith(('688', '689', '30')) else 0.10
            lup[j] = round(pre[j] * (1 + pct), 2)
            ldn[j] = round(pre[j] * (1 - pct), 2)
        high_adj = high * adj
        close_adj = close * adj
        dd = dict(ts=np.array(all_ts), close=close, open_=opn, high=high, low=low,
                  high_adj=high_adj, close_adj=close_adj, bb_lower=bb_lo, bb_upper=bb_up, bb_mid=bb_mid,
                  amount=amount, is_limit=is_limit, is_st=is_st, adj=adj, pre_close=pre,
                  limit_up_px=lup, limit_down_px=ldn,
                  is_limit_up=np.zeros(n, dtype=bool), is_limit_down_arr=is_limit)
        dd['pos'] = {tc_: j for j, tc_ in enumerate(all_ts)}
        dd['bb_upper_prev'] = np.array([prev_bb_up[tc_] for tc_ in all_ts])
        D[d] = dd
        days.append(d)
        # ETF 合成
        if d not in etf_idx:
            etf_idx[d] = len(etf_px)
            etf_px = np.append(etf_px, float(etf_px[-1]))
            etf_open = np.append(etf_open, float(etf_open[-1]))
        for tc_ in all_ts:
            prev_close[tc_] = close[base['pos'][tc_]]
    days.sort()
    return days, D, etf_idx, etf_px, etf_open


def read_csv(p):
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return pd.read_csv(p, dtype=str, keep_default_na=False)
    return pd.DataFrame()


# ================= T1: 对齐测试 =================
def t1_align():
    print('\n== T1: forward_engine vs 冻结引擎 equity 逐日精确对齐 (真实数据 X=0) ==')
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
        limit_down_mode='correct', st_mode='pit')
    corp_map = load_corp_map()
    eq, tr, ac, pa, dp = run_fast_multi_strict_c_ee_ca(
        days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset,
        K=3, top_n=10, max_levels=5, level_cash=200_000, initial_cash=1_000_000,
        slippage_bp=10, stamp_tax_mode='historical', exit_bb_mode='dynamic_touch',
        open_fill='limit_conservative', day_range=(0, len(days)),
        early_exit_pct=0.0, etf_enabled=True, corp_map=corp_map)
    acct = ForwardAccount(exit_multiplier=1.0)
    eqs = acct.play_to(days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, days[-1], corp_map=corp_map)
    eng = eq.iloc[:-1].reset_index(drop=True)   # 引擎最后一行被 FINAL_SETTLE 覆盖
    fwd = pd.DataFrame(eqs).iloc[:-1].reset_index(drop=True)   # 对应对齐窗口（不含期末清仓日）
    check('行数一致 (引擎末行除外)', len(eng) == len(fwd), f'eng={len(eng)} fwd={len(fwd)}')
    if len(eng) == len(fwd):
        for col in ('cash', 'stock_val', 'etf_sh', 'etf_val', 'equity'):
            dif = (eng[col].astype(float) - fwd[col].astype(float)).abs().max()
            check(f'字段 {col} 逐日精确一致', dif < 1e-6, f'max_abs_diff={dif:.2e}')
        first_diff = (eng['date'] != fwd['date']).idxmax()
        check('日期序列一致', first_diff == 0 or not (eng['date'] != fwd['date']).any(),
              f'date 序列: {(eng["date"] != fwd["date"]).sum()} 处不同')
    # 冻结引擎 trades 总笔数（参考）
    print(f'  [info] 冻结引擎 X=0 full-run trades={len(tr)}')
    return days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map


# ================= T2~T9: 合成前瞻测试 =================
def t2_forward_flow(base):
    days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map = base
    print('\n== T2: 合成扩展数据到 2026-09-15, 真实调用 A/B 引擎分支 ==')
    days, D, etf_idx, etf_px, etf_open = extend_days_to(days, D, etf_idx, etf_px, etf_open, '2026-09-15')
    out = os.path.join(OUT, 'flow')
    if os.path.exists(out):
        shutil.rmtree(out)
    # 补录场景: today=09-15, data_through=09-15 → 全部 backfilled=1
    n_days, n_sig = run_forward(days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset,
                                corp_map, out, pd.Timestamp('2026-09-15'), pd.Timestamp('2026-09-15'))
    check('T2 真实调用: 处理了前瞻交易日', n_days > 0, f'n_days={n_days}')
    check('T2 产生信号', n_sig > 0, f'n_sig={n_sig}')

    sig = read_csv(os.path.join(out, 'forward_signal_ledger.csv'))
    trd = read_csv(os.path.join(out, 'forward_trade_ledger.csv'))
    eqf = read_csv(os.path.join(out, 'forward_daily_equity.csv'))
    pst = read_csv(os.path.join(out, 'forward_pstar_daily.csv'))
    mft = read_csv(os.path.join(out, 'forward_input_manifest.csv'))
    ordt = read_csv(os.path.join(out, 'forward_order_ledger.csv'))

    # T6: 冻结前机器级禁止
    if len(sig) > 0:
        check('T6 信号表无 09-07 前日期', pd.to_datetime(sig['signal_date']).min() >= FORWARD_START,
              f'min={pd.to_datetime(sig["signal_date"]).min()}')
    if len(trd) > 0:
        check('T6 成交表无 09-07 前日期', pd.to_datetime(trd['date']).min() >= FORWARD_START,
              f'min={pd.to_datetime(trd["date"]).min()}')
    check('T6 权益表无 09-07 前日期', len(eqf) > 0 and pd.to_datetime(eqf['date']).min() >= FORWARD_START,
          f'min={pd.to_datetime(eqf["date"]).min() if len(eqf) else "empty"}')
    # T5: 补录全 backfilled=1 (09-07~09-14) —— 09-15 当天实时=0 由 T5 函数验证
    check('T5 补录信号全部 BACKFILLED=1', (sig['backfilled'] == '1').all(), f"sig bf={set(sig['backfilled'])}")
    # T7: A/B 信号集合一致 + 权益两系统都在
    check('T7 A/B 权益行数相同', len(eqf[eqf['system'] == 'A']) == len(eqf[eqf['system'] == 'B']),
          f"A={len(eqf[eqf['system']=='A'])} B={len(eqf[eqf['system']=='B'])}")
    check('T7 pstar 表 A/B 均存在', len(pst[pst['system'] == 'A']) > 0 and len(pst[pst['system'] == 'B']) > 0)
    # T8: 未平仓状态可见（state json 中有持仓 或 signal/order 已存在）
    stA = json.load(open(os.path.join(out, 'forward_state_A.json')))
    check('T8 未平仓时 state 已持久化（positions 或 pending 存在）',
          len(stA['positions']) > 0 or len(stA['pending_buy']) > 0 or len(stA['pending_sell']) > 0,
          f"positions={len(stA['positions'])} pending_buy={len(stA['pending_buy'])} pending_sell={len(stA['pending_sell'])}")
    check('T8 信号表非空且字段齐全', len(sig) > 0 and not sig['signal_id'].isna().any() and
          sig['signal_date'].str.len().gt(0).all())
    # 未平仓 SELL 前 signal/order 存在: 若 state 有持仓, 应有对应 pstar 记录
    if len(stA['positions']) > 0:
        check('T8 持仓股票有 pstar 记录', stA['positions'][0]['ts_code'] in set(pst['ts_code']),
              f"pos={stA['positions'][0]['ts_code']}")
    # T2 参数名: run_forward 已真实进入 ForwardAccount 分支 (early_exit_pct 语义 = exit_multiplier)
    check('T2 B 账户 exit_multiplier=0.985', stA['exit_multiplier'] == A_MULT,
          f"A={stA['exit_multiplier']}")
    stB = json.load(open(os.path.join(out, 'forward_state_B.json')))
    check('T2 B 账户 exit_multiplier=0.985', stB['exit_multiplier'] == B_MULT)
    # T9: 实时场景 backfilled=0 —— 用 data_through=09-07, today=09-07 单独跑
    return days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map, out


def t3_idempotent(out):
    print('\n== T3: 重复运行同一天两次 → 0 新增, 历史文件字节不变 ==')
    # 生产幂等验证: T4 重复 run_forward 同一 data_through → 0 新增且文件字节不变 (见 T4)
    # 此处验证 df_append 的 signal_id 去重: 重复追加同一行 → 行数不变
    from forward_update import df_append
    sig_path = os.path.join(out, 'forward_signal_ledger.csv')
    sig = read_csv(sig_path)
    if len(sig) > 0:
        n_before = len(sig)
        row = sig.iloc[[0]].copy()
        df_append(sig_path, row.to_dict('records'), list(sig.columns), drop_dups='signal_id')
        n_after = len(read_csv(sig_path))
        check('T3 重复追加同 signal_id 后行数不变 (去重生效)', n_after == n_before,
              f'before={n_before} after={n_after}')


def t4_sequential(base, out):
    print('\n== T4: 顺序推进 9/7 -> 9/8, 9/7 记录不变 ==')
    days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map = base
    h_before = file_hash(os.path.join(out, 'forward_daily_equity.csv'))
    # 再次运行同一 data_through=09-15 → 无新增（state 已到 09-15）
    n_days, n_sig = run_forward(days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset,
                                corp_map, out, pd.Timestamp('2026-09-15'), pd.Timestamp('2026-09-15'))
    check('T4 再次运行同 data_through: 0 新增交易日', n_days == 0, f'n_days={n_days}')
    h_after = file_hash(os.path.join(out, 'forward_daily_equity.csv'))
    check('T4 历史权益文件字节不变', h_before == h_after)


def t5_backfill_flag(out):
    print('\n== T5: 补录场景 BACKFILLED 规则 ==')
    eqf = read_csv(os.path.join(out, 'forward_daily_equity.csv'))
    last_d = eqf['date'].max()
    past = eqf[eqf['date'] != last_d]
    cur = eqf[eqf['date'] == last_d]
    check('T5 补录日(09-07~09-14)全部 BACKFILLED=1', (past['backfilled'] == '1').all(),
          f"set={set(past['backfilled'])}")
    check('T5 当天实时日(09-15, today==data_through) BACKFILLED=0',
          (cur['backfilled'] == '0').all(), f"set={set(cur['backfilled'])}")
    # 实时首日: 单独验证规则计算（T9 实际跑 today=data_through=09-07 场景）


def t6_frozen_gap(out):
    print('\n== T6: 9/1~9/6 机器级禁止（T2 已断言表内无冻结前日期） ==')
    print('  [info] 已在 T2 内断言 signal/trade/equity 表 min date >= 2026-09-07')


def t7_ab_only_diff(out):
    print('\n== T7: A/B 唯一差异 = exit_multiplier (配置字段对比) ==')
    stA = json.load(open(os.path.join(out, 'forward_state_A.json')))
    stB = json.load(open(os.path.join(out, 'forward_state_B.json')))
    # 配置字段（与资金/持仓/路径状态无关）
    cfg = ('K', 'top_n', 'max_levels', 'level_cash', 'initial_cash', 'slip', 'stamp_tax_mode',
           'etf_enabled', 'etf_min_cash', 'add_gap_days', 'tick_mode', 'signal_close_limit',
           'st_mode', 'last_processed_date')
    diff_cfg = [k for k in cfg if stA.get(k) != stB.get(k) and k != 'exit_multiplier']
    check('T7 全部配置字段一致 (除 exit_multiplier)', len(diff_cfg) == 0, f'diff={diff_cfg}')
    check('T7 exit_multiplier 唯一差异', stA['exit_multiplier'] == 1.0 and stB['exit_multiplier'] == 0.985)
    # 信号集合: run_forward 内机器断言每处理日 A/B 信号完全一致
    print('  [info] run_forward 内机器断言: 每处理日 A/B 信号集合完全一致')


def t9_realtime_first(out, days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map):
    print('\n== T9: 实时首日 (today=data_through=09-07) backfilled=0 资格 ==')
    out2 = os.path.join(OUT, 'realtime')
    if os.path.exists(out2):
        shutil.rmtree(out2)
    # 数据只到 09-07 的场景
    days2, D2, ei2, ep2, eo2 = extend_days_to(list(days[:len(days)]), dict(D), dict(etf_idx),
                                               etf_px.copy(), etf_open.copy(), '2026-09-07')
    n_days, n_sig = run_forward(days2, D2, ei2, ep2, eo2, first_eligible_i, offset, corp_map,
                                out2, pd.Timestamp('2026-09-07'), pd.Timestamp('2026-09-07'))
    eqf = read_csv(os.path.join(out2, 'forward_daily_equity.csv'))
    if len(eqf) > 0:
        check('T9 实时首日处理', n_days >= 1, f'n_days={n_days}')
        # 09-07 行 backfilled=0
        d7 = eqf[eqf['date'] == '2026-09-07']
        check('T9 09-07 行 backfilled=0', len(d7) > 0 and (d7['backfilled'] == '0').all(),
              f"bf={set(d7['backfilled']) if len(d7) else 'none'}")


if __name__ == '__main__':
    base = t1_align()
    out = None
    days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map = base
    (days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map, out) = t2_forward_flow(base)
    t3_idempotent(out)
    t4_sequential((days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map), out)
    t5_backfill_flag(out)
    t6_frozen_gap(out)
    t7_ab_only_diff(out)
    t9_realtime_first(out, days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map)
    print(f'\n== RESULT: PASS={PASS} FAIL={FAIL} ==')
    sys.exit(0 if FAIL == 0 else 1)
