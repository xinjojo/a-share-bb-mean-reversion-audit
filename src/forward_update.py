"""FORWARD UPDATE — EE15 前瞻观察期每日记账器（重写版，真正逐日状态机）。

外部审计要求（本轮修复点）：
1. 参数名 bug: 引擎参数是 early_exit_pct，不再是 ee_early_exit。
2. 禁止从 completed trades 反推前瞻信号：本脚本从持久化 state 逐日推进，当日生成信号/订单并永久写入。
3. A/B 影子账户状态持久化（forward_state_A.json / forward_state_B.json）。
4. 每日只向前处理新增日期；冻结前（<2026-09-07）日期只静默推进状态、不写前瞻台账。
5. 信号当天写死、A/B 共用 signal_id；订单永久记录（FILLED/REJECTED/DEFERRED/NO_FILL_LIMIT_DOWN）。
6. 每日 P* 当天冻结；每日权益只能 append；输入数据 hash 持久化（防数据修订污染）。
7. 启动状态: 回放到冻结引擎数据末日(2026-08-25)，检查 PRE_EXISTING 持仓。
"""
import os, sys, json, glob, hashlib
import numpy as np, pandas as pd

GITHUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../github_repo (__file__ 位于 src/)
NEWCHAT = os.path.dirname(os.path.dirname(GITHUB))                     # .../new-chat
sys.path.insert(0, GITHUB)
sys.path.insert(0, NEWCHAT)
from round51_audit import prepare_v51
from forward_engine import ForwardAccount, build_input_hash, compute_raw_candidates
from forward_ext_data import merge_extended, build_ext_days, FROZEN_END

FORWARD_START = pd.Timestamp('2026-09-07')   # 前瞻起点（冻结指令：只统计 09-07 及以后首次出现的合法新信号）
SEED_END = FROZEN_END                         # 冻结引擎数据末日（启动回放终点）
A_MULT = 1.000
B_MULT = 0.985

OUT = os.path.join(GITHUB, 'results', 'evidence', 'forward')
DATA_ROOT = os.path.join(NEWCHAT, 'data', 'raw')


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


def scan_daily_max_dates():
    """全分片扫描 daily/*.parquet 主流/下限日期（避免只取第一个分片误报）。"""
    mx_main, mx_min = [], []
    for f in glob.glob(os.path.join(DATA_ROOT, 'daily', '*.parquet')):
        try:
            md = pd.read_parquet(f, columns=['date'])
            mx_main.append(md['date'].max())
            mx_min.append(md['date'].min())
        except Exception:
            continue
    return pd.Timestamp(max(mx_main)), pd.Timestamp(min(mx_min))


def df_append(path, rows, cols, drop_dups=None):
    """append-only 写表：存在则读旧表合并追加，可去重键。
    注意: keep_default_na=False 使 'NA' 等显式标记不会被 pandas 读成 NaN（避免历史行被改写）。"""
    df_new = pd.DataFrame(rows, columns=cols)
    if os.path.exists(path):
        old = pd.read_csv(path, dtype=str, keep_default_na=False)
        if len(old) == 0:
            merged = df_new
        else:
            merged = pd.concat([old, df_new.astype(str)], ignore_index=True)
            if drop_dups:
                merged = merged.drop_duplicates(subset=drop_dups, keep='last')
        merged.to_csv(path, index=False)
    else:
        df_new.to_csv(path, index=False)


def load_rows(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.DataFrame()


def signal_seq_no(path, ts_code, signal_date):
    """该 (ts_code, signal_date) 已用信号序号。"""
    df = load_rows(path)
    if len(df) == 0:
        return 0
    sub = df[(df['ts_code'] == ts_code) & (df['signal_date'] == signal_date)]
    return int(len(sub))


def run_forward(days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map,
                out_dir, data_through, today, name_map=None):
    """逐日推进 + 台账写入。可被测试 harness 以扩展数据调用。返回 (n_days, n_sig)。"""
    os.makedirs(out_dir, exist_ok=True)
    if name_map is None:
        name_map = {}
    day_idx = {d: i for i, d in enumerate(days)}
    print(f'  data_through={data_through.date()} today={today.date()}')

    # ---------- 启动状态（首次运行） ----------
    for mult, tag in ((A_MULT, 'A'), (B_MULT, 'B')):
        state_path = os.path.join(out_dir, f'forward_state_{tag}.json')
        if not os.path.exists(state_path):
            print(f'  [{tag}] 首次运行：回放启动状态到 {SEED_END.date()} (exit_multiplier={mult}) ...')
            acct = ForwardAccount(exit_multiplier=mult)
            eqs = acct.play_to(days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset,
                               SEED_END, corp_map=corp_map)
            snap = acct.snapshot()
            with open(state_path, 'w') as f:
                json.dump(snap, f, ensure_ascii=False, indent=1)
            pre = [(p['ts_code'], name_map.get(p['ts_code'], ''), p['entry_date'], p['levels'], p['shares'],
                    round(p['total_cost'], 2)) for p in acct.positions]
            pd.DataFrame(pre, columns=['ts_code', 'name', 'entry_date', 'levels', 'shares', 'total_cost']).to_csv(
                os.path.join(out_dir, f'forward_pre_existing_{tag}.csv'), index=False)
            last_eq = eqs[-1]
            print(f'  [{tag}] 启动完成: cash={last_eq["cash"]:.2f} stock_val={last_eq["stock_val"]:.2f} '
                  f'etf_sh={last_eq["etf_sh"]} positions={len(acct.positions)} '
                  f'(PRE_EXISTING {len(acct.positions)} 笔已保存，不计入 09-07 后新信号)')
        else:
            print(f'  [{tag}] state 已存在，载入')

    # ---------- 逐日推进 ----------
    acctA = ForwardAccount.load(json.load(open(os.path.join(out_dir, 'forward_state_A.json'))))
    acctB = ForwardAccount.load(json.load(open(os.path.join(out_dir, 'forward_state_B.json'))))
    last_proc = acctA.last_processed_date
    assert acctB.last_processed_date == last_proc, 'A/B last_processed_date 不一致'
    if last_proc not in day_idx:
        raise SystemExit(
            f'[FATAL] state.last_processed_date={last_proc.date()} 不在当前数据 days 中'
            f'（数据末日={data_through.date()}）。数据缺失/回退时禁止从头重放覆盖 state：'
            f'请先补齐数据或恢复 state 后再运行。')
    start_i = day_idx[last_proc] + 1
    end_i = day_idx.get(data_through, len(days) - 1)

    sig_path = os.path.join(out_dir, 'forward_signal_ledger.csv')
    ord_path = os.path.join(out_dir, 'forward_order_ledger.csv')
    trd_path = os.path.join(out_dir, 'forward_trade_ledger.csv')
    eq_path = os.path.join(out_dir, 'forward_daily_equity.csv')
    ps_path = os.path.join(out_dir, 'forward_pstar_daily.csv')
    mn_path = os.path.join(out_dir, 'forward_input_manifest.csv')

    sig_cols = ['signal_id', 'ts_code', 'stock_name', 'signal_date', 'generated_at', 'data_available_through',
                'candidate_rank', 'amount_rank', 'signal_type', 'level_target', 'entry_target_date',
                'close', 'bb_lower', 'BB_z', 'bb_width_pct', 'dynamic_Pstar', 'base_exit_line',
                'ee15_exit_line', 'daily_high', 'raw_candidate', 'A_held', 'B_held',
                'A_admission_status', 'B_admission_status', 'A_order_created', 'B_order_created',
                'A_reject_reason', 'B_reject_reason', 'backfilled']
    ord_cols = ['order_id', 'system', 'signal_id', 'created_date', 'intended_execution_date',
                'action', 'ts_code', 'target_price', 'target_shares', 'reason', 'status',
                'filled_date', 'filled_price', 'filled_shares', 'created_at', 'data_available_through', 'backfilled']
    trd_cols = ['system', 'order_id', 'signal_id', 'ts_code', 'date', 'event',
                'price', 'shares', 'gross', 'commission', 'transfer_fee', 'stamp_tax', 'slippage',
                'dividend', 'split', 'tax_settle', 'cash_before', 'cash_after', 'position_shares_after', 'note']
    eq_cols = ['date', 'system', 'cash', 'stock_market_value', 'ETF_market_value', 'dividend_cash_today',
               'tax_paid_today', 'fees_today', 'total_equity', 'open_positions', 'ETF_shares',
               'generated_at', 'data_available_through', 'backfilled']
    ps_cols = ['date', 'system', 'ts_code', 'level', 'entry_date', 'Pstar_raw', 'threshold', 'eff_threshold',
               'exit_multiplier', 'daily_high', 'triggered', 'order_created', 'hold_days', 'float_pnl',
               'generated_at', 'data_available_through', 'backfilled']
    mn_cols = ['processing_date', 'data_available_through', 'input_hash', 'generated_at', 'backfilled']

    n_days = 0
    n_sig = 0
    for i in range(start_i, end_i + 1):
        d = days[i]
        dd = D[d]
        ei = etf_idx.get(d)
        epx = etf_px[ei] if ei is not None else np.nan
        eopx = etf_open[ei] if ei is not None else np.nan
        corp = corp_map.get(str(d.date()))
        # 冻结前（<09-07）：静默推进状态，不写前瞻台账（09-01~09-06 属冻结前，即使补齐数据也不得纳入）
        silent = d < FORWARD_START
        backfilled = 0 if (d == today and d == data_through) else 1
        h = build_input_hash(d, dd, ei, epx, eopx, corp)

        # P0-1 第一层：市场层 raw candidate 只算一次，A/B 同源共用（不含账户 K/持仓/现金）
        gi = offset + i
        raw = compute_raw_candidates(d, dd, gi, first_eligible_i, acctA.top_n)
        resA = acctA.process_day(i, d, dd, ei, epx, eopx, corp, days, D, etf_idx, etf_px, etf_open,
                                 first_eligible_i, offset, gi=gi, raw_candidates=raw)
        resB = acctB.process_day(i, d, dd, ei, epx, eopx, corp, days, D, etf_idx, etf_px, etf_open,
                                 first_eligible_i, offset, gi=gi, raw_candidates=raw)
        # 机器 invariant（P0-1）：市场层 raw candidate 集合 A/B 必须一致（同源，天然成立）。
        # 禁止 invariant：admitted/order 集合永远相同——账户层允许合法分叉（K 槽/现金/持仓不同）。
        assert [r['ts_code'] for r in resA['raw_candidates']] == [r['ts_code'] for r in resB['raw_candidates']], \
            f'{d.date()}: raw candidate 不一致'

        if not silent:
            n_days += 1
            # ---- 信号台账（P0-1 分层）----
            # NEW_ENTRY：市场层 raw candidate 一行（A/B 同源），A/B admission/订单/拒绝原因分别记录。
            # ADD_ON：持仓侧信号（A/B 各自），B 提前退出后无持仓则无 ADD——合法分叉。
            a_new = {s['ts_code']: s for s in resA['signals'] if s['signal_type'] == 'NEW_ENTRY'}
            b_new = {s['ts_code']: s for s in resB['signals'] if s['signal_type'] == 'NEW_ENTRY'}
            # 同 raw 源 → key 集合必须相等（机器 invariant）
            assert set(a_new) == set(b_new), f"{d.date()}: NEW_ENTRY raw 集合 A/B 不一致"
            for tc in sorted(set(a_new)):
                sA, sB = a_new[tc], b_new[tc]
                seq = signal_seq_no(sig_path, tc, str(d.date())) + 1
                sid = f"FWD-{tc}-{str(d.date())}-{seq}"
                entry_target = days[i + 1] if i + 1 < len(days) else None
                a_held = tc in {p['ts_code'] for p in acctA.positions}
                b_held = tc in {p['ts_code'] for p in acctB.positions}
                row = [sid, tc, name_map.get(tc, '') or '', str(d.date()),
                       pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), str(data_through.date()),
                       sA['candidate_rank'] if np.isfinite(sA['candidate_rank']) else '',
                       sA['amount_rank'] if np.isfinite(sA['amount_rank']) else '',
                       'NEW_ENTRY', 1,
                       str(entry_target.date()) if entry_target is not None else '',
                       round(sA['close'], 4) if np.isfinite(sA['close']) else '',
                       round(sA['bb_lower'], 4) if np.isfinite(sA['bb_lower']) else '',
                       round(sA['bb_z'], 4) if np.isfinite(sA['bb_z']) else '',
                       round(sA['bb_width_pct'], 4) if np.isfinite(sA['bb_width_pct']) else '',
                       'NA', 'NA', 'NA',
                       round(sA['daily_high'], 4), 1, int(a_held), int(b_held),
                       sA['admission_status'], sB['admission_status'],
                       1 if sA['admission_status'] == 'ADMITTED' else 0,
                       1 if sB['admission_status'] == 'ADMITTED' else 0,
                       sA['reject_reason'], sB['reject_reason'], backfilled]
                df_append(sig_path, [row], sig_cols, drop_dups='signal_id')
                n_sig += 1
                # 回填 pending_buy 的 signal_id（供次日 BUY 成交追溯；A/B 各自）
                for pb in acctA.pending_buy:
                    if pb['ts_code'] == tc and pb.get('signal_date') == str(d.date()):
                        pb['signal_id'] = sid
                for pb in acctB.pending_buy:
                    if pb['ts_code'] == tc and pb.get('signal_date') == str(d.date()):
                        pb['signal_id'] = sid
            # ADD_ON（A/B 各自持仓侧信号，带系统后缀避免同 day 同股去重冲突）
            for tag, res, acct in (('A', resA, acctA), ('B', resB, acctB)):
                for s in res['signals']:
                    if s['signal_type'] != 'ADD_ON':
                        continue
                    seq = signal_seq_no(sig_path, s['ts_code'], s['signal_date']) + 1
                    sid = f"FWD-{s['ts_code']}-{s['signal_date']}-{seq}-{tag}"
                    entry_target = days[i + 1] if i + 1 < len(days) else None
                    dyn_p, base_ln, ee15_ln = np.nan, np.nan, np.nan
                    for p in res['pstars']:
                        if p['ts_code'] == s['ts_code'] and p['date'] == s['signal_date']:
                            dyn_p = p['pstar_raw']; base_ln = p['threshold']; ee15_ln = p['eff_threshold']
                            break
                    other_tag = 'B' if tag == 'A' else 'A'
                    other_acct = acctB if tag == 'A' else acctA
                    other_held = s['ts_code'] in {p['ts_code'] for p in other_acct.positions}
                    row = [sid, s['ts_code'], name_map.get(s['ts_code'], '') or '', s['signal_date'],
                           pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), str(data_through.date()),
                           '', '', 'ADD_ON', s['level_target'],
                           str(entry_target.date()) if entry_target is not None else '',
                           round(s['close'], 4) if np.isfinite(s['close']) else '',
                           round(s['bb_lower'], 4) if np.isfinite(s['bb_lower']) else '',
                           round(s['bb_z'], 4) if np.isfinite(s['bb_z']) else '',
                           round(s['bb_width_pct'], 4) if np.isfinite(s['bb_width_pct']) else '',
                           round(dyn_p, 4) if isinstance(dyn_p, float) and np.isfinite(dyn_p) else dyn_p,
                           round(base_ln, 4) if isinstance(base_ln, float) and np.isfinite(base_ln) else base_ln,
                           round(ee15_ln, 4) if isinstance(ee15_ln, float) and np.isfinite(ee15_ln) else ee15_ln,
                           round(s['daily_high'], 4), 0,
                           int(tag == 'A' or other_held), int(tag == 'B' or other_held),
                           'ADMITTED' if tag == 'A' else '', 'ADMITTED' if tag == 'B' else '',
                           1 if tag == 'A' else 0, 1 if tag == 'B' else 0,
                           '', '', backfilled]
                    df_append(sig_path, [row], sig_cols, drop_dups='signal_id')
                    n_sig += 1
            # ---- 订单台账 ----
            # 创建即记录：当日新生成的 pending_buy / pending_add 立即写 CREATED 行（不得等成交/取消才出现）
            for tag, acct in (('A', acctA), ('B', acctB)):
                for pb in acct.pending_buy:
                    if pb.get('signal_date') == str(d.date()) and pb.get('signal_id'):
                        oid = f"ORD-{tag}-{pb['signal_id']}-BUY-{pb['signal_date']}"
                        df_append(ord_path, [[
                            oid, tag, pb['signal_id'], pb['signal_date'], pb['signal_date'],
                            'BUY', pb['ts_code'], '', '', 'new-entry candidate (T+1 open fill)', 'CREATED',
                            '', '', '', pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
                            str(data_through.date()), backfilled]], ord_cols)
                for tc, sig_date in acct.pending_add.items():
                    if sig_date == str(d.date()):
                        pos = next((p for p in acct.positions if p['ts_code'] == tc), None)
                        sid = pos.get('signal_id', '') if pos else ''
                        if sid:
                            oid = f"ORD-{tag}-{sid}-ADD-{sig_date}"
                            df_append(ord_path, [[
                                oid, tag, sid, sig_date, sig_date,
                                'ADD', tc, '', '', 'add-on candidate (T+1 open fill)', 'CREATED',
                                '', '', '', pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
                                str(data_through.date()), backfilled]], ord_cols)
            for tag, res in (('A', resA), ('B', resB)):
                for o in res['orders']:
                    created = o.get('created_date', o['date'])
                    oid = f"ORD-{tag}-{o.get('signal_id', '')}-{o['event_type']}-{created}"
                    df_append(ord_path, [[
                        oid, tag, o.get('signal_id', ''), created,
                        o.get('intended_execution_date', o['date']),
                        o['event_type'], o['ts_code'], '', '', o['note'], o['status'],
                        o.get('filled_date', ''), o.get('filled_price', ''), o.get('qty', ''),
                        pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), str(data_through.date()), backfilled]],
                        ord_cols)
            # ---- 成交台账 ----
            for tag, res in (('A', resA), ('B', resB)):
                for e in res['trades']:
                    commission = float(e['fee']) - float(e['stamp_tax'] or 0) - float(e['transfer_fee'] or 0)
                    # BUY/BUY_ADD 的订单创建日 = 信号日（从 signal_id 解析: FWD-{ts_code}-{yyyy}-{mm}-{dd}-{seq}）
                    oid = f"ORD-{tag}-{e.get('signal_id', '')}-{e['event_type']}-{e['date']}"
                    if e['event_type'] in ('BUY', 'BUY_ADD') and e.get('signal_id'):
                        parts = e['signal_id'].split('-')
                        sd = '-'.join(parts[2:5]) if len(parts) >= 5 else e['date']
                        act = 'BUY' if e['event_type'] == 'BUY' else 'ADD'
                        oid = f"ORD-{tag}-{e['signal_id']}-{act}-{sd}"
                    df_append(trd_path, [[
                        tag, oid, e.get('signal_id', ''), e['ts_code'], e['date'], e['event_type'],
                        round(float(e['price']), 4) if not np.isnan(e['price']) else '',
                        e['shares'], round(float(e['gross']), 2), round(commission, 2),
                        round(float(e['transfer_fee'] or 0), 2), round(float(e['stamp_tax'] or 0), 2),
                        round(float(e['slippage'] or 0), 2), round(float(e['dividend'] or 0), 2),
                        e.get('split', 0), round(float(e['tax_settle'] or 0), 2),
                        round(float(e['cash_before']), 2), round(float(e['cash_after']), 2),
                        e['position_shares_after'], e['note']]], trd_cols)
            # ---- 权益台账 ----
            for tag, res in (('A', resA), ('B', resB)):
                div_today = sum(float(e.get('dividend') or 0) for e in res['trades']
                                if e['event_type'] == 'DIVIDEND')
                tax_today = sum(float(e.get('tax_settle') or 0) for e in res['trades'])
                fees_today = sum(float(e.get('fee') or 0) for e in res['trades'])
                df_append(eq_path, [[
                    str(d.date()), tag, round(res['equity']['cash'], 2),
                    round(res['equity']['stock_val'], 2), round(res['equity']['etf_val'], 2),
                    round(div_today, 2), round(tax_today, 2), round(fees_today, 2),
                    round(res['equity']['equity'], 2), len(acctA.positions if tag == 'A' else acctB.positions),
                    res['equity']['etf_sh'],
                    pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), str(data_through.date()), backfilled]],
                    eq_cols)
            # ---- 每日 P* 冻结 ----
            for tag, res in (('A', resA), ('B', resB)):
                for p in res['pstars']:
                    df_append(ps_path, [[
                        p['date'], tag, p['ts_code'], p['level'], p['entry_date'],
                        round(p['pstar_raw'], 4), round(p['threshold'], 4), round(p['eff_threshold'], 4),
                        p['exit_multiplier'], round(p['high_raw'], 4), int(p['triggered']),
                        int(p['triggered']), p['hold_days'], round(p['float_pnl'], 2),
                        pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), str(data_through.date()), backfilled]],
                        ps_cols)
            # ---- 输入 hash ----
            df_append(mn_path, [[
                str(d.date()), str(data_through.date()), h,
                pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), backfilled]], mn_cols)
        else:
            print(f'  {d.date()} 冻结前（静默推进状态，不写前瞻台账）')
        print(f'  processed {d.date()} (i={i})')

    # 机器 invariant: 前瞻台账不得含 09-07 之前日期（9/1~9/6 机器级禁止）
    for path in (sig_path, trd_path, eq_path):
        df = load_rows(path)
        if len(df) > 0 and 'signal_date' in df.columns:
            assert pd.to_datetime(df['signal_date']).min() >= FORWARD_START, \
                f'{os.path.basename(path)} 含冻结前信号日期'
        if len(df) > 0 and 'date' in df.columns:
            ds = pd.to_datetime(df['date'])
            assert ds.min() >= FORWARD_START, f'{os.path.basename(path)} 含冻结前日期'

    # 保存状态
    json.dump(acctA.snapshot(), open(os.path.join(out_dir, 'forward_state_A.json'), 'w'), ensure_ascii=False, indent=1)
    json.dump(acctB.snapshot(), open(os.path.join(out_dir, 'forward_state_B.json'), 'w'), ensure_ascii=False, indent=1)

    print(f'== DONE: 处理 {n_days} 个前瞻交易日, 新信号 {n_sig} 条 ==')
    print(f'  state 推进至 {acctA.last_processed_date.date()}')
    return n_days, n_sig


def main():
    print('== FORWARD UPDATE ==')
    print(f'  data_root  = {DATA_ROOT}')
    print(f'  out        = {OUT}')
    os.makedirs(OUT, exist_ok=True)

    today = pd.Timestamp(pd.Timestamp.now().date())

    print('  加载引擎数据：冻结段 prepare_v51（≤2026-08-25 原样）+ 扩展层（>2026-08-25 真实新增行情）...')
    pret = prepare_v51(limit_down_mode='correct', st_mode='pit')
    days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = merge_extended(pret)
    ext_days, ext_D, *_ = build_ext_days()
    data_through = max(days)
    print(f'  冻结段末日 = {SEED_END.date()}')
    print(f'  扩展段真实新增交易日 = {len(ext_days)} 个（{ext_days[0].date() if ext_days else "-"} .. {ext_days[-1].date() if ext_days else "-"}）')
    print(f'  data_available_through = {data_through.date()}')

    corp_map = load_corp_map()
    name_map = {}
    try:
        sb = pd.read_parquet(os.path.join(DATA_ROOT, 'stock_basic.parquet'))
        name_map = dict(zip(sb['ts_code'].astype(str), sb['name'].astype(str)))
    except Exception as exc:
        print(f'  [warn] stock_basic 读取失败，signal 表 stock_name 留空: {exc}')

    run_forward(days, D, etf_idx, etf_px, etf_open, first_eligible_i, offset, corp_map,
                OUT, data_through, today, name_map=name_map)

    # 状态判定（P0-2）：只有真实 2026-09-07+ 数据落盘后才可进入 LIVE
    if data_through < FORWARD_START:
        print(f'\n== PRODUCTION NOT STARTED ==')
        print(f'  尚无 2026-09-07 及以后的真实行情（当前数据止于 {data_through.date()}）。')
        print(f'  已用真实扩展数据（08-26 起）推进 A/B 状态至 {data_through.date()}，未产生任何前瞻台账。')
        print(f'  状态：FROZEN / FORWARD INFRA READY / NOT YET LIVE')
    else:
        print(f'\n== 已读取真实 {FORWARD_START.date()}+ 数据并落盘 ==')
        print(f'  状态：FORWARD OBSERVATION LIVE（首条 backfilled=0 记录已产生）')


if __name__ == '__main__':
    main()
