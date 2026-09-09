"""pytest fixtures: put src/ on sys.path for alpha_factory imports."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)
