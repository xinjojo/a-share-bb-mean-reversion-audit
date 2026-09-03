#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R0-A: build REPO_INVENTORY.csv for a-share-bb-mean-reversion-audit.
Classification rules are hard-coded here (manual knowledge of the research chain).
Run from repo root: python3 tools/r0_build_inventory.py
"""
import subprocess, csv, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()

# (phase, category, status, canonical, superseded_by, evidence_level, recommended_destination, notes)
TOP_MD = {
 "README.md":                          ("governance","doc","ACTIVE","FALSE","","infra","README.md","entry point - rewrite in R0-C"),
 "CURRENT_STATUS.md":                  ("governance","doc","ACTIVE","FALSE","","infra","CURRENT_STATUS.md","phase R0-C - current truth"),
 "RESEARCH_MAP.md":                    ("governance","doc","ACTIVE","FALSE","","infra","RESEARCH_MAP.md","phase R0-C - research chain"),
 "REPO_INVENTORY.csv":                 ("governance","doc","ACTIVE","FALSE","","infra","REPO_INVENTORY.csv","phase R0-A"),
 "MIGRATION_MAP.csv":                  ("governance","doc","ACTIVE","FALSE","","infra","MIGRATION_MAP.csv","phase R0-B"),
 "REMOTE_VERIFICATION.md":             ("governance","doc","ACTIVE","FALSE","","infra","REMOTE_VERIFICATION.md","phase R0 - remote push verification"),
 "RESULTS_LATEST.md":                  ("original","report","INVALID","FALSE","","invalid","archive/invalid/RESULTS_LATEST.md","pre-lookahead result summary; superseded by STRICT_C chain"),
 "AUDIT_GUIDE.md":                     ("governance","doc","INFRASTRUCTURE","FALSE","","infra","docs/AUDIT_GUIDE.md","how to audit the repo"),
 "AUDIT_REQUESTS.md":                  ("governance","doc","INFRASTRUCTURE","FALSE","","infra","docs/AUDIT_REQUESTS.md","external audit request log"),
 "BACKTEST_INVARIANTS.md":             ("governance","doc","INFRASTRUCTURE","FALSE","","infra","docs/BACKTEST_INVARIANTS.md","engine invariants / parity contract"),
 "CALLCHAIN.md":                       ("governance","doc","INFRASTRUCTURE","FALSE","","infra","docs/CALLCHAIN.md","engine call-chain description"),
 "TRADING_SYSTEM_STEPBYSTEP.md":       ("governance","doc","INFRASTRUCTURE","FALSE","","infra","docs/TRADING_SYSTEM_STEPBYSTEP.md","original system description (historical)"),
 "KLINE_DATA.md":                      ("governance","doc","INFRASTRUCTURE","FALSE","","infra","data_docs/KLINE_DATA.md","kline data format / provenance"),
 "THIRD_PARTY_AUDIT_BRIEF.md":         ("governance","doc","INFRASTRUCTURE","FALSE","","infra","docs/THIRD_PARTY_AUDIT_BRIEF.md","brief for third-party auditor"),
 "THIRD_PARTY_CLAIM_CHECK_ADJ_FACTOR.md":      ("redteam","report","SUPERSEDED","FALSE","THIRD_PARTY_CLAIM_CHECK_ADJ_FACTOR_V2.md","secondary","archive/superseded/THIRD_PARTY_CLAIM_CHECK_ADJ_FACTOR.md","superseded by V2"),
 "THIRD_PARTY_CLAIM_CHECK_ADJ_FACTOR_V2.md":   ("redteam","report","ACCEPTED","FALSE","","primary","research/signal/THIRD_PARTY_CLAIM_CHECK_ADJ_FACTOR_V2.md","adj-factor claim check v2"),
 "REDTEAM_STRICT_C.md":                ("strict_c","report","SUPERSEDED","FALSE","REDTEAM_STRICT_C_CORRECTED.md","primary","archive/superseded/REDTEAM_STRICT_C.md","superseded by corrected"),
 "REDTEAM_STRICT_C_CORRECTED.md":      ("strict_c","report","ACCEPTED","FALSE","","primary","research/signal/REDTEAM_STRICT_C_CORRECTED.md","STRICT_C semantics audit (corrected)"),
 "REDTEAM_ROUND51_STRICT.md":          ("strict_c","report","ACCEPTED","TRUE","","primary","research/signal/REDTEAM_ROUND51_STRICT.md","CANONICAL STRICT_C frozen-engine report"),
 "REDTEAM_ROUND5_STRICT.md":           ("redteam","report","SUPERSEDED","FALSE","REDTEAM_ROUND51_STRICT.md","secondary","archive/superseded/REDTEAM_ROUND5_STRICT.md","superseded by round51"),
 "REDTEAM_ROUND2_EXPERIMENTS.md":      ("redteam","report","SUPERSEDED","FALSE","","secondary","archive/superseded/REDTEAM_ROUND2_EXPERIMENTS.md","early redteam round"),
 "REDTEAM_ROUND3_ALPHA.md":            ("redteam","report","SUPERSEDED","FALSE","","secondary","archive/superseded/REDTEAM_ROUND3_ALPHA.md","early redteam round"),
 "REDTEAM_ROUND4_READINESS.md":        ("redteam","report","SUPERSEDED","FALSE","","secondary","archive/superseded/REDTEAM_ROUND4_READINESS.md","early redteam round"),
 "REDTEAM_AUDIT_REPLY.md":             ("redteam","report","SUPERSEDED","FALSE","","secondary","archive/superseded/REDTEAM_AUDIT_REPLY.md","early reply doc"),
 "INDEPENDENT_TRADE_REPLAY.md":        ("independent","report","SUPERSEDED","FALSE","INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md","primary","archive/superseded/INDEPENDENT_TRADE_REPLAY.md","replay V1"),
 "INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md":("independent","report","ACCEPTED","TRUE","","primary","research/signal/INDEPENDENT_TRADE_REPLAY_V2_AUDIT.md","CANONICAL independent replay V2 audit"),
 "TRADE_PATH_QUALITY_AUDIT.md":        ("tradepath","report","SUPERSEDED","FALSE","FULL_MARKET_TRADE_PATH_AUDIT.md","primary","archive/superseded/TRADE_PATH_QUALITY_AUDIT.md","primary-only path audit; superseded by full-market"),
 "FULL_MARKET_TRADE_PATH_AUDIT.md":    ("fullmarket","report","ACCEPTED","TRUE","","primary","research/trade_path/FULL_MARKET_TRADE_PATH_AUDIT.md","CANONICAL full-market trade-path audit"),
 "STOP_LOSS_COUNTERFACTUAL_PHASE_A.md":("stopA","report","CLOSED","TRUE","","primary","research/execution/STOP_LOSS_COUNTERFACTUAL_PHASE_A.md","CANONICAL stop phase A; verdict C NO USEFUL STOP; semantics issue NOT formally closed (not ACCEPTED)"),
 "TEMPORAL_CLUSTERING_PHASE_T1.md":    ("temporal","report","ACCEPTED","TRUE","","primary","research/market_state/TEMPORAL_CLUSTERING_PHASE_T1.md","CANONICAL T1; A STRONG CLUSTERING"),
 "MARKET_STATE_PHASE_T2.md":           ("marketstate","report","ACCEPTED","TRUE","","primary","research/market_state/MARKET_STATE_PHASE_T2.md","CANONICAL T2 discovery (reverse-direction)"),
 "MARKET_STATE_REVERSE_VALIDATION.md": ("marketstate","report","ACCEPTED","TRUE","","primary","research/market_state/MARKET_STATE_REVERSE_VALIDATION.md","CANONICAL T2-R; A STRONG VALIDATION"),
 "MARKET_STATE_GATE_T3.md":            ("gateT3","report","CLOSED","TRUE","","primary","research/market_state/MARKET_STATE_GATE_T3.md","CANONICAL T3; C NO USEFUL PORTFOLIO GATE (closed)"),
 "PATH_DEPENDENCE_ATTRIBUTION.md":     ("gateT3","report","SUPERSEDED","FALSE","MARKET_STATE_GATE_T3.md","secondary","archive/superseded/PATH_DEPENDENCE_ATTRIBUTION.md","early T3 path attribution; superseded by gate T3 report"),
 "T3_R05_BASIS_CLARIFICATION.md":      ("gateT3","report","ACCEPTED","FALSE","","secondary","research/market_state/T3_R05_BASIS_CLARIFICATION.md","R05 cutpoint-basis clarification (does not change T3 C)"),
 "CROSS_SECTIONAL_RANKING_P1.md":      ("ranking","report","SUPERSEDED","FALSE","CROSS_SECTIONAL_RANKING_P1_CORRECTED.md","primary","archive/superseded/CROSS_SECTIONAL_RANKING_P1.md","P1 pre-correction"),
 "CROSS_SECTIONAL_RANKING_P1_CORRECTED.md":("ranking","report","ACCEPTED","TRUE","","primary","research/ranking/CROSS_SECTIONAL_RANKING_P1_CORRECTED.md","CANONICAL P1.1; A DISCOVERY ROBUST"),
 "P1_RELATIVE_RETURN_INVARIANCE_NOTE.md":("ranking","report","ACCEPTED","FALSE","","secondary","research/ranking/P1_RELATIVE_RETURN_INVARIANCE_NOTE.md","REL_RET rank-invariance method note"),
 "CROSS_SECTIONAL_RANKING_P2_VALIDATION.md":("p2val","report","ACCEPTED","TRUE","","primary","research/ranking/CROSS_SECTIONAL_RANKING_P2_VALIDATION.md","CANONICAL P2; B PARTIAL VALIDATION (ATR20_PCT only)"),
 "ATR_SLOT_ALLOCATION_P3.md":          ("p3","report","CLOSED","TRUE","","primary","research/portfolio/ATR_SLOT_ALLOCATION_P3.md","CANONICAL P3; C NO USEFUL PORTFOLIO RANKING (closed)"),
 "P3_FUTURE_CONFIRMATION_RULE.md":     ("p3","report","ACCEPTED","FALSE","","secondary","research/portfolio/P3_FUTURE_CONFIRMATION_RULE.md","pre-frozen 2025-26 confirmation rule"),
 "SLOT_CONTENTION_PATH_AUDIT.md":      ("p31","report","ACCEPTED","TRUE","","primary","research/portfolio/SLOT_CONTENTION_PATH_AUDIT.md","CANONICAL P3.1; C BOTH (diagnostic)"),
 "P3_MECHANISM_CORRECTION_NOTE.md":    ("p31","report","ACCEPTED","FALSE","","secondary","research/portfolio/P3_MECHANISM_CORRECTION_NOTE.md","P3 doc label-error correction note"),
 "SLIPPAGE_PATH_DISCONTINUITY_AUDIT.md":("p31","report","ACCEPTED","FALSE","","secondary","research/portfolio/SLIPPAGE_PATH_DISCONTINUITY_AUDIT.md","10/20/50bp path-discontinuity audit"),
 "REGIME_RESEARCH_PLAN.md":            ("redteam","doc","SUPERSEDED","FALSE","","secondary","archive/superseded/REGIME_RESEARCH_PLAN.md","old regime research plan"),
 "REGIME_DISCOVERY_PHASE1.md":         ("redteam","report","SUPERSEDED","FALSE","REGIME_DISCOVERY_PHASE1_CORRECTED.md","secondary","archive/superseded/REGIME_DISCOVERY_PHASE1.md","old regime discovery v1"),
 "REGIME_DISCOVERY_PHASE1_CORRECTED.md":("redteam","report","SUPERSEDED","FALSE","REGIME_DISCOVERY_PHASE1_V3.md","secondary","archive/superseded/REGIME_DISCOVERY_PHASE1_CORRECTED.md","old regime discovery v2"),
 "REGIME_DISCOVERY_PHASE1_V3.md":      ("redteam","report","SUPERSEDED","FALSE","MARKET_STATE_PHASE_T2.md","secondary","archive/superseded/REGIME_DISCOVERY_PHASE1_V3.md","old regime discovery v3; replaced by T2 branch"),
 "REGIME_PHASE1_AUDIT_PACKET.md":      ("redteam","report","SUPERSEDED","FALSE","","secondary","archive/superseded/REGIME_PHASE1_AUDIT_PACKET.md","old regime audit packet"),
 "REGIME_PHASE1_METHODOLOGY_CLARIFICATION.md":("redteam","report","SUPERSEDED","FALSE","","secondary","archive/superseded/REGIME_PHASE1_METHODOLOGY_CLARIFICATION.md","old regime methodology note"),
}

TOP_REG = {
 "ATR_SLOT_ALLOCATION_REGISTRY.csv":   ("p3","registry","ACCEPTED","FALSE","","primary","research/portfolio/registries/ATR_SLOT_ALLOCATION_REGISTRY.csv","preregistration; committed before P3 portfolio runs"),
 "ATR_SLOT_ALLOCATION_REGISTRY.sha256":("p3","registry","ACCEPTED","FALSE","","primary","research/portfolio/registries/ATR_SLOT_ALLOCATION_REGISTRY.sha256","registry hash"),
 "CROSS_SECTIONAL_RANKING_REGISTRY.csv":("ranking","registry","ACCEPTED","FALSE","","primary","research/ranking/registries/CROSS_SECTIONAL_RANKING_REGISTRY.csv","P1 registry 9c36887"),
 "CROSS_SECTIONAL_RANKING_REGISTRY.sha256":("ranking","registry","ACCEPTED","FALSE","","primary","research/ranking/registries/CROSS_SECTIONAL_RANKING_REGISTRY.sha256","P1 registry hash"),
 "CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.csv":("p2val","registry","ACCEPTED","FALSE","","primary","research/ranking/registries/CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.csv","P2 validation registry"),
 "CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.sha256":("p2val","registry","ACCEPTED","FALSE","","primary","research/ranking/registries/CROSS_SECTIONAL_RANKING_VALIDATION_REGISTRY.sha256","P2 registry hash"),
 "HYPOTHESIS_REGISTRY.csv":            ("redteam","registry","CLOSED","FALSE","","primary","archive/superseded/HYPOTHESIS_REGISTRY.csv","old 104-cell regime registry; frozen, not modified"),
 "HYPOTHESIS_REGISTRY_TEMPLATE.csv":   ("redteam","registry","SUPERSEDED","FALSE","","secondary","archive/superseded/HYPOTHESIS_REGISTRY_TEMPLATE.csv","registry template"),
 "MARKET_STATE_GATE_REGISTRY.csv":     ("gateT3","registry","ACCEPTED","FALSE","","primary","research/market_state/registries/MARKET_STATE_GATE_REGISTRY.csv","T3 gate registry"),
 "MARKET_STATE_GATE_REGISTRY.sha256":  ("gateT3","registry","ACCEPTED","FALSE","","primary","research/market_state/registries/MARKET_STATE_GATE_REGISTRY.sha256","T3 registry hash"),
 "TEMPORAL_STATE_FEATURE_REGISTRY.csv":("marketstate","registry","ACCEPTED","FALSE","","primary","research/market_state/registries/TEMPORAL_STATE_FEATURE_REGISTRY.csv","T2 preregistered 27 features"),
 "TEMPORAL_STATE_FEATURE_REGISTRY.sha256":("marketstate","registry","ACCEPTED","FALSE","","primary","research/market_state/registries/TEMPORAL_STATE_FEATURE_REGISTRY.sha256","T2 registry hash"),
 "TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.csv":("marketstate","registry","ACCEPTED","FALSE","","primary","research/market_state/registries/TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.csv","T2-R reverse registry (7 vars)"),
 "TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.sha256":("marketstate","registry","ACCEPTED","FALSE","","primary","research/market_state/registries/TEMPORAL_STATE_REVERSE_VALIDATION_REGISTRY.sha256","T2-R registry hash"),
 "R01_DISCOVERY_CUTPOINTS.json":       ("gateT3","config","ACCEPTED","FALSE","","primary","research/market_state/R01_DISCOVERY_CUTPOINTS.json","frozen R01 (ALL_A_EW_RET60) Discovery quintile cutpoints"),
 "R05_DISCOVERY_CUTPOINTS.json":       ("gateT3","config","ACCEPTED","FALSE","","primary","research/market_state/R05_DISCOVERY_CUTPOINTS.json","frozen R05 (LIMIT_DOWN_SHARE) Discovery cutpoints"),
}

TOP_PY = {
 "strategy_optimized.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/strategy_optimized.py","original strategy (lookahead)"),
 "strategy_improved.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/strategy_improved.py","original strategy variant"),
 "strategy_multi_pool.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/strategy_multi_pool.py","original multi-pool variant"),
 "strategy_multi_tp.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/strategy_multi_tp.py","original multi-TP variant"),
 "strategy_bearish_exit.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/strategy_bearish_exit.py","original bearish-exit variant"),
 "strategy_v8_multi.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/strategy_v8_multi.py","original v8 multi"),
 "strategy_v8_multi_combined.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/strategy_v8_multi_combined.py","original v8 combined"),
 "strategy_v8_multi_fast.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/strategy_v8_multi_fast.py","original v8 fast"),
 "live_backtest.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/live_backtest.py","original live backtest"),
 "live_backtest_r2.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/live_backtest_r2.py","original r2 live backtest"),
 "revised_backtest.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/revised_backtest.py","original revised backtest"),
 "revised_plot.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/revised_plot.py","plot helper"),
 "revised_signal_analysis.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/revised_signal_analysis.py","original signal analysis"),
 "experiment_fast.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/experiment_fast.py","early experiment"),
 "multi_backtest.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/multi_backtest.py","original multi backtest"),
 "multi_analyze.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/multi_analyze.py","original analyzer"),
 "pool_analyze.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/pool_analyze.py","original pool analyzer"),
 "scan_pool.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/scan_pool.py","original pool scan"),
 "walk_forward.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/walk_forward.py","original walk-forward (optimistic)"),
 "stress_test_v2.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/stress_test_v2.py","original stress test"),
 "top10_selection.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/top10_selection.py","original Top10 selection"),
 "test_multi3.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/test_multi3.py","original test"),
 "test_timestop.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/test_timestop.py","original time-stop experiment"),
 "test_vbt_multi3.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/test_vbt_multi3.py","original vbt test"),
 "test_vbt_quick.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/test_vbt_quick.py","original vbt test"),
 "etf_live_backtest.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/etf_live_backtest.py","original ETF live backtest"),
 "etf_plot.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/etf_plot.py","ETF plot helper"),
 "etf_ratio_scan.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/etf_ratio_scan.py","ETF ratio scan"),
 "download_warmup.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/download_warmup.py","original warmup"),
 "signal_frequency.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/signal_frequency.py","original signal freq"),
 "bb_sensitivity.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/bb_sensitivity.py","BB param sensitivity (original)"),
 "bb_stop_grid.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/bb_stop_grid.py","stop grid on original system (optimization, not evidence)"),
 "bb_levels_comparison.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/bb_levels_comparison.py","levels comparison (original)"),
 "bb_lower_upper_full_market.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/bb_lower_upper_full_market.py","BB lower/upper scan"),
 "analyze_trade_features.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/analyze_trade_features.py","original feature analysis"),
 "analyze_volume_signal.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/analyze_volume_signal.py","volume-signal analysis"),
 "analyze_shrink_signal.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/analyze_shrink_signal.py","shrink-signal analysis"),
 "analyze_levels_comparison.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/analyze_levels_comparison.py","levels comparison analysis"),
 "analyze_features_large.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/analyze_features_large.py","large feature analysis"),
 "analyze_drawdown_postexit.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/analyze_drawdown_postexit.py","post-exit drawdown analysis (original)"),
 "live_analyze_r2.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/live_analyze_r2.py","r2 analyzer"),
 "live_plot.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/live_plot.py","plot helper"),
 "level1_tight_stop.py":("original","script","INVALID","FALSE","","invalid","archive/invalid/level1_tight_stop.py","tight-stop experiment (original)"),
 "stop_loss_sensitivity.py":("stopA","script","CLOSED","FALSE","","secondary","research/execution/stop_loss_sensitivity.py","stop sensitivity helper (pre-counterfactual)"),
 "semantic_touch.py":("strict_c","script","ACCEPTED","FALSE","","secondary","src/semantic_touch.py","semantic touch test for STRICT_C"),
 "run_strict_c.py":("strict_c","script","ACCEPTED","FALSE","","primary","src/run_strict_c.py","STRICT_C runner (canonical engine entry)"),
 "run_strict_c_math.py":("strict_c","script","ACCEPTED","FALSE","","secondary","src/run_strict_c_math.py","STRICT_C math verification"),
 "strict_c_corrected.py":("strict_c","script","ACCEPTED","FALSE","","primary","src/strict_c_corrected.py","STRICT_C corrected semantics"),
 "strict_c_attribution.py":("strict_c","script","ACCEPTED","FALSE","","secondary","src/strict_c_attribution.py","STRICT_C attribution"),
 "full_market_v8.py":("fullmarket","script","ACCEPTED","FALSE","","secondary","research/trade_path/full_market_v8.py","full-market scan v8 (secondary universe build)"),
 "full_market_scan.py":("fullmarket","script","ACCEPTED","FALSE","","secondary","research/trade_path/full_market_scan.py","full-market eligible scan"),
 "full_market_trade_path_audit.py":("fullmarket","script","ACCEPTED","FALSE","","primary","research/trade_path/full_market_trade_path_audit.py","full-market trade-path audit"),
 "trade_path_quality_audit.py":("tradepath","script","SUPERSEDED","FALSE","full_market_trade_path_audit.py","secondary","archive/superseded/trade_path_quality_audit.py","primary-only path quality audit"),
 "trade_max_drawdown.py":("tradepath","script","SUPERSEDED","FALSE","full_market_trade_path_audit.py","secondary","archive/superseded/trade_max_drawdown.py","max drawdown audit"),
 "independent_trade_replay.py":("independent","script","SUPERSEDED","FALSE","independent_trade_replay_v2.py","secondary","archive/superseded/independent_trade_replay.py","replay V1"),
 "independent_trade_replay_v2.py":("independent","script","ACCEPTED","FALSE","","primary","research/signal/independent_trade_replay_v2.py","replay V2 (canonical)"),
 "independent_trade_stats.py":("independent","script","ACCEPTED","FALSE","","secondary","research/signal/independent_trade_stats.py","replay stats"),
 "export_trade_details.py":("independent","script","ACCEPTED","FALSE","","secondary","research/signal/export_trade_details.py","trade detail export"),
 "stop_loss_counterfactual_phase_a.py":("stopA","script","CLOSED","FALSE","","primary","research/execution/stop_loss_counterfactual_phase_a.py","stop counterfactual Phase A"),
 "temporal_clustering_phase_t1.py":("temporal","script","ACCEPTED","FALSE","","primary","research/market_state/temporal_clustering_phase_t1.py","T1 temporal clustering"),
 "market_state_phase_t2.py":("marketstate","script","ACCEPTED","FALSE","","primary","research/market_state/market_state_phase_t2.py","T2 market-state discovery"),
 "STEP_A_PREREGISTER.py":("marketstate","script","ACCEPTED","FALSE","","primary","research/market_state/STEP_A_PREREGISTER.py","T2 preregistration step"),
 "STEP_B_VALIDATE.py":("marketstate","script","ACCEPTED","FALSE","","primary","research/market_state/STEP_B_VALIDATE.py","T2 validate step"),
 "market_state_gate_t3.py":("gateT3","script","CLOSED","FALSE","","primary","research/market_state/market_state_gate_t3.py","T3 gate construction"),
 "path_dependence_attribution.py":("gateT3","script","SUPERSEDED","FALSE","market_state_gate_t3.py","secondary","archive/superseded/path_dependence_attribution.py","early T3 attribution"),
 "cross_sectional_ranking_p1.py":("ranking","script","ACCEPTED","FALSE","","primary","research/ranking/cross_sectional_ranking_p1.py","P1 ranking discovery"),
 "cross_sectional_ranking_p1_corrected.py":("ranking","script","ACCEPTED","FALSE","","primary","research/ranking/cross_sectional_ranking_p1_corrected.py","P1.1 corrected"),
 "STEP_A_RANKING_VALIDATE_PREREGISTER.py":("p2val","script","ACCEPTED","FALSE","","primary","research/ranking/STEP_A_RANKING_VALIDATE_PREREGISTER.py","P2 preregister"),
 "STEP_B_RANKING_VALIDATE.py":("p2val","script","ACCEPTED","FALSE","","primary","research/ranking/STEP_B_RANKING_VALIDATE.py","P2 validate"),
 "atr_slot_allocation_p3.py":("p3","script","CLOSED","FALSE","","primary","research/portfolio/atr_slot_allocation_p3.py","P3 engine + instrumentation"),
 "slot_contention_path_audit.py":("p31","script","ACCEPTED","FALSE","","primary","research/portfolio/slot_contention_path_audit.py","P3.1 audit script"),
 "build_registry.py":("redteam","script","SUPERSEDED","FALSE","","secondary","archive/superseded/build_registry.py","old registry builder"),
 "claim_check_case_study.py":("redteam","script","SUPERSEDED","FALSE","","secondary","archive/superseded/claim_check_case_study.py","adj-factor claim check case study"),
 "cross_check_phase1.py":("redteam","script","SUPERSEDED","FALSE","","secondary","archive/superseded/cross_check_phase1.py","old regime cross-check"),
 "regime_discovery.py":("redteam","script","SUPERSEDED","FALSE","regime_discovery_corrected.py","secondary","archive/superseded/regime_discovery.py","old regime discovery v1"),
 "regime_discovery_corrected.py":("redteam","script","SUPERSEDED","FALSE","regime_discovery_v3.py","secondary","archive/superseded/regime_discovery_corrected.py","old regime discovery v2"),
 "regime_discovery_v3.py":("redteam","script","SUPERSEDED","FALSE","market_state_phase_t2.py","secondary","archive/superseded/regime_discovery_v3.py","old regime discovery v3"),
 "div_crosscheck.py":("redteam","script","SUPERSEDED","FALSE","","secondary","archive/superseded/div_crosscheck.py","dividend cross-check (early)"),
 "mechanism_plot.py":("governance","script","INFRASTRUCTURE","FALSE","","infra","tools/mechanism_plot.py","plot helper"),
}

rows = []
seen = set()
def add(path, phase, category, status, canonical, superseded_by, evidence_level, destination, notes):
    if path in seen:
        return
    seen.add(path)
    rows.append([path, "file", phase, category, status, canonical, superseded_by, evidence_level, destination, notes])

for f in files:
    if f in TOP_MD:
        ph,cat,st,ca,sb,el,dest,note = TOP_MD[f]; add(f,ph,cat,st,ca,sb,el,dest,note); continue
    if f in TOP_REG:
        ph,cat,st,ca,sb,el,dest,note = TOP_REG[f]; add(f,ph,cat,st,ca,sb,el,dest,note); continue
    if f in TOP_PY:
        ph,cat,st,ca,sb,el,dest,note = TOP_PY[f]; add(f,ph,cat,st,ca,sb,el,dest,note); continue

    if f.startswith("results/round5/"):
        rel = f.split("/",1)[1]
        if "optimistic" in f:
            add(f,"strict_c","result","SUPERSEDED","FALSE","","secondary","results/evidence/strict_c/"+rel,"optimistic-tick variant (invalid as evidence)")
        elif "v1" in f and "v2" not in f:
            add(f,"strict_c","result","SUPERSEDED","FALSE","","secondary","results/evidence/strict_c/"+rel,"v1 variant superseded")
        else:
            add(f,"strict_c","result","ACCEPTED","FALSE","","primary","results/evidence/strict_c/"+rel,"round5 STRICT_C frozen outputs")
        continue
    if f.startswith("results/p31_"):
        add(f,"p31","result","ACCEPTED","FALSE","","primary","results/evidence/p31/"+f[len("results/"):],"P3.1 mechanism audit output"); continue
    if f.startswith("results/p3_"):
        add(f,"p3","result","CLOSED","FALSE","","primary","results/evidence/p3/"+f[len("results/"):],"P3 portfolio output"); continue
    if f.startswith("results/p2_"):
        add(f,"p2val","result","ACCEPTED","FALSE","","primary","results/evidence/p2/"+f[len("results/"):],"P2 validation output"); continue
    if f.startswith("results/p11_"):
        add(f,"ranking","result","ACCEPTED","FALSE","","primary","results/evidence/p11/"+f[len("results/"):],"P1.1 corrected output"); continue
    if f.startswith("results/p1_"):
        add(f,"ranking","result","ACCEPTED","FALSE","","primary","results/evidence/p1/"+f[len("results/"):],"P1 discovery output"); continue
    if f.startswith("results/t2r_"):
        add(f,"marketstate","result","ACCEPTED","FALSE","","primary","results/evidence/t2r/"+f[len("results/"):],"T2-R validation output"); continue
    if f.startswith("results/t2_"):
        add(f,"marketstate","result","ACCEPTED","FALSE","","primary","results/evidence/t2/"+f[len("results/"):],"T2 discovery output"); continue
    if f.startswith("results/t3_"):
        add(f,"gateT3","result","CLOSED","FALSE","","primary","results/evidence/t3/"+f[len("results/"):],"T3 gate output"); continue
    if f.startswith("results/stop_phaseA"):
        add(f,"stopA","result","CLOSED","FALSE","","primary","results/evidence/stopA/"+f[len("results/"):],"stop phase A output (verdict C)"); continue
    if f.startswith("results/temporal_"):
        add(f,"temporal","result","ACCEPTED","FALSE","","primary","results/evidence/temporal/"+f[len("results/"):],"T1 output"); continue
    if f.startswith("results/fullmarket_"):
        add(f,"fullmarket","result","ACCEPTED","FALSE","","primary","results/evidence/fullmarket/"+f[len("results/"):],"full-market output"); continue
    if f.startswith("results/trade_path_"):
        add(f,"tradepath","result","SUPERSEDED","FALSE","fullmarket","primary","results/evidence/tradepath/"+f[len("results/"):],"primary-only path output; superseded by fullmarket"); continue
    if f.startswith("results/independent_"):
        add(f,"independent","result","ACCEPTED","FALSE","","primary","results/evidence/independent/"+f[len("results/"):],"independent replay output"); continue
    if f.startswith("results/regime_"):
        add(f,"redteam","result","SUPERSEDED","FALSE","","secondary","results/evidence/regime_old/"+f[len("results/"):],"old regime results (frozen)"); continue
    if "adjfactor" in f and f.startswith("results/"):
        add(f,"redteam","result","SUPERSEDED","FALSE","","secondary","results/evidence/redteam/"+f[len("results/"):],"adjfactor check output"); continue
    if f.startswith("results/"):
        base = os.path.basename(f)
        # original-system outputs (pre-lookahead +354.9% chain) -> INVALID evidence
        if base.startswith(("equity_curve","trades","yearly_returns","multi_pos_","parameter_scan_","etf_log","drawdown_","postexit")):
            add(f,"original","result","INVALID","FALSE","","invalid","archive/invalid/results/"+f[len("results/"):],"original-system output (invalid as performance evidence)")
        else:
            add(f,"governance","result","INFRASTRUCTURE","FALSE","","supporting","results/evidence/other/"+f[len("results/"):],"generic result artifact")
        continue
    if f.startswith("figures/"):
        base = os.path.basename(f)
        if base.startswith(("t2r_",)): ph="marketstate"
        elif base.startswith(("t2_",)): ph="marketstate"
        elif base.startswith(("t3_",)): ph="gateT3"
        elif base.startswith(("temporal_","monthly_","quarterly_","daily_","primary_secondary_temporal")): ph="temporal"
        elif base.startswith("stop_"): ph="stopA"
        elif base.startswith(("p1_",)): ph="ranking"
        elif base.startswith(("p2_",)): ph="p2val"
        elif base.startswith(("primary_vs_secondary","mae_","mfe_","turnover_","levels_","signal_crowding","secondary_","yearly_quality","underwater","post_exit")): ph="fullmarket"
        else: ph="governance"
        add(f,ph,"figure","ACCEPTED","FALSE","","supporting","figures/"+f[len("figures/"):],"figure for phase "+ph); continue
    if f.startswith("data/"):
        add(f,"infra","data","INFRASTRUCTURE","FALSE","","infra",f,"kline/etf market data (parquet)"); continue
    if f.startswith("analysis/"):
        # parameter/time-stop/topN sweeps served the original (lookahead) system -> INVALID evidence
        if any(k in f for k in ("param_scan","parameter_sweep","time_stop_sweep","topn_position_sweep","time_stop_single","single_stock_bb")):
            add(f,"original","script","INVALID","FALSE","","invalid","archive/invalid/analysis/"+f[len("analysis/"):],"parameter/time-stop/topN sweep on original system")
        else:
            add(f,"governance","script","INFRASTRUCTURE","FALSE","","infra","src/analysis/"+f[len("analysis/"):],"analysis helpers")
        continue
    if f.startswith("backtest/"):
        add(f,"governance","script","INFRASTRUCTURE","FALSE","","infra","src/backtest/"+f[len("backtest/"):],"backtest framework"); continue
    if f.startswith("config/"):
        add(f,"governance","config","INFRASTRUCTURE","FALSE","","infra","config/"+f[len("config/"):],"config"); continue
    if f.startswith("data_loader/"):
        add(f,"governance","script","INFRASTRUCTURE","FALSE","","infra","src/data_loader/"+f[len("data_loader/"):],"data loader"); continue
    if f.startswith("engine/"):
        add(f,"governance","script","INFRASTRUCTURE","FALSE","","infra","src/engine/"+f[len("engine/"):],"engine modules"); continue
    if f.startswith("tests/"):
        add(f,"governance","test","INFRASTRUCTURE","FALSE","","infra","tests/"+f[len("tests/"):],"invariant/parity tests"); continue
    if f.startswith("results_exp/"):
        if "exp2" in f:
            add(f,"redteam","result","INVALID","FALSE","","invalid","archive/invalid/results_exp/"+f[len("results_exp/"):],"exp2 limit-mismatch (invalid)")
        else:
            add(f,"redteam","result","SUPERSEDED","FALSE","","secondary","archive/superseded/results_exp/"+f[len("results_exp/"):],"early experiments")
        continue
    if f.startswith("round3/"):
        add(f,"redteam","result","SUPERSEDED","FALSE","","secondary","archive/superseded/round3/"+f[len("round3/"):],"round3 experiments"); continue
    if f.startswith("round4/"):
        add(f,"redteam","result","SUPERSEDED","FALSE","","secondary","archive/superseded/round4/"+f[len("round4/"):],"round4 experiments"); continue
    if f.startswith("round5/"):
        add(f,"redteam","script" if f.endswith(".py") else "result","SUPERSEDED","FALSE","","secondary","archive/superseded/round5/"+f[len("round5/"):],"round5 scripts; superseded by round51")
        continue
    if f.startswith("round51/"):
        if f.endswith(".py"):
            add(f,"strict_c","script","ACCEPTED","FALSE","","primary","src/round51/"+f[len("round51/"):],"STRICT_C frozen engine scripts (round51)")
        else:
            add(f,"strict_c","result","ACCEPTED","FALSE","","primary","results/evidence/strict_c/"+f[len("round51/"):],"round51 outputs")
        continue
    add(f,"governance","config" if f.endswith(".txt") or f==".gitignore" else "file","INFRASTRUCTURE","FALSE","","infra",f,"repo infrastructure file")

rows.sort(key=lambda r: r[0])
with open("REPO_INVENTORY.csv","w",newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["path","file_type","phase","category","status","canonical","superseded_by","evidence_level","recommended_destination","notes"])
    w.writerows(rows)

print("total tracked:", len(files), "inventoried:", len(rows))
from collections import Counter
print("status:", dict(Counter(r[4] for r in rows)))
print("phase:", dict(Counter(r[2] for r in rows)))
