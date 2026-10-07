"""Exploratory delayed-label macro update of aggregate employment profiles.

Three SCE categories: employed, SCE unemployed label, remaining/unknown.
These are survey-profile shares, not the CPS labour-force unemployment rate.
"""
import numpy as np


def month_shift(month, offset):
    y,m=divmod(int(month),100)
    if not 1<=m<=12:raise ValueError('invalid YYYYMM')
    index=y*12+m-1+offset
    return index//12*100+index%12+1


def employment_shares(margin):
    result=np.array([margin.get('employed',0.),margin.get('unemployed',0.),
                     1.-margin.get('employed',0.)-margin.get('unemployed',0.)],dtype=float)
    if not np.isfinite(result).all() or (result<0).any() or not np.isclose(result.sum(),1.):
        raise ValueError('invalid population shares')
    return result


def logratios(shares):
    shares=np.asarray(shares,dtype=float)
    if shares.shape!=(3,) or not np.isfinite(shares).all() or (shares<0).any() or not np.isclose(shares.sum(),1.):
        raise ValueError('invalid population composition')
    p=np.maximum(shares,1e-6);p=p/p.sum()
    return np.log(p[:2]/p[2])


def reconstruct(base, update):
    z=np.r_[logratios(base)+update,0.]
    p=np.exp(z-z.max())
    return p/p.sum()


def forecast(rows, test_row, *, label_cutoff, method='macro_ridge', min_train=24):
    """Fit only previously available profile labels; scale only training X.

    Fixed ridge alpha=1; no hyperparameter search on forecast months.
    Availability cutoff is provided by the caller and must precede target month.
    """
    if label_cutoff>=test_row['month']:raise ValueError('label cutoff must precede target')
    if method not in ('unrate_ols','macro_ridge','historical_drift'):raise ValueError('unknown method')
    train=[r for r in rows if r['month']<=label_cutoff]
    if len(train)<min_train:raise ValueError('insufficient previously available labels')
    width=1 if method=='unrate_ols' else 3
    x=np.array([r['features'][:width] for r in train],float)
    if x.shape!=(len(train),width) or not np.isfinite(x).all():raise ValueError('invalid training predictors')
    y=np.array([logratios(r['truth'])-logratios(r['base']) for r in train])
    if method=='historical_drift':
        return reconstruct(test_row['base'],y.mean(axis=0)),{
            'train_n':len(train),'max_train_month':max(r['month'] for r in train),
            'label_cutoff':label_cutoff,'features':0,'ridge_alpha':0.,
            'coefficients_standardized':[y.mean(axis=0).tolist()]}
    center=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-12]=1.
    design=np.column_stack([np.ones(len(x)),(x-center)/scale])
    if method=='unrate_ols':coef=np.linalg.lstsq(design,y,rcond=None)[0]
    else:
        penalty=np.diag(np.r_[0.,np.ones(width)])
        coef=np.linalg.solve(design.T@design+penalty,design.T@y)
    test=np.r_[1.,(np.array(test_row['features'][:width])-center)/scale]
    result=reconstruct(test_row['base'],test@coef)
    return result,{'train_n':len(train),'max_train_month':max(r['month'] for r in train),
                   'label_cutoff':label_cutoff,'features':width,'ridge_alpha':1. if method=='macro_ridge' else 0.,
                   'coefficients_standardized':coef.tolist()}
