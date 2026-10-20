"""Offline experiment analysis panel (v0).

Reads already-scored evaluation caches (cases_private.json + summary.json),
builds canonical long records, aggregates six fixed sections and renders a
self-contained HTML panel. Zero API calls, zero network, pure local compute.
"""
