import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS

def pack(v):return vp.pack(v)
def bnd(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)))
    return None if len(ids)<100 else (int(ids[0]),int(ids[-1]))

def run():
    x=g.prep();idx=x.index
    ed=m.build_edges(x);rL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);rS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);z=rL&rS;rL&=~z;rS&=~z
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(rL&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(rS&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_);ones=np.ones(len(x),dtype=np.bool_)
    arr=(o,h,lo,c,atr,slo,shi,L,S,ones,ones)
    finalists={
      'BASE_075_TP18':(.75,1.25,4,18.,144),
      'ROBUST_065_TP18':(.65,1.25,4,18.,144),
      'RETURN_065_TP20':(.65,1.25,4,20.,144),
      'NEIGHBOR_070_TP20':(.70,1.25,4,20.,144),
      'NEIGHBOR_070_TP19':(.70,1.25,4,19.,144),
    }
    cuts=[];cur=pd.Timestamp('2021-09-08',tz='UTC');end=pd.Timestamp('2026-07-22',tz='UTC')
    while cur<end:
        nxt=min(cur+pd.DateOffset(months=6),end);cuts.append((cur,nxt));cur=nxt
    out={}
    for name,p in finalists.items():
        af,be,ml,tp,hold=p;sl=[]
        for a,b in cuts:
            bd=bnd(idx,a,b)
            if bd is None:continue
            r=pack(vp.sim_profile(*arr,bd[0],bd[1],af,be,ml,tp,hold));r['start']=str(a.date());r['end']=str(b.date());sl.append(r)
        rets=np.array([q['ret'] for q in sl]);pfs=np.array([q['pf'] for q in sl]);dds=np.array([q['dd'] for q in sl]);avgr=np.array([q['avgR'] for q in sl])
        out[name]={'params':{'af':af,'beR':be,'maxlots':ml,'tpR':tp,'hold_hours':hold*5/60},'slices':sl,'summary':{'n':len(sl),'positive_slices':int((rets>0).sum()),'negative_slices':int((rets<0).sum()),'median_ret':float(np.median(rets)),'mean_ret':float(np.mean(rets)),'worst_ret':float(np.min(rets)),'best_ret':float(np.max(rets)),'median_pf':float(np.median(pfs)),'min_pf':float(np.min(pfs)),'median_dd':float(np.median(dds)),'max_slice_dd':float(np.max(dds)),'median_avgR':float(np.median(avgr))}}
        print('WF',name,out[name]['summary'],flush=True)
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'entry':'BRK+EXP + causal 24h M5 POC + Riyadh SAME WEEK_PLUS_ANY','policy':'Five predeclared finalists only; independent 6-month resets used for regime robustness, not parameter fitting.','results':out},default=float));print('RESULT_JSON_END')
if __name__=='__main__':run()
