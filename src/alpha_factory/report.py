"""A-Share Alpha Factory — automatic experiment report.

每次 Experiment 必须同时报告：尝试数、通过数、失败数、重复数、leakage 数、
FDR 通过数、OOS 通过数、KEEP 数、Top factors、Graveyard additions、
以及累计 hypothesis attempts（多口径）。禁止只展示赢家。

Phase 0.1 计数口径（与 registry.MultipleTestingLedger.summary 一致）：
TOTAL_REQUEST_ATTEMPTS / TOTAL_UNIQUE_EXPRESSIONS / TOTAL_COMPUTED_HYPOTHESES /
TOTAL_DUPLICATE_REQUESTS / TOTAL_REJECTED_COMPLEXITY / TOTAL_REJECTED_LEAKAGE /
TOTAL_REJECTED_LOOKBACK / TOTAL_REJECTED_INPUT / TOTAL_REJECTED_SYNTAX。
"""
from __future__ import annotations

import json
import os

import pandas as pd

from alpha_factory import registry as R


def write_report(experiment_id: str, out_dir: str, sections: dict) -> str:
    """Write an experiment report JSON + human-readable MD into out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    path_json = os.path.join(out_dir, f'{experiment_id}_report.json')
    path_md = os.path.join(out_dir, f'{experiment_id}_report.md')
    with open(path_json, 'w', encoding='utf-8') as f:
        json.dump(sections, f, ensure_ascii=False, indent=2, default=str)
    lines = [f'# Experiment {experiment_id}', '']
    for k, v in sections.items():
        lines.append(f'## {k}')
        if isinstance(v, (dict, list)):
            lines.append('```json')
            lines.append(json.dumps(v, ensure_ascii=False, indent=2, default=str))
            lines.append('```')
        else:
            lines.append(str(v))
        lines.append('')
    with open(path_md, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return path_md


def attempt_summary() -> dict:
    """全库 hypothesis attempts 多口径汇总。"""
    mt = R.MultipleTestingLedger()
    return mt.summary()


def tally(experiment_id: str, factor_ids: list[str],
          status_map: dict[str, str]) -> dict:
    """Tally factor outcomes for a report + 全库 attempt 多口径。"""
    reg = R.Registry()
    counts = {'proposed': 0, 'tested': 0, 'duplicate': 0, 'leakage': 0,
              'fdr_passed': 0, 'oos_passed': 0, 'keep': 0, 'fail': 0, 'archived': 0}
    for fid in factor_ids:
        try:
            st = status_map.get(fid) or reg.get(fid)['status']
        except KeyError:
            st = 'UNKNOWN'
        if st == 'PROPOSED':
            counts['proposed'] += 1
        elif st == 'SCREENING':
            counts['tested'] += 1
        elif st == 'DUPLICATE':
            counts['duplicate'] += 1
        elif st == 'LEAKAGE':
            counts['leakage'] += 1
        elif st == 'KEEP':
            counts['keep'] += 1
        elif st == 'FAIL':
            counts['fail'] += 1
        elif st == 'ARCHIVED':
            counts['archived'] += 1
    counts['total_attempts_this_experiment'] = len(factor_ids)
    counts.update(attempt_summary())
    return counts
