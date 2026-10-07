"""Parse available first-release CPI fields without inventing missing months."""
import re
import build_sce_environment as bls


def cpi_available(text, reference_period):
    if reference_period != '2025-11':
        return bls.transcribe_cpi(text, reference_period)
    compact = bls._compact(text)
    if not re.search(r'consumerpriceindex-?november2025', compact) or not (
            'overthe2monthsfromseptember2025tonovember2025' in compact):
        raise ValueError('November 2025 two-month release context absent')
    annual = re.search(r'allitemsindex(increased|decreased)([\d.]+)percentbeforeseasonaladjustment', compact)
    two = re.search(r'consumerpriceindexforallurbanconsumerscpi-u(increased|decreased)([\d.]+)percentonaseasonallyadjustedbasisoverthe2months', compact)
    usdl = re.search(r'usdl-(\d{2}-\d{4})', compact)
    if not all((annual, two, usdl)):
        raise ValueError('November 2025 available CPI fields incomplete')
    def value(match):
        return {'value': float(match[2]) * (-1 if match[1]=='decreased' else 1),
                'quote': bls._quote(compact, match)}
    return {'cpi_yoy_nsa_pct': value(annual), 'cpi_mom_sa_pct': None,
            'cpi_two_month_sa_pct': value(two), 'usdl': usdl[1],
            'missing_reason': 'BLS did not collect October 2025 survey prices; monthly change unavailable'}
