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

def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(ids[0]),int(ids[-1])
def pack(v):return vp.pack(v)

def run():
    x=g.prep();idx=x.index
    ed=m.build_edges(x);rL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);rS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);z=rL&rS;rL&=~z;rS&=~z
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(rL&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(rS&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_);ones=np.ones(len(x),dtype=np.bool_)
    arr=(o,h,lo,c,atr,slo,shi,L,S,ones,ones)
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    rows=[];cache={}
    for af in (.60,.65,.70):
      for be in (1.15,1.25,1.35):
        for tp in (18.,19.,20.,21.):
          tr=pack(vp.sim_profile(*arr,trb[0],trb[1],af,be,4,tp,144));va=pack(vp.sim_profile(*arr,vab[0],vab[1],af,be,4,tp,144))
          score=tr['ret']-1.5*tr['dd']+.85*va['ret']-1.25*va['dd']-50*abs(tr['avgR']-va['avgR'])
          key=(af,be,tp);rows.append((score,key,tr,va));cache[key]=(tr,va)
          print('SCREEN',key,'TR',round(tr['ret'],2),round(tr['pf'],3),round(tr['dd'],2),'VA',round(va['ret'],2),round(va['pf'],3),round(va['dd'],2),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);prom=[]
    # baseline return champion included plus top 8 selected exclusively by Train+Validation.
    picks=[];base=(.65,1.25,20.)
    picks.append([r for r in rows if r[1]==base][0])
    for r in rows:
      if r[1]!=base and len(picks)<9:picks.append(r)
    for score,key,tr,va in picks:
      af,be,tp=key;ho=pack(vp.sim_profile(*arr,hob[0],hob[1],af,be,4,tp,144));full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],af,be,4,tp,144))
      prom.append({'af':af,'beR':be,'tpR':tp,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'frozen_entry':'BRK+EXP + 24h M5 POC + Riyadh SAME WEEK_PLUS_ANY','fixed':'max4, hold12h','local_grid':{'af':[.60,.65,.70],'beR':[1.15,1.25,1.35],'tpR':[18,19,20,21]},'selection':'Train+Validation only; baseline AF.65/BE1.25/TP20 + top8 exposed to Holdout','promoted':prom,'warning':'Local plateau verification after coarse screen; not a global optimizer.'},default=float));print('RESULT_JSON_END')
if __name__=='__main__':run()
