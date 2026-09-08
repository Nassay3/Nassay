import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_bls_news_blackout as nb

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS;nb.g.URLS=g.URLS

def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(ids[0]),int(ids[-1])
def pack(v):return vp.pack(v)

def run():
    events=nb.parse_bls();x=g.prep();idx=x.index
    ed=m.build_edges(x);rL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);rS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);z=rL&rS;rL&=~z;rS&=~z
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    baseL=rL&wL&pd.Series(ok&(c>poc),index=idx);baseS=rS&wS&pd.Series(ok&(c<poc),index=idx)
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    modes=[('NONE',set(),0,0,'none'),('NFP_30_60',{'NFP'},30,60,'init'),('CPI_30_60',{'CPI'},30,60,'init'),('BOTH_30_60',{'NFP','CPI'},30,60,'init'),('BOTH_60_60',{'NFP','CPI'},60,60,'init'),('BOTH_30_60_ALL',{'NFP','CPI'},30,60,'all'),('BOTH_60_60_ALL',{'NFP','CPI'},60,60,'all')]
    rows=[];cache={}
    for name,kinds,pre,post,scope in modes:
        allow=pd.Series(True,index=idx) if name=='NONE' else nb.allow_mask(idx,events,kinds,pre,post)
        L=(baseL&allow).to_numpy(np.bool_) if scope!='none' else baseL.to_numpy(np.bool_)
        S=(baseS&allow).to_numpy(np.bool_) if scope!='none' else baseS.to_numpy(np.bool_)
        if scope=='all': addL=allow.to_numpy(np.bool_);addS=allow.to_numpy(np.bool_)
        else: addL=np.ones(len(x),dtype=np.bool_);addS=np.ones(len(x),dtype=np.bool_)
        arr=(o,h,lo,c,atr,slo,shi,L,S,addL,addS);cache[name]=arr
        # Current return champion from coarse pre-holdout screen: AF.65 BE1.25 max4 TP20 hold12h.
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],.65,1.25,4,20.,144));va=pack(vp.sim_profile(*arr,vab[0],vab[1],.65,1.25,4,20.,144))
        score=tr['ret']-1.5*tr['dd']+.85*va['ret']-1.25*va['dd']-50*abs(tr['avgR']-va['avgR']);rows.append((score,name,tr,va,int((~allow).sum())))
        print('SCREEN',name,'TR',round(tr['ret'],2),round(tr['pf'],3),'VA',round(va['ret'],2),round(va['pf'],3),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);pick=[]
    pick.append([r for r in rows if r[1]=='NONE'][0])
    for r in rows:
      if r[1]!='NONE' and len(pick)<4:pick.append(r)
    prom=[]
    for score,name,tr,va,blocked in pick:
      arr=cache[name];ho=pack(vp.sim_profile(*arr,hob[0],hob[1],.65,1.25,4,20.,144));full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],.65,1.25,4,20.,144));prom.append({'mode':name,'score':score,'blocked_bars':blocked,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'strategy':'BRK+EXP + 24h POC + Riyadh SAME WEEK_PLUS_ANY | AF.65 BE1.25 max4 TP20 hold12h','calendar':'Official BLS schedules 2021-2026; America/New_York event times -> UTC','selection':'blackout ranked Train+Validation only; NONE + top3 exposed Holdout','promoted':prom,'limitations':['NFP/CPI only here; FOMC/PCE separate','blackout modes either suppress campaign starts only or both starts+sequential adds','existing open lots are not forcibly closed']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':run()
