"""A-Share Alpha Factory — legacy research import.

把本项目已研究过的内容导入 Alpha Factory 历史知识库（不伪装成新发现）。
统一标 LEGACY_RESEARCH，关联 source_commit / source_report。
breadth 保留为已有有效描述性候选；其余失败项按原审计结论进入 Graveyard。
"""
from __future__ import annotations

import os
from datetime import date

from alpha_factory import registry as R
from alpha_factory import dsl

# source references (本仓库 git 历史中可追踪的提交)
SOURCES = {
    'ee15': 'commit 31f7266b9e978b031e0b685af4876312eb0090d3 (EE15 freeze)',
    'phase1': 'commit 6296cd3 (ML-BB Phase 1, rating B)',
    'phase2': 'commit cc20074 (ML-BB Phase 2, rating C)',
    'earlyexit': 'research/forward/FORWARD_STATUS.md; research/ee15/ (EE15 1.5% freeze)',
}

# 按原审计结论导入。失败项必须进入 Graveyard；baseline/信号定义字段标 ARCHIVED。
LEGACY = [
    # --- baseline / 信号定义（ARCHIVED，非 Alpha 候选） ---
    dict(factor_name='amount_rank_top10', formula='turnover_rank', universe='A',
         family='LIQUIDITY', status='ARCHIVED',
         description='当前 EE15 选股排序用的成交额排名（Top10 候选池）；baseline，不是 Alpha 因子',
         notes='LEGACY_RESEARCH baseline; source=' + SOURCES['ee15']),
    dict(factor_name='bb_z', formula='bb_z', universe='A',
         family='BB_CONDITIONAL', status='ARCHIVED',
         description='BB 下轨信号定义字段（z-score）；信号入口本身，非额外 Alpha',
         notes='LEGACY_RESEARCH signal definition; source=' + SOURCES['ee15']),
    dict(factor_name='distance_to_lower_band', formula='distance_to_lower_band', universe='A',
         family='BB_CONDITIONAL', status='ARCHIVED',
         description='距下轨距离；信号深度描述字段',
         notes='LEGACY_RESEARCH signal definition'),
    # --- breadth（有效描述性候选 → Library VALIDATING） ---
    dict(factor_name='market_breadth', formula='interaction(daily_bb_signal_count,daily_bb_up_ratio)',
         universe='A', family='BREADTH', status='VALIDATING',
         description='市场宽度：当日 BB 信号数量 + 信号日上涨比例；Phase 1 特征重要性名列前茅',
         notes='LEGACY_RESEARCH candidate; source=' + SOURCES['phase1'],
         library=True, library_metrics=dict(IC_mean=None, RankIC_mean=None, ICIR=None,
                                            Q5_Q1_mean=None, Q5_Q1_median=None,
                                            positive_year_ratio=None, OOS_IC=None, OOS_RankIC=None,
                                            robustness_grade='CANDIDATE',
                                            notes='LEGACY_RESEARCH candidate; 待 Alpha Factory 独立验证')),
    # --- 失败项（Graveyard） ---
    dict(factor_name='rsi_filter', formula='ts_zscore(signal_day_close,20) /* RSI 代理 */',
         universe='A', family='TREND', status='FAIL', failure_reason='NO_INCREMENTAL_ALPHA',
         failure_stage='validation', description='RSI 入场过滤：已审计关闭，无增量',
         notes='LEGACY_RESEARCH; 原结论"固定止损、周线BB、RSI/MACD、Squeeze/ADX入场过滤等分支均已关闭"; source=' + SOURCES['ee15']),
    dict(factor_name='macd_filter', formula='diff(signal_day_close,signal_day_close) /* MACD 代理 */',
         universe='A', family='TREND', status='FAIL', failure_reason='NO_INCREMENTAL_ALPHA',
         failure_stage='validation', description='MACD 过滤：已审计关闭',
         notes='LEGACY_RESEARCH; source=' + SOURCES['ee15']),
    dict(factor_name='weekly_bb', formula='bb_z /* 周线版 */', universe='A',
         family='BB_CONDITIONAL', status='FAIL', failure_reason='OOS_FAIL',
         failure_stage='validation', description='周线 BB 均值回归：已关闭',
         notes='LEGACY_RESEARCH; source=' + SOURCES['ee15']),
    dict(factor_name='squeeze_adx_filter', formula='interaction(bb_z,bb_z) /* Squeeze/ADX 代理 */',
         universe='A', family='VOLATILITY', status='FAIL', failure_reason='NO_INCREMENTAL_ALPHA',
         failure_stage='validation', description='Squeeze / ADX 入场过滤：已关闭',
         notes='LEGACY_RESEARCH; source=' + SOURCES['ee15']),
    dict(factor_name='regime_filter', formula='sign(daily_bb_up_ratio) /* regime 代理 */',
         universe='A', family='MARKET_CONTEXT', status='FAIL', failure_reason='REGIME_SPECIFIC',
         failure_stage='validation', description='简单 regime filter：已关闭',
         notes='LEGACY_RESEARCH; source=' + SOURCES['ee15']),
    dict(factor_name='atr_ranking', formula='atr14_pct', universe='A', family='VOLATILITY',
         status='FAIL', failure_reason='DUPLICATE', failure_stage='screening',
         description='ATR 排序：与 amount/随机排序无显著区分（Phase 1 Top-K 重叠）',
         notes='LEGACY_RESEARCH; source=' + SOURCES['phase1']),
    dict(factor_name='bad_classifier', formula='cs_rank(drawdown_20) /* BAD 模型代理 */',
         universe='A', family='BB_CONDITIONAL', status='FAIL',
         failure_reason='NO_INCREMENTAL_ALPHA', failure_stage='portfolio',
         description='坏单分类器：signal 分层存在（BAD 率 22% vs 11-14%），但 Phase 2 组合价值 p=0.24 不显著、2023 反向',
         notes='LEGACY_RESEARCH; Phase 2 评级 C; source=' + SOURCES['phase2']),
    dict(factor_name='addon_ranking', formula='cs_rank(bb_z) /* ADD_ON 排序代理 */',
         universe='A', family='BB_CONDITIONAL', status='FAIL',
         failure_reason='NO_INCREMENTAL_ALPHA', failure_stage='portfolio',
         description='ADD_ON 排序：signal IC 0.21-0.36 但组合仅 3 次资金竞争、单笔净负、p=0.18',
         notes='LEGACY_RESEARCH; Phase 2 评级 C; source=' + SOURCES['phase2']),
]

# 保留但未验证的 HOLD 项（不进 Library/Graveyard，仅 Registry 记录）
HOLD = [
    dict(factor_name='early_exit_1.5pct', formula='sign(distance_to_lower_band) /* 退出规则，非因子 */',
         universe='A', family='BB_CONDITIONAL', status='ARCHIVED',
         description='EE15 提前 1.5% 退出——冻结的退出规则，不属于因子研究；记录防止混淆',
         notes='LEGACY_RESEARCH; 冻结 commit 31f7266b; 禁止作为因子纳入 Alpha Factory'),
    dict(factor_name='monthly_bb', formula='bb_z /* 月线分支 */', universe='A',
         family='BB_CONDITIONAL', status='PROPOSED',
         description='月线 BB 均值回归独立分支（MONTHLY-BB-MR）——状态：独立研究未并入',
         notes='LEGACY_RESEARCH; 独立分支，未冻结，禁止并入 Alpha Factory Phase 0'),
]


def import_legacy() -> dict:
    """执行 legacy 导入。返回 {registered, graveyarded, library} 计数。"""
    reg = R.Registry()
    gy = R.Graveyard()
    lib = R.Library()
    count = {'registered': 0, 'graveyarded': 0, 'library': 0}
    for item in LEGACY:
        formula = item.pop('formula')
        family = item.pop('family')
        universe = item.pop('universe')
        status = item.pop('status')
        library = item.pop('library', False)
        library_metrics = item.pop('library_metrics', None)
        desc = item.pop('description', '')
        notes = item.pop('notes', '')
        # expression hash only for parseable formulas
        eh = None
        try:
            eh = dsl.expression_hash(formula)
        except Exception:
            eh = None
        row = dict(
            factor_name=item['factor_name'], factor_family=family, formula=formula,
            description=desc, economic_hypothesis=item.get('economic_hypothesis'),
            universe=universe, input_fields=None, lookback=None, operators=None,
            PIT_status='LEGACY_PIT_REVIEWED', max_source_lag=None, missing_policy='dropna',
            winsorization='none', normalization='none', expression_hash=eh,
            complexity_depth=None, complexity_inputs=None, complexity_interactions=None,
            created_date=date.today().isoformat(),
            created_by='legacy_import', experiment_id='LEGACY_RESEARCH',
            discovery_period='2020-2022', validation_period='2023', test_period='2024',
            status=status, notes=notes,
        )
        # 避免重复导入
        if eh and len(reg.df[(reg.df['expression_hash'] == eh) & (reg.df['universe'] == universe)]):
            continue
        row['factor_id'] = R.next_factor_id(reg.df)
        reg.add(**row)
        count['registered'] += 1
        if status == 'FAIL':
            gy.bury(factor_id=row['factor_id'], factor_name=row['factor_name'],
                    formula=formula, failure_stage=item.get('failure_stage', 'validation'),
                    failure_reason=item.get('failure_reason', 'NO_SIGNAL'),
                    discovery_metric=None, validation_metric=None, test_metric=None,
                    yearly_direction=None, correlation_with_existing=None,
                    duplicate_of=item.get('duplicate_of'), leakage_detected=False,
                    notes=notes)
            count['graveyarded'] += 1
        if library and library_metrics:
            lib.approve(factor_id=row['factor_id'], factor_name=row['factor_name'],
                        formula=formula, **library_metrics)
            count['library'] += 1
    for item in HOLD:
        formula = item.pop('formula')
        family = item.pop('family')
        universe = item.pop('universe')
        status = item.pop('status')
        desc = item.pop('description', '')
        notes = item.pop('notes', '')
        row = dict(factor_name=item['factor_name'], factor_family=family, formula=formula,
                   description=desc, universe=universe, PIT_status='LEGACY_PIT_REVIEWED',
                   created_by='legacy_import', experiment_id='LEGACY_RESEARCH',
                   discovery_period='2020-2022', validation_period='2023', test_period='2024',
                   status=status, notes=notes)
        row['factor_id'] = R.next_factor_id(reg.df)
        reg.add(**row)
        count['registered'] += 1
    return count


def write_legacy_mapping() -> str:
    """Write a CSV mapping of legacy entries to factor_ids."""
    import pandas as pd
    reg = R.Registry()
    m = reg.df[reg.df['experiment_id'] == 'LEGACY_RESEARCH']
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), 'research', 'alpha_factory',
        'LEGACY_IMPORT.csv')
    m[['factor_id', 'factor_name', 'status', 'formula', 'notes']].to_csv(path, index=False)
    return path
