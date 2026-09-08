import json
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS

def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b))); return int(ids[0]),int(ids[-1])
def pack(v): return vp.pack(v)

@njit(cache=True)
def m1_profile_for_m5(m1_ns,m1_h,m1_l,m1_c,m1_v,m5_end_ns,lookback_ns,bins=32,refresh=3):
    n=len(m5_end_ns); out=np.full(n,np.nan); hist=np.zeros(bins,np.float64)
    last=np.nan
    for i in range(n):
        if refresh>1 and i%refresh!=0 and np.isfinite(last):
            out[i]=last; continue
        end=m5_end_ns[i]; start=end-lookback_ns
        a=np.searchsorted(m1_ns,start); b=np.searchsorted(m1_ns,end)
        if b-a<30: continue
        lo0=1e100; hi0=-1e100
        for j in range(a,b):
            if m1_l[j]<lo0: lo0=m1_l[j]
            if m1_h[j]>hi0: hi0=m1_h[j]
        span=hi0-lo0
        if span<=0: continue
        for k in range(bins): hist[k]=0.
        for j in range(a,b):
            typ=(m1_h[j]+m1_l[j]+m1_c[j])/3.
            k=int((typ-lo0)/span*bins)
            if k<0:k=0
            if k>=bins:k=bins-1
            w=m1_v[j]
            if not np.isfinite(w) or w<=0:w=1.
            hist[k]+=w
        best=-1.; p=0
        for k in range(bins):
            if hist[k]>best:best=hist[k];p=k
        last=lo0+(p+.5)*(span/bins);out[i]=last
    return out

def run():
    # Build frozen M5 signal stack, then separately read original M1 only for the profile calculation.
    x=g.prep(); idx=x.index
    ed=m.build_edges(x); rawL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False); rawS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False)
    z=rawL&rawS;rawL&=~z;rawS&=~z
    f=vw.vwap_ladder(x,3,True); wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    ones=np.ones(len(x),dtype=np.bool_)
    raw=g.read_all()
    mns=raw.index.asi8.astype(np.int64); mh=raw.high.to_numpy(float); ml=raw.low.to_numpy(float); mc=raw.close.to_numpy(float); mv=raw.tick_volume.to_numpy(float)
    mend=(idx+pd.Timedelta(minutes=5)).asi8.astype(np.int64)
    profiles={}
    print('BUILD_M5_24H',flush=True); m5p,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70); profiles['M5_24H']=m5p
    for hrs in (12,24,48):
        print('BUILD_M1',hrs,'H',flush=True)
        profiles[f'M1_{hrs}H']=m1_profile_for_m5(mns,mh,ml,mc,mv,mend,np.int64(hrs*3600*1_000_000_000),32,3)
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    rows=[];cache={}
    for name,poc in profiles.items():
        ok=np.isfinite(poc); L=(rawL&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(rawS&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
        arr=(o,h,lo,c,atr,slo,shi,L,S,ones,ones);cache[name]=arr
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],.75,1.25,4,18.,144));va=pack(vp.sim_profile(*arr,vab[0],vab[1],.75,1.25,4,18.,144))
        score=tr['ret']-1.5*tr['dd']+.85*va['ret']-1.25*va['dd']-50*abs(tr['avgR']-va['avgR']);rows.append((score,name,tr,va))
        print('SCREEN',name,'TR',round(tr['ret'],2),round(tr['pf'],3),'VA',round(va['ret'],2),round(va['pf'],3),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);prom=[]
    # only four predeclared variants: exposing all on Holdout does not create a second selection grid.
    for score,name,tr,va in rows:
        arr=cache[name];ho=pack(vp.sim_profile(*arr,hob[0],hob[1],.75,1.25,4,18.,144));full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],.75,1.25,4,18.,144))
        prom.append({'name':name,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'frozen':'BRK+EXP + Riyadh SAME WEEK_PLUS_ANY | AF.75 BE1.25 max4 TP18 hold12h','profile':'M1 HLC3 weighted by each completed M1 bar tick_volume into 32 dynamic price bins; exact elapsed lookback; causal; refresh every 15m','comparison':['M5_24H proxy','M1_12H','M1_24H','M1_48H'],'promoted':prom,'warning':'Still quote/tick activity, not COMEX GC traded volume-at-price.'},default=float));print('RESULT_JSON_END')
if __name__=='__main__':run()
