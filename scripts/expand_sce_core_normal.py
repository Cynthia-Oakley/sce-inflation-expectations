"""Expand scored LLM Core answers; no current truth or provider API accepted."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studies.sce_inflation_expectations.experiments.core_normal_expansion import predict

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--population',required=True,type=Path)
    p.add_argument('--core',required=True,type=Path)
    p.add_argument('--answers',required=True,type=Path)
    p.add_argument('--tau',required=True,type=float)
    p.add_argument('--normal-seed',type=int)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();predict(a.population,a.core,a.answers,a.out,tau=a.tau,normal_seed=a.normal_seed)
