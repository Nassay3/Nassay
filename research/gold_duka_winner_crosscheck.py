import json
import numpy as np
import pandas as pd

import gold_quality_duka_bidask as qsel
import gold_quality_duka_bidask_corrected as corr

d=qsel.d

# Freeze Numba-selected winner. Selection used only ERA1/ERA2/ERA3 before 2025.
d.CANDIDATE='DUKA_EXEC_BRK_DWREL_POCMOM25'
d.AF=.80
d.BE_R=4.0
d.MAX_LOTS=2
d.TP_R=10.0
d.HOLD_MIN=24*60


def build_winner_signals():
    d.wire_signal_source();x=d.g.prep();idx=x.index;ed=d.m.build_edges(x)
    L=ed['BRK'][0].fillna(False).copy();S=ed['BRK'][1].fillna(False).copy()
    clash=L&S;L&=~clash;S&=~clash
    c=x.close.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);vol=x.tick_volume.to_numpy(float);atr=x.atr14.to_numpy(float)
    poc,_,_=d.vp.profile_levels(h,lo,c,vol,288,32,3,.70)
    ok=np.isfinite(poc)&np.isfinite(atr)&(atr>0)
    pL=pd.Series(ok&(c>poc)&((c-poc)>=.25*atr),index=idx)
    pS=pd.Series(ok&(c<poc)&((poc-c)>=.25*atr),index=idx)
    f=d.vw.vwap_ladder(x,3,True);wL,wS=d.vc.mk_masks(x,f)['DW_REL_PRICE2']
    L=(L&wL&pL).fillna(False);S=(S&wS&pS).fillna(False)
    x=x.copy();x['sigL']=L;x['sigS']=S
    x['slo7']=x.low.rolling(7,min_periods=1).min();x['shi7']=x.high.rolling(7,min_periods=1).max()
    x['next_open_signal']=x.open.shift(-1)
    return x


def main():
    sig=build_winner_signals();exe,ediag=d.load_execution();bdiag=corr.basis_diag(sig,exe)
    results={}
    for name,a,b in d.SPLITS:
        r=corr.sim_segment_corrected(sig,exe,a,b);results[name]=r
        print(name,json.dumps(r,default=float),flush=True)
    print('RESULT_JSON_START')
    print(json.dumps({'candidate':d.CANDIDATE,'engine':'independent pure-Python corrected-distance BID/ASK crosscheck',
      'selected_without_2025plus':True,'execution_data':ediag,'basis_diag':bdiag,
      'edges':['BRK'],'filters':{'vwap':'DW_REL_PRICE2','profile':'24h POC + >=0.25ATR momentum'},
      'params':{'atr_floor':d.AF,'beR':d.BE_R,'max_lots':d.MAX_LOTS,'targetR':d.TP_R,'hold_hours':24,'fresh_signal_add':True},
      'splits':results,'comparison_expectation':'Should be close to Numba rebuild; differences only from one-minute scheduling implementation are acceptable if small, not sign-changing.'},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
