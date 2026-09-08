import json, math, itertools
import numpy as np
import gold_m5_discovery_spike as g
import gold_champion_execution_stress as s


def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])

def score(parts):
    # All four Train/Validation x base/stress cells must have positive expectancy and PF>1.05.
    for q in parts:
        if q['ret']<=0 or q['pf']<1.05:return -1e12
    trb,vab,trs,vas=parts
    # Reward stress-resistant compounded return, then OOS consistency; penalize drawdown.
    z=(math.log1p(trb['ret']/100)+1.5*math.log1p(vab['ret']/100)+
       1.15*math.log1p(trs['ret']/100)+1.65*math.log1p(vas['ret']/100)-
       .014*trb['dd']-.022*vab['dd']-.018*trs['dd']-.028*vas['dd']-
       1.2*abs(trs['avgR']-vas['avgR']))
    return z

def main():
    x,arr=s.build();idx=x.index
    tr=bounds(idx,g.START,g.TRAIN_END);va=bounds(idx,g.TRAIN_END,g.VAL_END);ho=bounds(idx,g.VAL_END,g.END);full=bounds(idx,g.START,g.END)
    afs=[.40,.45,.50,.55,.60,.65,.70,.75,.85]
    bes=[.75,1.0,1.25,1.5,1.75,2.0]
    mls=[2,3,4]
    tps=[8.,10.,12.,15.,18.,20.,24.,28.,32.,36.]
    holds=[72,108,144,216] # 6h, 9h, 12h, 18h
    grid=list(itertools.product(afs,bes,mls,tps,holds));rows=[]
    # warm
    s.sim_stress(*arr,tr[0],min(tr[0]+1000,tr[1]),.6,1.25,3,20.,144,.08,0.,1,1)
    for n,(af,be,ml,tp,mh) in enumerate(grid,1):
        trb=s.pack(s.sim_stress(*arr,tr[0],tr[1],af,be,ml,tp,mh,.08,0.,1,1))
        vab=s.pack(s.sim_stress(*arr,va[0],va[1],af,be,ml,tp,mh,.08,0.,1,1))
        trs=s.pack(s.sim_stress(*arr,tr[0],tr[1],af,be,ml,tp,mh,.15,.05,1,1))
        vas=s.pack(s.sim_stress(*arr,va[0],va[1],af,be,ml,tp,mh,.15,.05,1,1))
        sc=score((trb,vab,trs,vas))
        if sc>-1e11:rows.append((sc,af,be,ml,tp,mh,trb,vab,trs,vas))
        if n%1000==0:print('GRID',n,'/',len(grid),'qualified',len(rows),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);out=[]
    for z in rows[:20]:
        sc,af,be,ml,tp,mh,trb,vab,trs,vas=z
        hob=s.pack(s.sim_stress(*arr,ho[0],ho[1],af,be,ml,tp,mh,.08,0.,1,1))
        hos=s.pack(s.sim_stress(*arr,ho[0],ho[1],af,be,ml,tp,mh,.15,.05,1,1))
        fb=s.pack(s.sim_stress(*arr,full[0],full[1],af,be,ml,tp,mh,.08,0.,1,1))
        fs=s.pack(s.sim_stress(*arr,full[0],full[1],af,be,ml,tp,mh,.15,.05,1,1))
        out.append({'score':sc,'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':mh*5/60,
                    'train_base':trb,'val_base':vab,'train_stress':trs,'val_stress':vas,
                    'holdout_base':hob,'holdout_stress':hos,'full_base':fb,'full_stress':fs})
    print('RESULT_JSON_START')
    print(json.dumps({'architecture':'UNION4 + activity POC + Riyadh WEEK_PLUS_ANY VWAP; every add requires fresh same-direction alpha signal','risk':'.36% current MTM equity per fresh lot','grid_size':len(grid),'qualified_train_val_both_scenarios':len(rows),'selection':'Rank strictly Train+Validation across BOTH base(.08R) and stress(.15R cost+.05R stop slip); Holdout/full revealed only top20','top20':out,'guardrail':'Any later choice based on Holdout/full must be labeled post-selection; preferred candidate is top score unless catastrophic Holdout failure.'},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
