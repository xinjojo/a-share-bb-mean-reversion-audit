"""Universe B — performance benchmark (Phase 0).
实测：读 1 月 / 1 年 / 5 年 panel + features 的时间与峰值内存。
结论决定 Phase 1 引擎选择（Pandas / Polars / DuckDB）。
"""
import os
import resource
import time
import pandas as pd

REPO = '/Users/mouha/DoubaoWork/chats/2026-08-25/new-chat/audit_package/github_repo'
UB = os.path.join(REPO, 'results/evidence/alpha_factory/universe_b')


def _peak_rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # macOS 单位 KB -> MB


def bench_read(part, label):
    t0 = time.time()
    files = []
    root = os.path.join(UB, part)
    for r, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.parquet') and (label == 'all' or label in r):
                files.append(os.path.join(r, f))
    if label == 'all':
        files = [os.path.join(root_, f) for root_, _, fs in os.walk(root)
                 for f in fs if f.endswith('.parquet')]
    t1 = time.time()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    t2 = time.time()
    return {'part': part, 'scope': label, 'rows': len(df),
            'cols': df.shape[1], 'discover_s': round(t1 - t0, 2),
            'read_s': round(t2 - t1, 2), 'peak_rss_mb': round(_peak_rss_mb(), 0)}


def bench():
    out = []
    # panel: 1 月 / 1 年 / 全
    for label in ['year=2020', 'all']:
        out.append(bench_read('panel', label))
    # features: 1 年 / 全
    for label in ['year=2020', 'all']:
        out.append(bench_read('features', label))
    # labels: 全
    out.append(bench_read('labels', 'all'))
    b = pd.DataFrame(out)
    b.to_csv(os.path.join(UB, 'BENCHMARK.csv'), index=False)
    md = ['# UNIVERSE B — BENCHMARK (M2 Pro / 10 核 / 16GB RAM)', '',
          b.to_markdown(index=False), '',
          '说明：Pandas 并行读取 parquet（pyarrow）；peak_rss 为进程峰值常驻内存。',
          '结论：若全量 ~6.5M 行×80 列可在 30s 内读入、峰值 <8GB，则 Pandas 足够 Phase 1；'
          '若 >60s 或内存吃紧，转 Polars（惰性计算）或 DuckDB（SQL 下推）。']
    with open(os.path.join(UB, 'BENCHMARK.md'), 'w') as f:
        f.write('\n'.join(md))
    print(b.to_string(index=False))
    return b


if __name__ == '__main__':
    bench()
