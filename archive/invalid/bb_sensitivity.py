"""布林参数敏感性：period {10,20,30} × std {1.5,2,2.5}，固定 Top10池 + 5层"""
import os, time
import numpy as np
import pandas as pd
import live_backtest as lb

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

t0 = time.time()
print('准备数据...', flush=True)
df = lb.prepare_data()
print(f'数据准备完成 {time.time()-t0:.0f}s', flush=True)

rows = []
# 基准（默认20/2）
eq, tr = lb.run_backtest(df, top_n=10, max_levels=5)
st = lb.calc_stats(eq, tr)
st['配置'] = '基准_20_2'
rows.append(st)
print(f"  基准20/2: 总收益{st['总收益%']}%, 回撤{st['最大回撤%']}%", flush=True)

for period in [10, 20, 30]:
    for std in [1.5, 2, 2.5]:
        if period == 20 and std == 2:
            continue
        g = df.groupby('ts_code')['close_adj']
        ma = g.transform(lambda x, p=period: x.rolling(p, min_periods=p).mean())
        sd = g.transform(lambda x, p=period: x.rolling(p, min_periods=p).std())
        df['ma20'] = ma
        df['std20'] = sd
        df['bb_lower'] = ma - std * sd
        df['bb_upper'] = ma + std * sd
        eq, tr = lb.run_backtest(df, top_n=10, max_levels=5)
        st = lb.calc_stats(eq, tr)
        st['配置'] = f'period{period}_std{std}'
        rows.append(st)
        print(f"  period{period}_std{std}: 总收益{st['总收益%']}%, 回撤{st['最大回撤%']}%, Sharpe{st['Sharpe']}, 交易{st['交易次数']}次", flush=True)

sm = pd.DataFrame(rows)
sm.to_csv(os.path.join(PROJECT_ROOT, 'results', 'bb_sensitivity.csv'), index=False)
print(sm[['配置', '总收益%', '年化收益%', '最大回撤%', 'Sharpe', '交易次数', '胜率%', 'ProfitFactor']].to_string(index=False), flush=True)
print('完成', flush=True)
