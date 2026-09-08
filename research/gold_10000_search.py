import json, math, itertools
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS
RISK=g.RISK

def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)))
    return int(ids[0]),int(ids[-1])

def pack(v): return vp.pack(v)

def score_pair(tr,va):
    # Selection is strictly Train+Validation. Reward geometric growth and OOS-like stability,
    # not full-period return. DD and PF floors prevent selecting a pure leverage-like tail.
    if tr['ret'] <= 0 or va['ret'] <= 0 or tr['pf'] < 1.10 or va['pf'] < 1.10:
        return -1e9
    ltr=math.log1p(tr['ret']/100.0); lva=math.log1p(va['ret']/100.0)
    stability=abs(tr['avgR']-va['avgR'])
    return 1.00*ltr + 1.35*lva - 0.018*tr['dd'] - 0.025*va['dd'] - 1.5*stability

def main():
    x=g.prep(); idx=x.index
    ed=m.build_edges(x)
    rL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False); rS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False)
    clash=rL&rS; rL&=~clash; rS&=~clash
    o=x.open.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); c=x.close.to_numpy(float)
    atr=x.atr14.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float); shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)

    # Frozen causal context from the current champion: 24h activity POC + Riyadh VWAP WEEK_PLUS_ANY.
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70); ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True); wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(rL&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_)
    S=(rS&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
    # Sequential adds are allowed only after all existing lots are protected at BE.
    # addL/addS=True means the campaign may recycle risk without demanding another base signal.
    addL=np.ones(len(x),dtype=np.bool_); addS=np.ones(len(x),dtype=np.bool_)
    arr=(o,h,lo,c,atr,slo,shi,L,S,addL,addS)

    trb=bounds(idx,g.START,g.TRAIN_END); vab=bounds(idx,g.TRAIN_END,g.VAL_END)
    hob=bounds(idx,g.VAL_END,g.END); fullb=bounds(idx,g.START,g.END)

    baseline={'af':.65,'be':1.25,'ml':4,'tp':20.,'mh':144}
    base_tr=pack(vp.sim_profile(*arr,trb[0],trb[1],.65,1.25,4,20.,144))
    base_va=pack(vp.sim_profile(*arr,vab[0],vab[1],.65,1.25,4,20.,144))
    base_ho=pack(vp.sim_profile(*arr,hob[0],hob[1],.65,1.25,4,20.,144))
    base_full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],.65,1.25,4,20.,144))
    print('BASE',base_full,flush=True)

    # Stage A: broad but economically constrained search. Fresh risk remains 0.36% per new lot.
    coarse=list(itertools.product([.55,.65,.75],[1.0,1.25,1.5],[4,6,8],[18.,22.,26.,30.,36.],[144,288,432]))
    rows=[]
    for n,(af,be,ml,tp,mh) in enumerate(coarse,1):
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],af,be,ml,tp,mh))
        va=pack(vp.sim_profile(*arr,vab[0],vab[1],af,be,ml,tp,mh))
        sc=score_pair(tr,va)
        if sc>-1e8: rows.append((sc,af,be,ml,tp,mh,tr,va))
        if n%50==0: print('COARSE',n,'/',len(coarse),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0])

    # Stage B: local plateau around the best three Train+Validation candidates only.
    refine=set()
    for z in rows[:3]:
        _,af,be,ml,tp,mh,_,_=z
        for a in [max(.45,af-.05),af,min(.90,af+.05)]:
          for b in [max(.75,be-.10),be,min(1.75,be+.10)]:
            for mm in [max(3,ml-1),ml,min(8,ml+1)]:
              for t in [max(14.,tp-2.),tp,tp+2.]:
                for hh in [max(96,mh-72),mh,min(576,mh+72)]:
                    refine.add((round(a,2),round(b,2),int(mm),float(t),int(hh)))
    seen={(r[1],r[2],r[3],r[4],r[5]) for r in rows}
    for n,(af,be,ml,tp,mh) in enumerate(sorted(refine),1):
        if (af,be,ml,tp,mh) in seen: continue
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],af,be,ml,tp,mh))
        va=pack(vp.sim_profile(*arr,vab[0],vab[1],af,be,ml,tp,mh))
        sc=score_pair(tr,va)
        if sc>-1e8: rows.append((sc,af,be,ml,tp,mh,tr,va))
    rows.sort(reverse=True,key=lambda z:z[0])

    # Freeze ranking, then reveal Holdout for top 12 only.
    promoted=[]
    for sc,af,be,ml,tp,mh,tr,va in rows[:12]:
        ho=pack(vp.sim_profile(*arr,hob[0],hob[1],af,be,ml,tp,mh))
        full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],af,be,ml,tp,mh))
        promoted.append({'score':sc,'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':mh*5/60,'train':tr,'val':va,'holdout':ho,'full':full,'over_10000':full['ret']>=10000})

    # Also report the highest full return only among the already-frozen promoted set.
    best_full=max(promoted,key=lambda z:z['full']['ret']) if promoted else None
    best_robust=max(promoted,key=lambda z:(z['holdout']['pf']>=1.10 and z['holdout']['ret']>0, z['score'])) if promoted else None
    reqR=math.log(101.0)/RISK
    print('RESULT_JSON_START')
    print(json.dumps({
      'risk_pct_fresh_lot':.36,
      'target_return_pct':10000,
      'target_final_multiple':101,
      'approx_required_compound_R':reqR,
      'strategy':'BRK+EXP + 24h causal activity POC + Riyadh WEEK_PLUS_ANY VWAP + sequential risk recycling',
      'risk_rule':'A new 0.36% lot is permitted only after all older live lots have moved to BE on a completed bar; no increase in per-lot fresh risk.',
      'selection':'coarse + local plateau uses Train+Validation only; Holdout and Full revealed only after top-12 ranking is frozen',
      'baseline':{'params':baseline,'train':base_tr,'val':base_va,'holdout':base_ho,'full':base_full},
      'coarse_grid_size':len(coarse),'refine_grid_size':len(refine),'promoted':promoted,
      'best_full_among_frozen':best_full,'best_robust_among_frozen':best_robust,
      'limitations':['M1 OHLC resampled to M5; not bid/ask tick execution','tick-volume activity POC, not COMEX GC true volume-at-price','sequential adds do not require a fresh BRK/EXP signal; this is intentionally aggressive and must be separately validated against a fresh-signal variant','0.08R modeled cost per completed lot','no Holdout parameter selection']
    },default=float))
    print('RESULT_JSON_END')

if __name__=='__main__': main()
