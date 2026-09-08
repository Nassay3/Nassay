import json
import numpy as np
import pandas as pd
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

def run():
    x=g.prep(); idx=x.index
    ed=m.build_edges(x)
    rawL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False); rawS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False)
    z=rawL&rawS; rawL&=~z; rawS&=~z
    o=x.open.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); c=x.close.to_numpy(float)
    atr=x.atr14.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float); shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    print('PROFILE_BUILD_24H',flush=True)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70); ok=np.isfinite(poc)
    pocL=pd.Series(ok&(c>poc),index=idx); pocS=pd.Series(ok&(c<poc),index=idx)
    f=vw.vwap_ladder(x,3,True); masks=vc.mk_masks(x,f)
    wL,wS=masks['WEEK_PLUS_ANY']
    L=(rawL&pocL&wL).to_numpy(np.bool_); S=(rawS&pocS&wS).to_numpy(np.bool_)
    ones=np.ones(len(x),dtype=np.bool_)
    arr=(o,h,lo,c,atr,slo,shi,L,S,ones,ones)
    trb=bounds(idx,g.START,g.TRAIN_END); vab=bounds(idx,g.TRAIN_END,g.VAL_END); hob=bounds(idx,g.VAL_END,g.END); fullb=bounds(idx,g.START,g.END)

    # Coarse sensitivity around the frozen champion. No fine optimization.
    afs=(.65,.75,.85)
    bes=(1.0,1.25,1.5)
    maxlots=(3,4,5)
    tps=(16.,18.,20.,22.)
    holds=(96,144,216)  # 8h,12h,18h M5 bars
    # Stage 1 varies one dimension at a time around baseline, plus a small set of economically sensible intersections.
    specs=set()
    base=(.75,1.25,4,18.,144); specs.add(base)
    for a in afs: specs.add((a,1.25,4,18.,144))
    for b in bes: specs.add((.75,b,4,18.,144))
    for ml in maxlots: specs.add((.75,1.25,ml,18.,144))
    for tp in tps: specs.add((.75,1.25,4,tp,144))
    for hold in holds: specs.add((.75,1.25,4,18.,hold))
    # Cross only nearby settings, deliberately avoiding a 108-way blind grid.
    for tp in (18.,20.,22.):
      for b in (1.0,1.25,1.5): specs.add((.75,b,4,tp,144))
    for tp in (18.,20.,22.):
      for a in (.65,.75,.85): specs.add((a,1.25,4,tp,144))
    for tp in (18.,20.,22.):
      for ml in (3,4,5): specs.add((.75,1.25,ml,tp,144))
    for tp in (18.,20.,22.):
      for hold in (96,144,216): specs.add((.75,1.25,4,tp,hold))

    rows=[]; cache={}
    for af,be,ml,tp,hold in sorted(specs):
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],af,be,ml,tp,hold)); va=pack(vp.sim_profile(*arr,vab[0],vab[1],af,be,ml,tp,hold))
        # Reward return/PF through return, penalize DD and regime mismatch. Holdout never participates.
        score=tr['ret']-1.5*tr['dd']+.85*va['ret']-1.25*va['dd']-50*abs(tr['avgR']-va['avgR'])
        key=(af,be,ml,tp,hold); cache[key]=(tr,va); rows.append((score,key,tr,va))
        print('SCREEN',key,'TR',round(tr['ret'],2),round(tr['pf'],3),round(tr['dd'],2),'VA',round(va['ret'],2),round(va['pf'],3),round(va['dd'],2),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0])
    picked=[]
    base_row=[r for r in rows if r[1]==base][0]; picked.append(base_row)
    for r in rows:
        if r[1]!=base and len(picked)<9: picked.append(r)
    promoted=[]
    for score,key,tr,va in picked:
        af,be,ml,tp,hold=key
        ho=pack(vp.sim_profile(*arr,hob[0],hob[1],af,be,ml,tp,hold)); full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],af,be,ml,tp,hold))
        promoted.append({'af':af,'beR':be,'maxlots':ml,'tpR':tp,'hold_bars':hold,'hold_hours':hold*5/60,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START')
    print(json.dumps({'risk_pct':.36,'frozen_entry':'BRK+EXP + causal 24h POC_GATE + Riyadh SAME-session VWAP WEEK_PLUS_ANY','week_plus_any':'strict weekly VWAP alignment AND (strict daily OR strict session alignment)','selection':'coarse parameter plateau ranked on Train+Validation only; Holdout exposed for baseline + top8','baseline':{'af':.75,'beR':1.25,'maxlots':4,'tpR':18.,'hold_hours':12},'screen':[{'score':s,'af':k[0],'beR':k[1],'maxlots':k[2],'tpR':k[3],'hold_bars':k[4],'train':tr,'val':va} for s,k,tr,va in rows],'promoted':promoted,'warning':'No fine-grid optimization; risk per unprotected new lot remains 0.36% and adds occur only after existing lots are protected.'},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__': run()
