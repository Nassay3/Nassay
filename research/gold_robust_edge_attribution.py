import json, math, itertools
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_champion_execution_stress as s

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv'];m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS;s.g.URLS=g.URLS
NAMES=('BRK','EXP','PULL','FRACTAL')

def bounds(idx,a,b):
 z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])
def score(trb,vab,trs,vas):
 for q in (trb,vab,trs,vas):
  if q['ret']<=0 or q['pf']<1.05:return -1e12
 return math.log1p(trb['ret']/100)+1.5*math.log1p(vab['ret']/100)+1.15*math.log1p(trs['ret']/100)+1.65*math.log1p(vas['ret']/100)-.014*trb['dd']-.022*vab['dd']-.018*trs['dd']-.028*vas['dd']-1.2*abs(trs['avgR']-vas['avgR'])

def main():
 x=g.prep();idx=x.index;ed=m.build_edges(x)
 o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
 slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
 poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc);f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
 tr=bounds(idx,g.START,g.TRAIN_END);va=bounds(idx,g.TRAIN_END,g.VAL_END);ho=bounds(idx,g.VAL_END,g.END);full=bounds(idx,g.START,g.END)
 af,be,ml,tp,mh=.65,1.75,2,32.,216
 rows=[]
 for r in range(1,5):
  for subset in itertools.combinations(NAMES,r):
   L=pd.Series(False,index=idx);S=pd.Series(False,index=idx)
   for nm in subset:L|=ed[nm][0];S|=ed[nm][1]
   clash=L&S;L&=~clash;S&=~clash
   L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
   arr=(o,h,lo,c,atr,slo,shi,L,S)
   trb=s.pack(s.sim_stress(*arr,tr[0],tr[1],af,be,ml,tp,mh,.08,0.,1,1));vab=s.pack(s.sim_stress(*arr,va[0],va[1],af,be,ml,tp,mh,.08,0.,1,1))
   trs=s.pack(s.sim_stress(*arr,tr[0],tr[1],af,be,ml,tp,mh,.15,.05,1,1));vas=s.pack(s.sim_stress(*arr,va[0],va[1],af,be,ml,tp,mh,.15,.05,1,1));sc=score(trb,vab,trs,vas)
   rows.append((sc,subset,arr,trb,vab,trs,vas))
 rows.sort(reverse=True,key=lambda z:z[0]);out=[]
 for sc,subset,arr,trb,vab,trs,vas in rows:
  hob=s.pack(s.sim_stress(*arr,ho[0],ho[1],af,be,ml,tp,mh,.08,0.,1,1));hos=s.pack(s.sim_stress(*arr,ho[0],ho[1],af,be,ml,tp,mh,.15,.05,1,1));fb=s.pack(s.sim_stress(*arr,full[0],full[1],af,be,ml,tp,mh,.08,0.,1,1));fs=s.pack(s.sim_stress(*arr,full[0],full[1],af,be,ml,tp,mh,.15,.05,1,1))
  out.append({'edges':list(subset),'score':sc,'train_base':trb,'val_base':vab,'train_stress':trs,'val_stress':vas,'holdout_base':hob,'holdout_stress':hos,'full_base':fb,'full_stress':fs})
 print('RESULT_JSON_START');print(json.dumps({'frozen_params':{'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':18},'risk':'.36% MTM equity per fresh lot','selection':'All 15 edge subsets ranked using Train+Validation base+stress only. Holdout/full shown after ranking.','ranking':out,'guardrail':'Top-ranked subset is methodological choice unless catastrophic external/tick failure; do not select lower subset using Holdout.'},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
