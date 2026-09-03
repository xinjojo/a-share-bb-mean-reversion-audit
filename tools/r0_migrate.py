#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
R0-B: apply REPO_INVENTORY.recommended_destination via git mv (history-preserving).
Run from repo root: python3 tools/r0_migrate.py
Only performs renames/moves; never deletes content.
"""
import csv, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

rows = list(csv.DictReader(open('REPO_INVENTORY.csv')))

moves = []
for r in rows:
    old = r['path']
    new = r['recommended_destination']
    if new and new != old:
        moves.append((old, new))

# do not move governance entry files / infra that must stay
skip_prefixes = ('README.md','CURRENT_STATUS.md','RESEARCH_MAP.md','REPO_INVENTORY.csv','MIGRATION_MAP.csv',
                 'REMOTE_VERIFICATION.md','data/','config/','figures/','tools/','tests/')
moves = [(o,n) for o,n in moves if not o.startswith(skip_prefixes)]

print("planned moves:", len(moves))
# detect duplicate targets
from collections import Counter
dup = [t for t,c in Counter(n for _,n in moves).items() if c>1]
if dup:
    print("DUPLICATE TARGETS:", dup); sys.exit(1)

done, failed = [], []
for old, new in moves:
    parent = os.path.dirname(new)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    # mkdir before git mv so empty dirs don't matter; git mv handles file
    if not os.path.exists(old):
        failed.append((old, new, "old missing")); continue
    if os.path.exists(new):
        failed.append((old, new, "new exists")); continue
    try:
        subprocess.run(["git","mv",old,new], check=True, capture_output=True)
        done.append((old,new))
    except subprocess.CalledProcessError as e:
        failed.append((old,new,e.stderr.decode(errors='replace').strip()[:200]))

print("moved:", len(done), "failed:", len(failed))
for o,n,err in failed:
    print("  FAIL", o, "->", n, "|", err)

# write MIGRATION_MAP.csv (all inventory rows with destination change, plus moved ones marked)
with open('MIGRATION_MAP.csv','w',newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['old_path','new_path','status','canonical'])
    for r in rows:
        old, new = r['path'], r['recommended_destination']
        if new and new != old:
            w.writerow([old, new, r['status'], r['canonical']])
print("MIGRATION_MAP.csv rows:", sum(1 for r in rows if r['recommended_destination'] and r['recommended_destination']!=r['path']))
