"""STRICT_C 数学验证: 动态 Bollinger 上轨临界价 P*
Upper(P) = mean(x1..x19, P) + 2*sample_std(x1..x19, P), ddof=1
求 P*: P* = Upper(P*)
"""
import sys, os
import numpy as np

ROOT = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat'
sys.path.insert(0, ROOT)

def mean19(x): return x.sum() / 20.0

def upper(P, x):
    """Upper(P), x = 前19个收盘价 (len 19)"""
    P = np.asarray(P, dtype=float)
    x = np.asarray(x, dtype=float)
    S = x.sum(); T = (x ** 2).sum()
    m = (S + P) / 20.0
    # sample_std ddof=1
    ss = np.maximum(0.0, T + P * P - 20.0 * m * m)
    sd = np.sqrt(ss / 19.0)
    return m + 2.0 * sd

def g(P, x):
    return P - upper(P, x)

def analytic_Pstar(x):
    """解析解: 5339 P^2 - 562 S P + (99 S^2 - 1600 T) = 0, 较大根且 P>=S/19
    推导: SS(P)=(19/20)P^2-(1/10)SP+T-(1/20)S^2; 19(19P-S)^2=1600*SS"""
    S = x.sum(); T = (x ** 2).sum()
    a, b, c = 5339.0, -562.0 * S, 99.0 * S * S - 1600.0 * T
    disc = b * b - 4.0 * a * c
    if disc < 0:
        return None
    sq = np.sqrt(disc)
    p1 = (-b + sq) / (2.0 * a)
    p2 = (-b - sq) / (2.0 * a)
    S19 = S / 19.0
    cand = [p for p in (p1, p2) if p >= S19 - 1e-9]
    if not cand:
        return None
    return max(cand)

def numeric_Pstar(x):
    """数值解: brentq 求 g(P)=0 在 [0, 50*max(x)] 区间"""
    from scipy.optimize import brentq
    lo = 0.0
    hi = 50.0 * max(x)
    gl = g(lo, x); gh = g(hi, x)
    if gl * gh > 0:
        # 扩大上界
        for f in (100, 200, 500, 1000):
            hi = f * max(x)
            gh = g(hi, x)
            if gl * gh <= 0:
                break
        if gl * gh > 0:
            return None
    return brentq(g, lo, hi, args=(x,), xtol=1e-12, rtol=1e-12)

def check_region(x, Pstar):
    """验证 g(P) 在 (0,P*) <0, 在 (P*, 4P*) >0, P* > 0"""
    if Pstar is None:
        return ('NO_ROOT', 0, 0, 0)
    if Pstar <= 0:
        return ('PSTAR_LE_0', Pstar, 0, 0)
    # 左区间抽样 (不包括0, 用 max(x)*1e-6 下界)
    loP = max(1e-12, Pstar * 1e-6)
    pts_l = np.linspace(loP, Pstar * 0.999, 200)
    gl = np.array([g(p, x) for p in pts_l])
    if (gl >= 0).any():
        # 找到正零点: 说明左区间有根
        idx = np.where(gl >= 0)[0][0]
        return ('EXTRA_ROOT_LEFT', Pstar, pts_l[idx], gl[idx])
    pts_r = np.linspace(Pstar * 1.001, 4.0 * Pstar, 200)
    gr = np.array([g(p, x) for p in pts_r])
    if (gr <= 0).any():
        idx = np.where(gr <= 0)[0][0]
        return ('EXTRA_ROOT_RIGHT', Pstar, pts_r[idx], gr[idx])
    # 远右侧: 确认无第二根 (线性上升域)
    pts_far = np.linspace(Pstar * 4.0, 50.0 * Pstar, 200)
    gf = np.array([g(p, x) for p in pts_far])
    if (gf <= 0).any():
        idx = np.where(gf <= 0)[0][0]
        return ('EXTRA_ROOT_FAR', Pstar, pts_far[idx], gf[idx])
    return ('OK', Pstar, 0, 0)

if __name__ == '__main__':
    # ---------- 1) 简单解析验证 ----------
    # 全相等窗口: P* = c
    for c in (1.0, 10.0, 25.7):
        x = np.full(19, c)
        pa = analytic_Pstar(x); pn = numeric_Pstar(x)
        print(f'全相等 c={c}: analytic={pa:.10f} numeric={pn:.10f} (理论={c})')

    # ---------- 2) 1000+ 真实窗口 ----------
    df = pd_read = None
    import pandas as pd
    df = pd.read_parquet(os.path.join(ROOT, 'data', 'combined_daily.parquet'))
    df = df[df['date'] >= '2020-01-01']
    df = df.sort_values(['ts_code', 'date'])
    rng = np.random.default_rng(42)
    codes = df['ts_code'].unique()
    max_err = 0.0; n_ok = 0; n_bad = 0; issues = []
    n_win = 0
    while n_win < 1000 and n_bad < 5:
        tc = rng.choice(codes)
        sub = df[df['ts_code'] == tc]['close'].to_numpy()
        if len(sub) < 20:
            continue
        i = rng.integers(0, len(sub) - 20)
        x = sub[i:i + 19].astype(float)
        if np.any(x <= 0) or x.std() < 1e-9:
            continue
        n_win += 1
        pa = analytic_Pstar(x); pn = numeric_Pstar(x)
        if pa is None or pn is None:
            n_bad += 1; issues.append((tc, i, 'NO_ROOT'))
            continue
        err = abs(pa - pn)
        max_err = max(max_err, err)
        status, Pstar, xp, gp = check_region(x, pa)
        if status == 'OK' and err < 1e-6:
            n_ok += 1
        else:
            n_bad += 1
            issues.append((tc, i, status, err))
    print(f'\n[1000窗口验证] ok={n_ok} bad={n_bad} max|analytic-numeric|={max_err:.3e}')
    print(f'issues样本: {issues[:5]}')
    print('\n[解析公式] 5339*P^2 - 562*S*P + (99*S^2 - 1600*T) = 0, P*=较大根且P>=S/19')
    print('[结论] P* = Upper(P*), 且 g(P)=P-Upper(P) 在 (0,P*) 恒<0, (P*,4P*) 恒>0 => high>=P* 等价于盘中曾触碰动态上轨')
