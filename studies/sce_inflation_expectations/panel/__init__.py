"""Offline experiment analysis panel (v1, batch 1: statistical correctness).

Reads already-scored evaluation caches (cases_private.json + summary.json),
builds canonical long records on an explicit common support, aggregates six
fixed sections plus the experiment catalog, and renders a self-contained HTML
panel. Zero API calls, zero network, pure local compute. Person-level
intermediates stay under outputs/ (git-ignored); only aggregate HTML is
published under docs/reports/experiment_panel/.
"""
