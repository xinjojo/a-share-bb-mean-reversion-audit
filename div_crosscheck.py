#!/usr/bin/env python3
"""对 case-study 选股逐一拉 dividend, 与 adj_factor 大幅跳变日对照."""
import os, time
import pandas as pd, numpy as np
import tushare as ts

pro = ts.pro_api(os.environ['TUSHARE_TOKEN'])

d = pd.read_parquet('data/combined_daily.parquet', columns=['date','ts_code','adj_factor'])
d = d.sort_values(['ts_code','date'])
d['prev'] = d.groupby('ts_code')['adj_factor'].shift(1)
d['chg'] = d['adj_factor']/d['prev'] - 1
big = d[(d['prev'].notna()) & (np.abs(d['chg'])>0.005)]
cnt = big.groupby('ts_code').size().sort_values(ascending=False)
picks = list(cnt[cnt>=5].index[:24])

rows=[]
for i, tc in enumerate(picks):
    s = d[d.ts_code==tc]
    jumps = s[s['prev'].notna() & (np.abs(s['chg'])>0.005)]
    jump_dates = sorted(set(jumps['date'].astype(str).str[:10].tolist()))
    div = None
    for attempt in range(3):
        try:
            div = pro.dividend(ts_code=tc)
            break
        except Exception as e:
            time.sleep(5)
    if div is None or len(div)==0:
        rows.append(dict(ts_code=tc, n_jumps=len(jump_dates), jump_dates=';'.join(jump_dates), n_div=0, ex_dates=''))
        print(f'{tc}: NO dividend data', flush=True); time.sleep(2); continue
    ex = sorted(div['ex_date'].dropna().astype(str).str[:8].tolist())
    ex_dates = set(ex)
    # 跳变日匹配: adj_factor 跳变日是否在 dividend 的 ex_date 里 (跳变日=Tushare调整日, 可能=ex_date 或相邻)
    matched=0; unmatched=[]
    for jd in jump_dates:
        jd8 = jd.replace('-','')
        # 匹配: ex_date 恰等于跳变日, 或 ex_date 在跳变日 ±3 自然日内
        hit = any(abs((pd.Timestamp(x).date()-pd.Timestamp(jd).date()).days)<=3 for x in ex_dates if len(x)==8)
        if hit: matched+=1
        else: unmatched.append(jd)
    rows.append(dict(ts_code=tc, n_jumps=len(jump_dates), jump_dates=';'.join(jump_dates), n_div=len(ex), matched=matched, unmatched=';'.join(unmatched)))
    print(f'{tc}: jumps={len(jump_dates)} div_exdate={len(ex)} matched={matched} unmatched={unmatched[:40]}', flush=True)
    time.sleep(2)

res = pd.DataFrame(rows)
res.to_csv('results/adjfactor_vs_dividend.csv', index=False)
print('\n=== 汇总 ===')
print(f'选股 {len(res)} | 总跳变 {res.n_jumps.sum()} | 匹配 {res.matched.sum() if "matched" in res else "N/A"}')
