"""Typeset the competition research-report draft from frozen aggregate evidence."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] /
                      "studies/sce_inflation_expectations/reports/final_report_draft/render.py"),
                   run_name="__main__")
