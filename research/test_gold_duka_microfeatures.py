import numpy as np
import pandas as pd

from gold_duka_microfeatures import compute_features


def synthetic(n=40):
    t=pd.date_range('2026-01-01', periods=n, freq='1min', tz='UTC')
    mid=3000.0 + np.arange(n)*0.10
    spread=np.full(n,0.50)
    bid=mid-spread/2
    ask=mid+spread/2
    return pd.DataFrame({
        'time':t,
        'open_bid':bid-.02,'high_bid':bid+.08,'low_bid':bid-.06,'close_bid':bid,
        'open_ask':ask-.02,'high_ask':ask+.08,'low_ask':ask-.06,'close_ask':ask,
    })


def main():
    x=synthetic()
    a=compute_features(x)
    # Constant 0.50 spread should normalize to ~1 after the rolling warm-up.
    assert abs(float(a.spread_ratio.iloc[-1])-1.0)<1e-10, a.spread_ratio.iloc[-1]
    # Monotonic mid must have positive causal 1m/5m/15m momentum.
    assert float(a.mom1.iloc[-1])>0
    assert float(a.mom5.iloc[-1])>0
    assert float(a.mom15.iloc[-1])>0
    # No future leakage: alter only the future tail; all earlier features must remain identical.
    y=x.copy()
    cut=25
    y.loc[cut+1:,['open_bid','high_bid','low_bid','close_bid','open_ask','high_ask','low_ask','close_ask']] += 500.0
    b=compute_features(y)
    cols=['spread','spread_ratio','spread_change','mom1','mom5','mom15','clv5','range_exp5','pressure5']
    np.testing.assert_allclose(a.loc[:cut,cols].to_numpy(float),b.loc[:cut,cols].to_numpy(float),equal_nan=True,rtol=0,atol=0)
    # Features at row t may only use rows <=t, so first long-horizon values stay NaN until enough past exists.
    assert np.isnan(a.mom15.iloc[10])
    assert np.isfinite(a.mom15.iloc[20])
    print('DUKA_MICROFEATURE_TESTS_PASS')


if __name__=='__main__':main()
