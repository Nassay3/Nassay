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

def bnd(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])
def pack(v):return vp.pack(v)

def run():
    x=g.prep();idx=x.index
    ed=m.build_edges(x)
    rawL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);rawS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);z=rawL&rawS;rawL&=~z;rawS&=~z
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)
    pocL=pd.Series(ok&(c>poc),index=idx);pocS=pd.Series(ok&(c<poc),index=idx)
    f=vw.vwap_ladder(x,3,True);mm=vc.mk_masks(x,f)
    wL,wS=mm['WEEK_PLUS_ANY'];strict2L,strict2S=mm['STRICT2']
    # exact all-three strict reconstruction
    q=vc.components(x,f); allL=q['strictL'][0]&q['strictL'][1]&q['strictL'][2];allS=q['strictS'][0]&q['strictS'][1]&q['strictS'][2]
    initL=rawL&pocL&wL;initS=rawS&pocS&wS
    true=pd.Series(True,index=idx)
    specs={
      'AUTO_AFTER_BE':(true,true),
      'POC_ONLY':(pocL,pocS),
      'VWAP_WEEKPLUS':(wL,wS),
      'POC_WEEKPLUS':(pocL&wL,pocS&wS),
      'POC_STRICT2':(pocL&strict2L,pocS&strict2S),
      'POC_ALL3':(pocL&allL,pocS&allS),
      'RESIGNAL':(rawL,rawS),
      'RESIGNAL_POC':(rawL&pocL,rawS&pocS),
      'RESIGNAL_WEEKPLUS':(rawL&wL,rawS&wS),
      'RESIGNAL_POC_WEEKPLUS':(rawL&pocL&wL,rawS&pocS&wS),
    }
    trb=bnd(idx,g.START,g.TRAIN_END);vab=bnd(idx,g.TRAIN_END,g.VAL_END);hob=bnd(idx,g.VAL_END,g.END);fullb=bnd(idx,g.START,g.END)
    rows=[];cache={}
    for name,(aL,aS) in specs.items():
        arr=(o,h,lo,c,atr,slo,shi,initL.to_numpy(np.bool_),initS.to_numpy(np.bool_),aL.fillna(False).to_numpy(np.bool_),aS.fillna(False).to_numpy(np.bool_));cache[name]=arr
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],.65,1.25,4,18.,144));va=pack(vp.sim_profile(*arr,vab[0],vab[1],.65,1.25,4,18.,144))
        score=tr['ret']-1.5*tr['dd']+.85*va['ret']-1.25*va['dd']-50*abs(tr['avgR']-va['avgR'])
        rows.append((score,name,tr,va));print('SCREEN',name,'TR',round(tr['ret'],2),round(tr['pf'],3),round(tr['dd'],2),'VA',round(va['ret'],2),round(va['pf'],3),round(va['dd'],2),'ADDS',tr['adds'],va['adds'],flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);picks=[]
    picks.append([r for r in rows if r[1]=='AUTO_AFTER_BE'][0])
    for r in rows:
        if r[1]!='AUTO_AFTER_BE' and len(picks)<6:picks.append(r)
    prom=[]
    for score,name,tr,va in picks:
        arr=cache[name];ho=pack(vp.sim_profile(*arr,hob[0],hob[1],.65,1.25,4,18.,144));full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],.65,1.25,4,18.,144))
        prom.append({'mode':name,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'frozen_initial_entry':'BRK+EXP + causal24h POC + Riyadh SAME WEEK_PLUS_ANY','frozen_exit':'AF.65 BE1.25 max4 TP18 hold12h','selection':'add quality ranked on Train+Validation only; baseline + top5 exposed to Holdout','important':'AUTO_AFTER_BE is legacy behavior: once all open lots are protected, next bar may add without a fresh signal. Other modes require stated contextual continuation or re-signal.','promoted':prom},default=float));print('RESULT_JSON_END')
if __name__=='__main__':run()
