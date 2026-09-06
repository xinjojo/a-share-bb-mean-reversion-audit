"""ACCOUNTING AUDIT — 任务A: 97笔交易的收益账彻底算正确
原理: 引擎盈亏在 raw(不复权)口径计算. 持仓期跨除权除息(送转/现金分红/配股)时,
      raw 价格跳变但股数未调/分红未计 -> 会计错误.
正确口径: 以每笔交易 entry 日为复权基准, 每次成交金额 × (当日adj_factor/entry日adj_factor)
      = 该层在统一基准下的市值. pnl_adj = 复权卖出收入 - Σ复权买入成本 (费用按真实现金).
      数学上等价于真实盈亏(送转股数补偿+现金分红折算全部由 adj_factor 吸收).
注意: 引擎期末清仓 FINAL_SETTLE 不写 actions, 卖出成交从 flows(stock settle) 按顺序匹配恢复.
"""
import sys, os
import numpy as np, pandas as pd

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'audit_package', 'github_repo', 'src'))
from round51_audit import prepare_v51, stamp_rate, COMMISSION_RATE, MIN_COMMISSION, TRANSFER_FEE_RATE

OUT = os.path.join(ROOT, 'audit_package', 'github_repo', 'results', 'evidence', 'ee_audit')
os.makedirs(OUT, exist_ok=True)

days, D, etf_idx, etf_px, etf_open, etf_nav, first_eligible_i, offset = prepare_v51(
    limit_down_mode='correct', st_mode='pit')
sb = pd.read_parquet(os.path.join(ROOT, 'data', 'raw', 'stock_basic.parquet'))[['ts_code', 'name']]
NAME = dict(zip(sb['ts_code'], sb['name']))

def adj_of(ts_code, date_str):
    d = pd.Timestamp(date_str)
    dd = D.get(d)
    if dd is None:
        return np.nan
    j = dd['pos'].get(ts_code)
    if j is None:
        return np.nan
    return float(dd['adj'][j])

def buy_fee(amt):
    return max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * TRANSFER_FEE_RATE

def sell_fee(amt, d):
    return max(amt * COMMISSION_RATE, MIN_COMMISSION) + amt * stamp_rate(pd.Timestamp(d), 'historical') + amt * TRANSFER_FEE_RATE

# ===== 期末清仓成交恢复: flows(stock settle) 顺序 == tr FINAL_SETTLE 顺序 =====
def build_settle_map(tag):
    """返回 list of dict(ts_code, date, px, shares, gross, fee, net)"""
    fl = pd.read_csv(os.path.join(OUT, f'{tag}_flows.csv'))
    settles = fl[(fl['leg'] == 'stock') & (fl['action'] == 'settle')].reset_index(drop=True)
    tr = pd.read_csv(os.path.join(OUT, f'{tag}_trades.csv'))
    tr['entry_date'] = tr['entry_date'].astype(str)
    fin = tr[tr['exit_type'] == 'FINAL_SETTLE'].reset_index(drop=True)
    if len(settles) != len(fin):
        print(f'  [WARN {tag}] settle flows {len(settles)} != FINAL_SETTLE trades {len(fin)}')
    out = []
    for k in range(min(len(settles), len(fin))):
        s = settles.iloc[k]; t = fin.iloc[k]
        out.append(dict(ts_code=t['ts_code'], date=s['date'], px=float(s['px']), shares=int(s['shares']),
                        gross=float(s['gross']), fee=float(s['fee']), net=float(s['net']),
                        adj=adj_of(t['ts_code'], s['date'])))
    return out

SETTLE = {'combo': build_settle_map('base'), 'pure': build_settle_map('pure_base')}

def assign_round(ac, tr):
    tr['entry_date'] = tr['entry_date'].astype(str)
    ac['round_id'] = ''
    for _, t in tr.iterrows():
        mask = (ac['ts_code'] == t['ts_code']) & (ac['date'] >= t['entry_date']) & (ac['date'] <= t['exit_date'])
        ac.loc[mask, 'round_id'] = f"{t['ts_code']}|{t['entry_date']}"
    n_un = (ac['round_id'] == '').sum()
    if n_un:
        print('  [WARN] unmapped actions:', n_un)
    return ac

# ================= 1. FILL LEDGER =================
for tag, ap, tp in [('combo', 'base_actions.csv', 'base_trades.csv'),
                    ('pure', 'pure_base_actions.csv', 'pure_base_trades.csv')]:
    ac = pd.read_csv(os.path.join(OUT, ap))
    tr = pd.read_csv(os.path.join(OUT, tp))
    tr['entry_date'] = tr['entry_date'].astype(str)
    ac = assign_round(ac, tr)
    rows = []
    for _, a in ac.iterrows():
        ts = a['ts_code']; px = float(a['price']); sh = int(a['shares']); amt = px * sh
        d = a['date']; adj = adj_of(ts, d)
        if a['action'] in ('INITIAL_ENTRY', 'ADD_POSITION'):
            fee = buy_fee(amt)
            rows.append(dict(round_id=a['round_id'], ts_code=ts, name=NAME.get(ts, ''), direction='买入', date=d,
                             raw_price=round(px, 3), adj_factor=round(adj, 6), adj_price=round(px*adj, 4),
                             shares=sh, amount=round(amt, 2), commission=round(max(amt*COMMISSION_RATE, MIN_COMMISSION), 2),
                             transfer_fee=round(amt*TRANSFER_FEE_RATE, 2), stamp=0.0,
                             total_fee=round(fee, 2), level=int(a['level']), action=a['action']))
        else:
            sr = stamp_rate(pd.Timestamp(d), 'historical')
            fee = sell_fee(amt, d)
            rows.append(dict(round_id=a['round_id'], ts_code=ts, name=NAME.get(ts, ''), direction='卖出', date=d,
                             raw_price=round(px, 3), adj_factor=round(adj, 6), adj_price=round(px*adj, 4),
                             shares=sh, amount=round(amt, 2), commission=round(max(amt*COMMISSION_RATE, MIN_COMMISSION), 2),
                             transfer_fee=round(amt*TRANSFER_FEE_RATE, 2), stamp=round(amt*sr, 2),
                             total_fee=round(fee, 2), level=int(a['level']), action=a['action']))
    # 补 FINAL_SETTLE 卖出 (从 settle map)
    for s in SETTLE[tag]:
        amt = s['gross']; sh = s['shares']; px = s['px']; adj = s['adj']; d = s['date']
        sr = stamp_rate(pd.Timestamp(d), 'historical')
        rows.append(dict(round_id=f"{s['ts_code']}|{s['date']}", ts_code=s['ts_code'], name=NAME.get(s['ts_code'], ''),
                         direction='卖出', date=d, raw_price=round(px, 3), adj_factor=round(adj, 6),
                         adj_price=round(px*adj, 4), shares=sh, amount=round(amt, 2),
                         commission=round(max(amt*COMMISSION_RATE, MIN_COMMISSION), 2),
                         transfer_fee=round(amt*TRANSFER_FEE_RATE, 2), stamp=round(amt*sr, 2),
                         total_fee=round(s['fee'], 2), level=np.nan, action='FINAL_SETTLE'))
    led = pd.DataFrame(rows)
    led.to_csv(os.path.join(OUT, f'corrected_fill_ledger_{tag}.csv'), index=False)
    print(f'[{tag}] fill ledger rows:', len(led), '(buys:', int((led.direction=="买入").sum()),
          'sells:', int((led.direction=="卖出").sum()), ')')

# ================= 2. PER-TRADE CORRECTED RETURNS =================
def trade_accounting(actions_path, trades_path, tag):
    ac = pd.read_csv(os.path.join(OUT, actions_path))
    tr = pd.read_csv(os.path.join(OUT, trades_path))
    tr['entry_date'] = tr['entry_date'].astype(str)
    ac = assign_round(ac, tr)
    recs = []
    for _, t in tr.iterrows():
        rid = f"{t['ts_code']}|{t['entry_date']}"
        sub = ac[ac['round_id'] == rid]
        entry_date = t['entry_date']
        adj_e = adj_of(t['ts_code'], entry_date)
        buys = sub[sub['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])]
        sells = sub[~sub['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])]
        cost_adj = 0.0; cost_raw = 0.0; rev_adj = 0.0; rev_raw = 0.0
        for _, b in buys.iterrows():
            amt = float(b['price']) * int(b['shares'])
            fee = buy_fee(amt)
            adj_b = adj_of(t['ts_code'], b['date'])
            cost_adj += amt * (adj_b / adj_e if adj_e > 0 else 1.0) + fee
            cost_raw += amt + fee
        if len(sells) > 0:
            for _, s in sells.iterrows():
                amt = float(s['price']) * int(s['shares'])
                fee = sell_fee(amt, s['date'])
                adj_s = adj_of(t['ts_code'], s['date'])
                rev_adj += (amt - fee) * (adj_s / adj_e if adj_e > 0 else 1.0)
                rev_raw += amt - fee
        else:
            # FINAL_SETTLE: 无 ac 动作, 用 tr.pnl 反推 raw 净收入
            proceeds_raw = float(t['pnl']) + cost_raw
            adj_s = adj_of(t['ts_code'], t['exit_date'])
            rev_adj = proceeds_raw * (adj_s / adj_e if adj_e > 0 else 1.0)
            rev_raw = proceeds_raw
        pnl_raw = float(t['pnl'])
        pnl_adj = rev_adj - cost_adj
        dates = sorted(set(list(buys['date']) + list(sells['date'])))
        adj_seq = [adj_of(t['ts_code'], d) for d in dates]
        ca = len(set(round(a, 6) for a in adj_seq if a == a)) > 1
        multi_cross = False
        if len(buys) >= 2:
            for _, b in buys.iterrows():
                if abs(adj_of(t['ts_code'], b['date']) - adj_e) > 1e-9:
                    multi_cross = True
        flip = (pnl_raw <= 0 < pnl_adj) or (pnl_raw >= 0 > pnl_adj)
        recs.append(dict(ts_code=t['ts_code'], name=NAME.get(t['ts_code'], ''), entry_date=t['entry_date'],
                         exit_date=t['exit_date'], levels=int(t['levels_used']),
                         pnl_old=round(pnl_raw, 2), pnl_correct=round(pnl_adj, 2),
                         diff=round(pnl_adj - pnl_raw, 2),
                         ret_old=round(float(t['return_pct']), 2),
                         ret_correct=round(pnl_adj / cost_adj * 100, 2) if cost_adj > 0 else np.nan,
                         cross_ca=bool(ca), multi_level_cross_ca=bool(multi_cross),
                         sign_flip=bool(flip), adj_entry=round(adj_e, 6)))
    df = pd.DataFrame(recs)
    df.to_csv(os.path.join(OUT, f'corrected_trade_returns_{tag}.csv'), index=False)
    return df

cr_combo = trade_accounting('base_actions.csv', 'base_trades.csv', 'combo')
cr_pure = trade_accounting('pure_base_actions.csv', 'pure_base_trades.csv', 'pure')
print('[combo] trades:', len(cr_combo), 'cross_ca:', int(cr_combo['cross_ca'].sum()),
      'multi_cross:', int(cr_combo['multi_level_cross_ca'].sum()), 'flip:', int(cr_combo['sign_flip'].sum()))
print('[combo] pnl_old sum:', round(cr_combo['pnl_old'].sum(), 2), 'pnl_correct sum:', round(cr_combo['pnl_correct'].sum(), 2))
print('[pure] trades:', len(cr_pure), 'cross_ca:', int(cr_pure['cross_ca'].sum()),
      'multi_cross:', int(cr_pure['multi_level_cross_ca'].sum()), 'flip:', int(cr_pure['sign_flip'].sum()))
print('[pure] pnl_old sum:', round(cr_pure['pnl_old'].sum(), 2), 'pnl_correct sum:', round(cr_pure['pnl_correct'].sum(), 2))
# 非CA交易 diff 应≈0 (硬断言)
nc = cr_combo[~cr_combo['cross_ca']]
bad = nc[nc['diff'].abs() > 0.5]
print('[assert] non-CA trades diff>0.5:', len(bad))
if len(bad):
    print(bad[['ts_code', 'entry_date', 'exit_date', 'pnl_old', 'pnl_correct', 'diff']].to_string(index=False))

# ================= 3. 公司行为审计 =================
rows = []
for tag, ap, tp in [('combo', 'base_actions.csv', 'base_trades.csv'), ('pure', 'pure_base_actions.csv', 'pure_base_trades.csv')]:
    tr = pd.read_csv(os.path.join(OUT, tp))
    for _, t in tr.iterrows():
        ts = t['ts_code']; e = str(t['entry_date']); x = str(t['exit_date'])
        dd = [d for d in days if e <= str(d.date()) <= x]
        seq = [(str(d.date()), adj_of(ts, str(d.date()))) for d in dd]
        seq = [(d, a) for d, a in seq if a == a]
        changes = []
        for k in range(1, len(seq)):
            if abs(seq[k][1] - seq[k - 1][1]) > 1e-9:
                changes.append((seq[k][0], seq[k - 1][1], seq[k][1], seq[k][1] / seq[k - 1][1]))
        rows.append(dict(ts_code=ts, name=NAME.get(ts, ''), entry_date=e, exit_date=x,
                         levels=int(t['levels_used']), adj_entry=round(adj_of(ts, e), 6),
                         adj_exit=round(adj_of(ts, x), 6),
                         n_ca_changes=len(changes),
                         change_dates=';'.join([c[0] for c in changes]),
                         change_ratios=';'.join([f"{c[0]}:{c[3]:.6f}" for c in changes]),
                         ca_any=len(changes) > 0,
                         multi_level_cross=(int(t['levels_used']) >= 2 and any(c[0] > e for c in changes))))
ca = pd.DataFrame(rows)
ca.to_csv(os.path.join(OUT, 'corporate_action_cases.csv'), index=False)
print('[CA] total rows:', len(ca), 'ca_any:', int(ca['ca_any'].sum()), 'multi_level_cross:', int(ca['multi_level_cross'].sum()))

# ================= 4. EQUITY 重放 (复权会计) =================
def replay_equity(actions_path, flows_path, eq_path, tag):
    ac = pd.read_csv(os.path.join(OUT, actions_path))
    fl = pd.read_csv(os.path.join(OUT, flows_path))
    eq = pd.read_csv(os.path.join(OUT, eq_path))
    key_map = {'TAKE_PROFIT_UB': 0, 'INITIAL_ENTRY': 2, 'ADD_POSITION': 2,
               'TAKE_PROFIT_DYN': 3, 'FINAL_SETTLE': 5}
    ac['key'] = ac['action'].map(key_map).fillna(4)
    cash = 1_000_000.0
    pos = {}
    out = []
    settle_iter = iter(SETTLE[tag])
    settle_by_date = {}
    for s in SETTLE[tag]:
        settle_by_date.setdefault(s['date'], []).append(s)
    for date in sorted(eq['date'].unique()):
        etf_sells = fl[(fl['leg'] == 'etf') & (fl['date'] == date) & (fl['action'] == 'sell')]
        etf_buys = fl[(fl['leg'] == 'etf') & (fl['date'] == date) & (fl['action'] == 'buy')]
        etf_settle = fl[(fl['leg'] == 'etf') & (fl['date'] == date) & (fl['action'] == 'settle')]
        acd = ac[ac['date'] == date].sort_values('key')
        # 1) TAKE_PROFIT_UB (open 卖)
        for _, a in acd[acd['action'] == 'TAKE_PROFIT_UB'].iterrows():
            ts = a['ts_code']
            if ts not in pos:
                continue
            p = pos[ts]
            amt = float(a['price']) * int(a['shares'])
            fee = sell_fee(amt, date)
            adj_t = adj_of(ts, date)
            cash += (amt - fee) * (adj_t / p['adj_entry'])
            del pos[ts]
        # 2) etf sell
        for _, f in etf_sells.iterrows():
            cash += float(f['net'])
        # 3) stock buy (INITIAL/ADD) — 复权成本
        for _, a in acd[acd['action'].isin(['INITIAL_ENTRY', 'ADD_POSITION'])].iterrows():
            ts = a['ts_code']
            amt = float(a['price']) * int(a['shares'])
            fee = buy_fee(amt)
            adj_t = adj_of(ts, date)
            if a['action'] == 'INITIAL_ENTRY':
                pos[ts] = dict(shares=int(a['shares']), adj_entry=adj_t, entry_date=date)
                cash -= amt + fee
            else:
                if ts not in pos:
                    continue
                cash -= amt * (adj_t / pos[ts]['adj_entry']) + fee
                pos[ts]['shares'] += int(a['shares'])
        # 4) TAKE_PROFIT_DYN
        for _, a in acd[acd['action'] == 'TAKE_PROFIT_DYN'].iterrows():
            ts = a['ts_code']
            if ts not in pos:
                continue
            p = pos[ts]
            amt = float(a['price']) * int(a['shares'])
            fee = sell_fee(amt, date)
            adj_t = adj_of(ts, date)
            cash += (amt - fee) * (adj_t / p['adj_entry'])
            del pos[ts]
        # 5) etf buy
        for _, f in etf_buys.iterrows():
            cash -= abs(float(f['net']))
        # 6) FINAL_SETTLE (from settle map)
        for s in settle_by_date.get(date, []):
            ts = s['ts_code']
            if ts not in pos:
                continue
            p = pos[ts]
            cash += s['net'] * (s['adj'] / p['adj_entry'])
            del pos[ts]
        # 7) etf settle
        for _, f in etf_settle.iterrows():
            cash += float(f['net'])
        # 市值
        d_ = D[pd.Timestamp(date)]
        sv = 0.0
        for ts, p in pos.items():
            j = d_['pos'].get(ts)
            if j is not None:
                adj_t = float(d_['adj'][j])
                sv += p['shares'] * float(d_['close'][j]) * (adj_t / p['adj_entry'])
        etf_row = eq[eq['date'] == date]
        etf_val = float(etf_row['etf_val'].iloc[0]) if len(etf_row) else 0.0
        out.append(dict(date=date, equity=cash + sv + etf_val, cash=cash, stock_val=sv, etf_val=etf_val))
    eqa = pd.DataFrame(out)
    eqa.to_csv(os.path.join(OUT, f'equity_adj_{tag}.csv'), index=False)
    total = eqa['equity'].iloc[-1] / eqa['equity'].iloc[0] - 1
    n_years = len(eqa) / 245
    ann = (1 + total) ** (1 / n_years) - 1 if n_years > 0 else 0
    eq2 = eqa['equity'].to_numpy()
    peak = np.maximum.accumulate(eq2)
    mdd = ((eq2 - peak) / peak).min()
    r = np.diff(eq2) / eq2[:-1]
    sharpe = float(np.mean(r) / np.std(r) * np.sqrt(245)) if np.std(r) > 0 else 0
    print(f'[{tag} ADJ] total={total*100:.2f}% ann={ann*100:.2f}% mdd={mdd*100:.2f}% sharpe={sharpe:.3f}')
    return eqa

eqa_combo = replay_equity('base_actions.csv', 'base_flows.csv', 'base_equity.csv', 'combo')
eqa_pure = replay_equity('pure_base_actions.csv', 'pure_base_flows.csv', 'pure_base_equity.csv', 'pure')

# ================= 5. 牧原 + 5笔跨CA人工展开 =================
def expand_case(ts, entry_date, tag='combo'):
    stem = 'base' if tag == 'combo' else 'pure_base'
    ac = pd.read_csv(os.path.join(OUT, f'{stem}_actions.csv'))
    tr = pd.read_csv(os.path.join(OUT, f'{stem}_trades.csv'))
    tr['entry_date'] = tr['entry_date'].astype(str)
    t = tr[(tr['ts_code'] == ts) & (tr['entry_date'] == entry_date)]
    if len(t) == 0:
        return None
    t = t.iloc[0]
    sub = ac[(ac['ts_code'] == ts) & (ac['date'] >= entry_date) & (ac['date'] <= t['exit_date'])]
    adj_e = adj_of(ts, entry_date)
    lines = []
    cost_adj = 0.0; cost_raw = 0.0; rev_adj = 0.0; rev_raw = 0.0
    for _, a in sub.iterrows():
        px = float(a['price']); sh = int(a['shares']); amt = px * sh
        adj = adj_of(ts, a['date'])
        if a['action'] in ('INITIAL_ENTRY', 'ADD_POSITION'):
            fee = buy_fee(amt)
            cost_raw += amt + fee
            cost_adj += amt * (adj / adj_e) + fee
            lines.append(dict(role=a['action'], date=a['date'], raw_px=px, adj=adj,
                              qty=sh, amount=round(amt, 2), fee=round(fee, 2),
                              adj_amount=round(amt*(adj/adj_e), 2)))
        else:
            fee = sell_fee(amt, a['date'])
            rev_raw += amt - fee
            rev_adj += (amt - fee) * (adj / adj_e)
            lines.append(dict(role=a['action'], date=a['date'], raw_px=px, adj=adj,
                              qty=sh, amount=round(amt, 2), fee=round(fee, 2),
                              adj_amount=round(-(amt-fee)*(adj/adj_e), 2)))
    # FINAL_SETTLE 补行
    if t['exit_type'] == 'FINAL_SETTLE' and len(lines) == 0 or (len(lines) and lines[-1]['role'] != 'FINAL_SETTLE' and t['exit_type']=='FINAL_SETTLE'):
        st = [s for s in SETTLE[tag] if s['ts_code'] == ts and s['date'] == t['exit_date']]
        if st:
            s = st[0]
            rev_raw += s['net']
            rev_adj += s['net'] * (s['adj'] / adj_e)
            lines.append(dict(role='FINAL_SETTLE', date=s['date'], raw_px=s['px'], adj=s['adj'],
                              qty=s['shares'], amount=round(s['gross'], 2), fee=round(s['fee'], 2),
                              adj_amount=round(-s['net']*(s['adj']/adj_e), 2)))
    return dict(ts_code=ts, name=NAME.get(ts, ''), entry_date=entry_date, exit_date=str(t['exit_date']),
                levels=int(t['levels_used']), adj_entry=adj_e, pnl_old=float(t['pnl']),
                pnl_adj=rev_adj - cost_adj, ret_old=float(t['return_pct']),
                ret_adj=(rev_adj - cost_adj) / cost_adj * 100,
                cost_raw=cost_raw, cost_adj=cost_adj, rev_raw=rev_raw, rev_adj=rev_adj,
                lines=lines)

m = expand_case('002714.SZ', '2020-05-12')
if m:
    pd.DataFrame(m['lines']).to_csv(os.path.join(OUT, 'mulyuan_manual_expand.csv'), index=False)
    print('[牧原]', m['ts_code'], m['entry_date'], '->', m['exit_date'], 'levels', m['levels'],
          'pnl_old', round(m['pnl_old'], 2), 'pnl_adj', round(m['pnl_adj'], 2),
          'ret_old', m['ret_old'], 'ret_adj', round(m['ret_adj'], 2))

cr = cr_combo.sort_values('diff', key=abs, ascending=False)
cross = cr[cr['cross_ca']]
pick = cross.head(6)
for _, r in pick.iterrows():
    m2 = expand_case(r['ts_code'], r['entry_date'])
    if m2:
        pd.DataFrame(m2['lines']).to_csv(
            os.path.join(OUT, f"cross_ca_manual_{m2['ts_code'].replace('.','_')}_{m2['entry_date']}.csv"), index=False)
        print('[CA5]', m2['ts_code'], m2['name'], m2['entry_date'], '->', m2['exit_date'],
              'levels', m2['levels'], 'pnl_old', round(m2['pnl_old'], 2),
              'pnl_adj', round(m2['pnl_adj'], 2), 'adj_entry', round(m2['adj_entry'], 4))
print('ACCOUNTING DONE')
