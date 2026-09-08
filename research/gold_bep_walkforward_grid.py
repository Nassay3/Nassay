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
EDGES=('BRK','EXP','PULL')
FOLDS=[('ERA1',pd.Timestamp('2021-09-08',tz='UTC'),pd.Timestamp('2023-01-01',tz='UTC')),('ERA2',pd.Timestamp('2023-01-01',tz='UTC'),pd.Timestamp('2024-01-01',tz='UTC')),('ERA3',pd.Timestamp('2024-01-01',tz='UTC'),pd.Timestamp('2025-01-01',tz='UTC'))]

def bounds(idx,a,b):
 z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])
def build():
 x=g.prep();idx=x.index;ed=m.build_edges(x);L=pd.Series(False,index=idx);S=pd.Series(False,index=idx)
 for nm in EDGES:L|=ed[nm][0];S|=ed[nm][1]
 clash=L&S;L&=~clash;S&=~clash
 o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
 slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
 poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc);f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
 L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
 return x,(o,h,lo,c,atr,slo,shi,L,S)
def rank_score(cells):
 # Six cells = 3 eras x base/stress. Fail closed on any nonpositive return or PF <= 1.05.
 for q in cells:
  if q['ret']<=0 or q['pf']<=1.05:return -1e12
 logs=[math.log1p(q['ret']/100) for q in cells];worst=min(logs);mean=sum(logs)/len(logs);dds=[q['dd'] for q in cells]
 # Weight the weakest regime heavily; then geometric consistency; penalize worst DD.
 return 2.2*worst+mean-.018*max(dds)-.006*sum(dds)/len(dds)
def main():
 x,arr=build();idx=x.index;fb=[(n,bounds(idx,a,b)) for n,a,b in FOLDS];ho=bounds(idx,pd.Timestamp('2025-01-01',tz='UTC'),g.END);full=bounds(idx,g.START,g.END)
 afs=[.50,.65,.80];bes=[1.50,1.75,2.00,2.25];mls=[2,3];tps=[24.,28.,32.,36.,40.];holds=[144,216,288]
 grid=list(itertools.product(afs,bes,mls,tps,holds));rows=[]
 s.sim_stress(*arr,fb[0][1][0],min(fb[0][1][0]+1000,fb[0][1][1]),.65,1.75,2,32.,216,.08,0.,1,1)
 for af,be,ml,tp,mh in grid:
  cells=[];details={}
  for nm,b in fb:
   base=s.pack(s.sim_stress(*arr,b[0],b[1],af,be,ml,tp,mh,.08,0.,1,1));stress=s.pack(s.sim_stress(*arr,b[0],b[1],af,be,ml,tp,mh,.15,.05,1,1));cells.extend([base,stress]);details[nm]={'base':base,'stress':stress}
  sc=rank_score(cells)
  if sc>-1e11:rows.append((sc,af,be,ml,tp,mh,details))
 rows.sort(reverse=True,key=lambda z:z[0]);out=[]
 for sc,af,be,ml,tp,mh,details in rows[:15]:
  hob=s.pack(s.sim_stress(*arr,ho[0],ho[1],af,be,ml,tp,mh,.08,0.,1,1));hos=s.pack(s.sim_stress(*arr,ho[0],ho[1],af,be,ml,tp,mh,.15,.05,1,1));fullb=s.pack(s.sim_stress(*arr,full[0],full[1],af,be,ml,tp,mh,.08,0.,1,1));fulls=s.pack(s.sim_stress(*arr,full[0],full[1],af,be,ml,tp,mh,.15,.05,1,1))
  out.append({'score':sc,'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':mh*5/60,'eras':details,'holdout_2025plus_base':hob,'holdout_2025plus_stress':hos,'full_base':fullb,'full_stress':fulls})
 print('RESULT_JSON_START');print(json.dumps({'edges':list(EDGES),'risk':'.36% MTM equity/fresh lot; all adds require fresh same-direction signal','grid_size':len(grid),'qualified_all_3_eras_both_costs':len(rows),'selection':'Rank ONLY 3 pre-2025 eras, each required positive with PF>1.05 under base .08R and stress .15R+.05R stop slip; 2025+ exposed only top15','ranking':out,'warning':'Repeated research on same historical source creates meta-overfit risk; external bid/ask tick validation remains decisive.'},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
