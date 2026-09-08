import os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd

import gold_dukascopy_tick_validation as d

CANDIDATE='SQ03_EXP_PULL_WREL2PRICE2_POC96'
EDGES=('EXP','PULL')
VWAP_MODE='W_REL2_PRICE2'
PROFILE_LB=96
AF=.80
BE_R=2.25
MAX_LOTS=3
TP_R=28.0
HOLD_HOURS=18.0


def build_signals(m1path):
    d.g.URLS=[m1path]
    d.m.g.URLS=d.g.URLS
    d.vp.g.URLS=d.g.URLS
    d.vw.g.URLS=d.g.URLS
    d.vc.g.URLS=d.g.URLS
    d.g.END=d.END
    x=d.g.prep(); idx=x.index; ed=d.m.build_edges(x)
    L=pd.Series(False,index=idx); S=pd.Series(False,index=idx)
    for nm in EDGES:
        L |= ed[nm][0]; S |= ed[nm][1]
    clash=L&S; L &= ~clash; S &= ~clash
    c=x.close.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    poc,_,_=d.vp.profile_levels(h,lo,c,vol,PROFILE_LB,32,3,.70)
    ok=np.isfinite(poc)
    f=d.vw.vwap_ladder(x,3,True)
    wL,wS=d.vc.mk_masks(x,f)[VWAP_MODE]
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).fillna(False)
    S=(S&wS&pd.Series(ok&(c<poc),index=idx)).fillna(False)
    x=x.copy(); x['sigL']=L; x['sigS']=S
    x['slo7']=x.low.rolling(7,min_periods=1).min(); x['shi7']=x.high.rolling(7,min_periods=1).max()
    return x


def main():
    os.makedirs(d.RAW,exist_ok=True)
    hours=d.hours_range()
    print('DOWNLOAD_HOURS',len(hours),flush=True)
    with ThreadPoolExecutor(max_workers=20) as ex:
        fut=[ex.submit(d.fetch_hour,t) for t in hours]
        done=0;valid=0;byt=0
        for f in as_completed(fut):
            _,p,n=f.result(); done+=1; valid+=int(p is not None); byt+=n
            if done%240==0:
                print('DL',done,'/',len(hours),'valid',valid,'MB',round(byt/1e6,1),flush=True)
    m1path,datadiag=d.make_m1(hours)
    x=build_signals(m1path)
    print('DUKA_DATA',datadiag,flush=True)
    out={}
    for extra in (0.0,.02,.05,.10):
        key=f'BIDASK_PLUS_{extra:.2f}R'
        out[key]=d.sim_ticks(x,hours,AF,BE_R,MAX_LOTS,TP_R,HOLD_HOURS,extra)
        print(CANDIDATE,key,out[key],flush=True)
    print('RESULT_JSON_START')
    print(json.dumps({
        'candidate':CANDIDATE,
        'source':'Dukascopy public XAUUSD BI5 bid/ask quote ticks',
        'download_window':[str(d.DL_START),str(d.END)],
        'test_window':[str(d.TEST_START),str(d.END)],
        'data':datadiag,
        'edges':list(EDGES),
        'filters':{'vwap':VWAP_MODE,'activity_profile':'POC96 causal 32-bin 70% VA proxy'},
        'params':{'atr_floor':AF,'beR':BE_R,'max_lots':MAX_LOTS,'targetR':TP_R,'hold_hours':HOLD_HOURS,'fresh_signal_add':True},
        'risk_rule':'0.36% of current executable bid/ask MTM equity per fresh lot; prior live lots protected before add',
        'execution':'long enters ask/exits bid; short enters bid/exits ask; variable spread implicit; observed quote can slip through stop; optional extra round-trip cost stress in R',
        'results':out,
        'selection_note':'Candidate was chosen from pre-2025 historical robustness plus GetData validation before this Dukascopy run. Dukascopy therefore serves as the next independent execution test.',
        'limitations':['Independent broker quote feed, not CME GC futures.','Profile uses quote activity, not COMEX traded volume-at-price.','Six-week tick window is execution validation, not a multi-year proof.']
    },default=float))
    print('RESULT_JSON_END')

if __name__=='__main__':
    main()
