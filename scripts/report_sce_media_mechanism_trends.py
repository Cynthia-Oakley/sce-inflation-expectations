#!/usr/bin/env python3
"""Publish monthly line charts and the unexecuted crossed-design proposal."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.reports.media_mechanism_trends import publish
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--crossed',type=Path,required=True)
    a=p.parse_args();print(json.dumps(publish(a.source,a.out,a.crossed),ensure_ascii=False,indent=2))
