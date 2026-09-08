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
def sc(tr,va):
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.10 or va['pf']<1.10:return -1e9
    # Robustness-first. No Holdout/Full information in ranking.
    return math.log1p(tr['ret']/100)+1.45*math.log1p(va['ret']/100)-.018*tr['dd']-.028*va['dd']-1.75*abs(tr['avgR']-va['avgR'])

def main():
    x=g.prep();idx=x.index;ed=m.build_edges(x)
    names=('BRK','EXP','PULL','FRACTAL')
    L=pd.Series(False,index=idx);S=L.copy()
    for nm in names:L|=ed[nm][0];S|=ed[nm][1]
    clash=L&S;L&=~clash;S&=~clash
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
    add=np.ones(len(x),dtype=np.bool_);arr=(o,h,lo,c,atr,slo,shi,L,S,add,add)
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    afs=[round(v,3) for v in np.arange(.50,.701,.025)]
    bes=[round(v,2) for v in np.arange(1.15,1.401,.05)]
    mls=[2,3,4];tps=[float(v) for v in range(20,31)];mhs=[96,120,144,180,216]
    grid=list(itertools.product(afs,bes,mls,tps,mhs));rows=[]
    for n,(af,be,ml,tp,mh) in enumerate(grid,1):
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],af,be,ml,tp,mh));va=pack(vp.sim_profile(*arr,vab[0],vab[1],af,be,ml,tp,mh));s=sc(tr,va)
        if s>-1e8:rows.append((s,af,be,ml,tp,mh,tr,va))
        if n%1000==0:print('GRID',n,'/',len(grid),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0])
    promoted=[]
    for s,af,be,ml,tp,mh,tr,va in rows[:30]:
        ho=pack(vp.sim_profile(*arr,hob[0],hob[1],af,be,ml,tp,mh));full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],af,be,ml,tp,mh))
        promoted.append({'score':s,'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':mh*5/60,'train':tr,'val':va,'holdout':ho,'full':full,'over_10000':full['ret']>=10000})
    # Plateau summary among frozen top30, not a new selection rule.
    above=[z for z in promoted if z['full']['ret']>=10000]
    print('RESULT_JSON_START');print(json.dumps({'risk_pct_fresh_lot':.36,'edges':list(names),'grid_size':len(grid),'selection':'Dense grid ranked strictly Train+Validation; Holdout/Full revealed only top30','required_compound_R_10000':math.log(101)/g.RISK,'promoted':promoted,'count_over_10000_among_frozen_top30':len(above),'best_full_among_frozen_top30':max(promoted,key=lambda z:z['full']['ret']) if promoted else None,'best_score':promoted[0] if promoted else None,'limitations':['Repeated research means original Holdout is no longer pristine; final candidate must be checked on external GetData forward','auto adds after BE without fresh signal','M1 OHLC->M5, 0.08R modeled cost per lot','activity POC uses tick volume']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
