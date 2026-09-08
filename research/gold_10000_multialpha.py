import json, math, itertools
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
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])
def pack(v):return vp.pack(v)
def score(tr,va):
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.08 or va['pf']<1.08:return -1e9
    return math.log1p(tr['ret']/100)+1.35*math.log1p(va['ret']/100)-.018*tr['dd']-.025*va['dd']-1.5*abs(tr['avgR']-va['avgR'])

def main():
    x=g.prep();idx=x.index;ed=m.build_edges(x)
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    gateL=wL&pd.Series(ok&(c>poc),index=idx);gateS=wS&pd.Series(ok&(c<poc),index=idx)
    combos=[('BRK','EXP'),('BRK','EXP','PULL'),('BRK','EXP','FRACTAL'),('BRK','EXP','PULL','FRACTAL'),('BRK','PULL'),('BRK','FRACTAL'),('EXP','PULL'),('EXP','FRACTAL')]
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    add=np.ones(len(x),dtype=np.bool_);rows=[]
    for names in combos:
        L=pd.Series(False,index=idx);S=L.copy()
        for nm in names:
            L|=ed[nm][0];S|=ed[nm][1]
        clash=L&S;L&=~clash;S&=~clash;L&=gateL;S&=gateS
        arr=(o,h,lo,c,atr,slo,shi,L.to_numpy(np.bool_),S.to_numpy(np.bool_),add,add)
        for af,be,ml,tp in itertools.product([.55,.60,.65,.70],[1.15,1.25,1.35],[3,4],[18.,20.,22.,24.,26.]):
            tr=pack(vp.sim_profile(*arr,trb[0],trb[1],af,be,ml,tp,144));va=pack(vp.sim_profile(*arr,vab[0],vab[1],af,be,ml,tp,144));sc=score(tr,va)
            if sc>-1e8:rows.append((sc,names,af,be,ml,tp,tr,va,arr))
        print('DONE_COMBO',names,flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);prom=[]
    # Freeze top 15 by Train+Validation before revealing Holdout.
    for sc,names,af,be,ml,tp,tr,va,arr in rows[:15]:
        ho=pack(vp.sim_profile(*arr,hob[0],hob[1],af,be,ml,tp,144));full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],af,be,ml,tp,144))
        prom.append({'edges':list(names),'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'score':sc,'train':tr,'val':va,'holdout':ho,'full':full,'over_10000':full['ret']>=10000})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct_fresh_lot':.36,'strategy':'Multi-alpha starts + 24h causal POC + Riyadh WEEK_PLUS_ANY + sequential risk recycling','selection':'All edge/parameter selection Train+Validation only; Holdout revealed top15','tested_combos':[list(x) for x in combos],'grid_count':len(combos)*4*3*2*5,'promoted':prom,'best_full_among_frozen':max(prom,key=lambda z:z['full']['ret']) if prom else None,'required_compound_R_10000':math.log(101)/g.RISK,'limitations':['PULL/FRACTAL definitions inherited frozen discovery code','auto sequential adds after BE do not require fresh alpha signal','M1 OHLC resampled M5; 0.08R cost/lot','POC uses tick activity not COMEX volume']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
