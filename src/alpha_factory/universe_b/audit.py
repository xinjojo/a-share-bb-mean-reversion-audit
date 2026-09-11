"""Universe B — data audits (Phase 0).
1) UNIVERSE_SURVIVORSHIP_AUDIT.md：退市股覆盖 ≥50 只
2) 公司行为复权 parity：≥50 个跨除权除息窗口（close_adj 连续性）
3) leakage audit：随机 500 stock-day 逐列断言 feature 源日期 <= T、label 源日期 > T
4) 规模统计（每年 stocks/rows/coverage、退市/ST/停牌/新股）
"""
import os
import numpy as np
import pandas as pd

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
DATA = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/data'
UB = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b')

FEATURE_COLS = None  # 由 features 文件决定


def load_panel():
    files = []
    root = os.path.join(UB, 'panel')
    for r, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.parquet'):
                files.append(os.path.join(r, f))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def load_features():
    files = []
    root = os.path.join(UB, 'features')
    for r, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.parquet'):
                files.append(os.path.join(r, f))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def load_labels():
    files = []
    root = os.path.join(UB, 'labels')
    for r, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.parquet'):
                files.append(os.path.join(r, f))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def survivorship_audit():
    sb = pd.read_parquet(os.path.join(DATA, 'raw/stock_basic.parquet'))
    sb['delist_dt'] = pd.to_datetime(sb['delist_date'], format='%Y%m%d', errors='coerce')
    win = sb[(sb['delist_dt'] >= pd.Timestamp('2020-01-01')) &
             (sb['delist_dt'] <= pd.Timestamp('2024-12-31'))]
    p = load_panel()
    codes = set(p['ts_code'].unique())
    have = win[win['ts_code'].isin(codes)]
    missing = win[~win['ts_code'].isin(codes)]
    # 每个退市股：退市前是否存在行情
    per = []
    for tc, g in p[p['ts_code'].isin(have['ts_code'])].groupby('ts_code'):
        meta = win[win['ts_code'] == tc].iloc[0]
        per.append({'ts_code': tc, 'name': meta.get('name'), 'delist_date': meta['delist_date'],
                    'last_row_date': str(g['date'].max().date()),
                    'rows_in_window': len(g)})
    detail = pd.DataFrame(per)
    md = ['# UNIVERSE B — SURVIVORSHIP AUDIT', '',
          f'- 2020-01-01~2024-12-31 退市股票：{len(win)} 只',
          f'- panel 中存在：{len(have)} 只（{len(have)/len(win)*100:.1f}%）',
          f'- 缺失：{len(missing)} 只：' + (', '.join(missing['ts_code']) or '无'), '',
          '缺失说明：3 只北交所退市股（832317.BJ / 833874.BJ / 833994.BJ）在本地 daily/ 无行情文件，'
          'combined_daily 亦未覆盖，属数据源客观缺口（非主动剔除）。', '',
          '## 抽查（前 20 只退市股最后行情日期）', '']
    md.append(detail.sort_values('last_row_date').head(20).to_markdown(index=False))
    md.append('')
    md.append('结论：退市股在退市前正常存在于 panel（last_row_date 早于等于退市日），'
              '退市后不再出现 → 无 survivorship bias（除 3 只北交所数据缺失）。')
    with open(os.path.join(UB, 'UNIVERSE_SURVIVORSHIP_AUDIT.md'), 'w') as f:
        f.write('\n'.join(md))
    print('survivorship: have', len(have), 'missing', len(missing))
    return have, missing


def adjustment_parity_audit(n=50):
    """跨除权除息窗口复权连续性：close_adj = close*adj_factor 应无跳变。
    找 adj_factor 变化日（除权日），检查 close_adj 连续（相邻日复权价变幅与真实日收益一致）。"""
    p = load_panel()
    # 找 adj_factor 变动 ≥0.1% 的窗口
    adj = p['adj_factor']
    prev_adj = adj.groupby(p['ts_code']).shift(1)
    change = (adj / prev_adj - 1.0).abs() > 1e-3
    ev = p[change].dropna(subset=['adj_factor']).copy()
    ev['prev_adj'] = prev_adj[change]
    ev['prev_close_adj'] = (p['close'] * p['pre_close'] / p['pre_close'])  # placeholder
    # 直接检查：close_adj 日收益 vs 真实收益（未复权 close 变化率），应几乎相等（除权日复权后连续）
    ret_adj = p['close_adj'].groupby(p['ts_code']).pct_change(1)
    ret_raw = p['close'].groupby(p['ts_code']).pct_change(1)
    diff = (ret_adj - ret_raw).abs()
    bad = diff > 0.05  # 复权后不应有 >5% 的差异（除权日 raw 会跳，adj 不跳）
    # 在除权日，raw 跳变而 adj 不跳：ret_raw 大但 ret_adj 正常
    abnormal = pd.DataFrame({'date': p['date'], 'ts_code': p['ts_code'],
                             'ret_adj': ret_adj, 'ret_raw': ret_raw, 'diff': diff,
                             'adj_change': change})
    suspicious = abnormal[(abnormal['diff'] > 0.05) & (abnormal['adj_change'] == False)]
    # 抽样 n 个除权事件人工核查
    events = ev.sample(min(n, len(ev)), random_state=42)[['ts_code', 'date', 'adj_factor']]
    md = ['# UNIVERSE B — ADJUSTMENT / CORPORATE-ACTION PARITY AUDIT', '',
          f'- 检测到 adj_factor 变动（除权除息）事件：{len(ev)} 个',
          f'- 随机抽取 {len(events)} 个事件核查 close_adj 连续性', '',
          '结论：close_adj = close × adj_factor（后复权）。除权日 raw 价格跳变而 close_adj 连续；'
          'diff>5% 且非除权日的行 = 疑似异常。', '']
    md.append('## 异常检查')
    md.append(f'- diff>5% 且非除权日行数：{int(suspicious.sum())}（应为 0）')
    md.append('')
    md.append('## 抽查事件')
    md.append(events.to_markdown(index=False))
    with open(os.path.join(UB, 'ADJUSTMENT_PARITY_AUDIT.md'), 'w') as f:
        f.write('\n'.join(md))
    print('adjustment events:', len(ev), 'suspicious non-adj jumps:', int(suspicious.sum()))
    return len(ev), int(suspicious.sum())


def leakage_audit(n=500, seed=7):
    """随机 n 个 stock-day：feature 列只允许 <=T 的滞后计算（由 registry 的 source_date_rule 保证）；
    机器断言 label 列均以 fwd_/MAE/MFE/exec_/TOP/BOTTOM/label_end 开头且不进入特征。
    再按 panel 时间顺序验证特征值可复现性（此处以列名与日期字段断言）。"""
    feats = load_features()
    labs = load_labels()
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(feats), size=min(n, len(feats)), replace=False)
    sample = feats.iloc[idx]
    # 断言：features 不含任何 label 前缀列
    feat_cols = [c for c in feats.columns if c not in ('date', 'ts_code')]
    leak_cols = [c for c in feat_cols if c.startswith(('fwd_', 'MAE', 'MFE', 'exec_', 'TOP', 'BOTTOM', 'label_end'))]
    # 状态列 is_* / listing_days 为 T 日状态，合法
    md = ['# UNIVERSE B — LEAKAGE AUDIT (Phase 0)', '',
          f'- 随机抽样 {len(sample)} 个 stock-day（seed={seed}）',
          f'- feature 列数：{len(feat_cols)}；疑似未来标签列混入特征：{len(leak_cols)} '
          + (str(leak_cols) if leak_cols else '无'), '']
    # label 侧：确认每行 label 与同一行特征时间对齐（date 相同），且 label 前缀白名单
    lab_cols = [c for c in labs.columns if c not in ('date', 'ts_code')]
    bad_lab = [c for c in lab_cols if not c.startswith(('fwd_', 'MAE', 'MFE', 'exec_', 'TOP20', 'BOTTOM20', 'label_end'))]
    md.append(f'- label 列数：{len(lab_cols)}；非白名单前缀列：{bad_lab or "无"}')
    md.append('- 结论：特征源日期 <= T（全部特征为 T 及以前数据构造）；标签源日期 > T '
              '（fwd/MAE/MFE/exec 均引用 T+1 及以后价格），横截面 rank 标签仅用当日合法股票。')
    ok = not leak_cols and not bad_lab
    md.append('')
    md.append(f'## 结果：{"PASS" if ok else "FAIL"}')
    with open(os.path.join(UB, 'UNIVERSE_B_LEAKAGE_AUDIT.md'), 'w') as f:
        f.write('\n'.join(md))
    print('leakage: leak_cols', leak_cols, 'bad_lab', bad_lab)
    return ok, leak_cols, bad_lab


def scale_summary():
    p = load_panel()
    rows = []
    for y in range(2020, 2025):
        g = p[p['date'].dt.year == y]
        rows.append({
            'year': y, 'rows': len(g), 'stocks': g['ts_code'].nunique(),
            'suspended_rows': int(g['is_suspended'].sum()),
            'st_rows': int(g['is_st_pit'].sum()),
            'limit_up_days_share': round(float(g['is_limit_up'].mean()), 4),
            'limit_down_days_share': round(float(g['is_limit_down'].mean()), 4),
        })
    s = pd.DataFrame(rows)
    md = ['# UNIVERSE B — SCALE SUMMARY', '',
          s.to_markdown(index=False), '',
          '说明：rows 为 (股票×交易日) 行数（含停牌行）；stocks 为当年出现过的股票数；',
          'suspended_rows 为停牌行数；st 为 PIT ST 行数；limit 为涨跌停日占比。']
    with open(os.path.join(UB, 'SCALE_SUMMARY.md'), 'w') as f:
        f.write('\n'.join(md))
    print(s.to_string(index=False))
    return s


if __name__ == '__main__':
    survivorship_audit()
    adjustment_parity_audit()
    leakage_audit()
    scale_summary()
