import json
import numpy as np
import pandas as pd

import gold_duka_winner_crosscheck as w
from gold_duka_microfeatures import compute_features

START=pd.Timestamp('2026-01-01',tz='UTC')
END=pd.Timestamp('2026-06-23 17:00:00',tz='UTC')


def prior_duka_features(sig,exe):
    f=compute_features(exe)
    ens=pd.DatetimeIndex(exe.time).as_unit('ns').asi8
    dns=pd.DatetimeIndex(sig.index+pd.Timedelta(minutes=5)).as_unit('ns').asi8
    pos=np.searchsorted(ens,dns)-1
    good=(pos>=0)&(pos<len(ens))
    out=pd.DataFrame(index=sig.index,columns=f.columns,dtype=float)
    gi=np.flatnonzero(good)
    out.iloc[gi]=f.iloc[pos[good]].to_numpy(float)
    return out


def records(sig,L,S,label):
    out=[]
    for i,(ts,row) in enumerate(sig.iterrows()):
        if ts<START or ts>=END: continue
        d=1 if bool(L.iloc[i]) and not bool(S.iloc[i]) else (-1 if bool(S.iloc[i]) and not bool(L.iloc[i]) else 0)
        if d==0: continue
        es=float(row.next_open_signal); av=float(row.atr14)
        if not np.isfinite(es) or es<=0 or not np.isfinite(av) or av<=0: continue
        if d==1:
            st=min(float(row.slo7)-.1*av,es-.8*av); risk=es-st
        else:
            st=max(float(row.shi7)+.1*av,es+.8*av); risk=st-es
        rp=risk/es
        if not np.isfinite(rp) or rp<=0 or rp>.012: continue
        entry_ts=ts+pd.Timedelta(minutes=5)
        out.append({'t':int(entry_ts.timestamp()*1000),'d':int(d),'rp':float(rp),'src':label})
    return out


def compact(rr):
    # Lossless timestamps at minute resolution; risk pct quantized to 1e-8 (well below market tick relevance).
    mins=[int(z['t']//60000) for z in rr]
    first=mins[0] if mins else 0
    dt=[0]+[mins[i]-mins[i-1] for i in range(1,len(mins))] if mins else []
    dirs=''.join('L' if z['d']==1 else 'S' for z in rr)
    rp8=[int(round(z['rp']*100_000_000)) for z in rr]
    # Verify round trip before emitting.
    cur=first;ts=[]
    for i,d in enumerate(dt):
        if i>0: cur+=d
        ts.append(cur*60000)
    assert ts==[z['t'] for z in rr]
    assert all(abs(rp8[i]/100_000_000-rr[i]['rp'])<=5.1e-9 for i in range(len(rr)))
    return {'first_min':first,'dt_min':dt,'dirs':dirs,'rp8':rp8}


def main():
    sig=w.build_winner_signals(); exe,ediag=w.d.load_execution(); feat=prior_duka_features(sig,exe)
    baseL=sig.sigL.astype(bool);baseS=sig.sigS.astype(bool)
    sr=feat.spread_ratio;m5=feat.mom5;p=feat.pressure5
    qL=((m5>0)&(p>0)&(sr<=1.25)).fillna(False)
    qS=((m5<0)&(p<0)&(sr<=1.25)).fillna(False)
    robustL=baseL&qL;robustS=baseS&qS
    base=records(sig,baseL,baseS,'BASE')
    robust=records(sig,robustL,robustS,'M5_PRESS_SPR125')
    for name,rr in [('BASE',base),('M5_PRESS_SPR125',robust)]:
        assert all(rr[i]['t']<=rr[i+1]['t'] for i in range(len(rr)-1))
        assert all(0<z['rp']<=.012 and z['d'] in (-1,1) for z in rr)
        assert len({(z['t'],z['d']) for z in rr})==len(rr)
    print('SIGNAL_EXPORT_SUMMARY',json.dumps({'window':[str(START),str(END)],'base_n':len(base),'robust_n':len(robust),'execution_data':ediag},default=float),flush=True)
    print('BASE_COMPACT',json.dumps(compact(base),separators=(',',':')))
    print('ROBUST_COMPACT',json.dumps(compact(robust),separators=(',',':')))

if __name__=='__main__':main()
