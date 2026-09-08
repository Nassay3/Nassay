import numpy as np
import pandas as pd
import gold_duka_m1_bidask_multiyear as d

# Freeze the winner selected ONLY on pre-2025 historical base+stress in gold_quality_filter_failclosed.py.
d.CANDIDATE='QUALITY_PULL_WREL2PRICE2_POCMOM025'
d.EDGES=('PULL',)
d.VWAP_MODE='W_REL2_PRICE2'
d.PROFILE_LB=288  # 24h on M5
d.AF=.80
d.BE_R=2.25
d.MAX_LOTS=3
d.TP_R=28.
d.HOLD_MIN=18*60


def build_quality_signals():
    d.wire_signal_source(); x=d.g.prep(); idx=x.index; ed=d.m.build_edges(x)
    L=ed['PULL'][0].fillna(False).copy(); S=ed['PULL'][1].fillna(False).copy()
    clash=L&S; L&=~clash; S&=~clash
    c=x.close.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); vol=x.tick_volume.to_numpy(float); atr=x.atr14.to_numpy(float)
    poc,_,_=d.vp.profile_levels(h,lo,c,vol,288,32,3,.70)
    ok=np.isfinite(poc)&np.isfinite(atr)&(atr>0)
    # Frozen profile condition: correct side of 24h POC and at least 0.25 ATR away from POC.
    pL=pd.Series(ok&(c>poc)&((c-poc)>=.25*atr),index=idx)
    pS=pd.Series(ok&(c<poc)&((poc-c)>=.25*atr),index=idx)
    f=d.vw.vwap_ladder(x,3,True); wL,wS=d.vc.mk_masks(x,f)['W_REL2_PRICE2']
    L=(L&wL&pL).fillna(False); S=(S&wS&pS).fillna(False)
    x=x.copy(); x['sigL']=L; x['sigS']=S
    x['slo7']=x.low.rolling(7,min_periods=1).min(); x['shi7']=x.high.rolling(7,min_periods=1).max()
    return x


d.build_signals=build_quality_signals

if __name__=='__main__':
    d.main()
