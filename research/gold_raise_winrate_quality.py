import json, math, itertools
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_10000_equity_risk as er

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS;er.g.URLS=g.URLS

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])
def pack(v):return er.pack(v)

def union(ed,names,idx):
    L=pd.Series(False,index=idx);S=L.copy()
    for nm in names:L|=ed[nm][0];S|=ed[nm][1]
    q=L&S;return L&~q,S&~q

def quality_masks(x):
    # All are causal because x columns are available only after completed M5/M15/H1 bars.
    zdirL=(x.z48>0)&(x.z84>0); zdirS=(x.z48<0)&(x.z84<0)
    zstrongL=(x.z48>.5)&(x.z84>0); zstrongS=(x.z48<-.5)&(x.z84<0)
    zbreakL=(x.z48>x.z48_prev10max)&(x.z84>x.z84_prev10max)&(x.z48>0)&(x.z84>0)
    zbreakS=(x.z48<x.z48_prev10min)&(x.z84<x.z84_prev10min)&(x.z48<0)&(x.z84<0)
    flow09=(x.dv>x.dvma30)&(x.rqvol>.9)
    flow12=(x.dv>x.dvma30)&(x.rqvol>1.2)
    flow15=(x.dv>x.dvma30)&(x.rqvol>1.5)
    mtfzL=(x.m15_z48>0)&(x.m15_z84>0)&(x.h1_z48>.5)&(x.h1_z84>0)
    mtfzS=(x.m15_z48<0)&(x.m15_z84<0)&(x.h1_z48<-.5)&(x.h1_z84<0)
    return {
      'NONE':(pd.Series(True,index=x.index),pd.Series(True,index=x.index)),
      'ZDIR':(zdirL,zdirS),
      'ZSTRONG':(zstrongL,zstrongS),
      'ZBREAK':(zbreakL,zbreakS),
      'FLOW09':(flow09,flow09),
      'FLOW12':(flow12,flow12),
      'FLOW15':(flow15,flow15),
      'ZDIR_FLOW09':(zdirL&flow09,zdirS&flow09),
      'ZSTRONG_FLOW09':(zstrongL&flow09,zstrongS&flow09),
      'MTFZ':(mtfzL,mtfzS),
      'MTFZ_FLOW09':(mtfzL&flow09,mtfzS&flow09),
      'MTFZ_FLOW12':(mtfzL&flow12,mtfzS&flow12),
    }

def score(tr,va):
    if tr['lots']<150 or va['lots']<50 or tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.03 or va['pf']<1.03:return -1e9
    minwr=min(tr['wr'],va['wr'])
    return 6*minwr + 8*math.log1p(tr['ret']/100)+12*math.log1p(va['ret']/100)-.35*tr['dd']-.5*va['dd']-18*abs(tr['avgR']-va['avgR'])

def main():
    x=g.prep();idx=x.index;ed=m.build_edges(x)
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc);pocL=pd.Series(ok&(c>poc),index=idx);pocS=pd.Series(ok&(c<poc),index=idx)
    vf=vw.vwap_ladder(x,3,True);vms=vc.mk_masks(x,vf);qms=quality_masks(x)
    sigs={'UNION4':('BRK','EXP','PULL','FRACTAL'),'EXP_PULL':('EXP','PULL'),'UNION3':('BRK','EXP','PULL')}
    vgates=['WEEK_PLUS_ANY','STRICT2','DW_REL_PRICE2']
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    rows=[];cache={}
    for sname,names in sigs.items():
      bL,bS=union(ed,names,idx)
      for vg in vgates:
        vL,vS=vms[vg]
        for qname,(qL,qS) in qms.items():
          L=(bL&pocL&vL&qL).fillna(False);S=(bS&pocS&vS&qS).fillna(False)
          arr=(o,h,lo,c,atr,slo,shi,L.to_numpy(np.bool_),S.to_numpy(np.bool_));cache[(sname,vg,qname)]=arr
          for af,be,ml,tp in itertools.product([.55,.60,.65],[.75,1.0,1.25],[2,3],[2.,3.,4.,5.,6.,8.,10.,12.]):
            tr=pack(er.sim_equity(*arr,trb[0],trb[1],af,be,ml,tp,144));va=pack(er.sim_equity(*arr,vab[0],vab[1],af,be,ml,tp,144));sc=score(tr,va)
            if sc>-1e8:rows.append((sc,sname,vg,qname,af,be,ml,tp,tr,va))
      print('DONE',sname,flush=True)
    rows.sort(reverse=True,key=lambda z:z[0])
    picks=[];seen=set()
    def add(r):
      k=r[1:8]
      if k not in seen:seen.add(k);picks.append(r)
    for r in rows[:12]:add(r)
    # Freeze high-WR frontiers at increasing return floors before Holdout reveal.
    for trfloor,vafloor in [(20,10),(50,15),(100,25),(200,40),(300,50)]:
      e=[r for r in rows if r[8]['ret']>=trfloor and r[9]['ret']>=vafloor and r[8]['pf']>=1.08 and r[9]['pf']>=1.08]
      e.sort(key=lambda r:min(r[8]['wr'],r[9]['wr']),reverse=True)
      for r in e[:5]:add(r)
    out=[]
    for sc,sn,vg,qn,af,be,ml,tp,tr,va in picks[:30]:
      arr=cache[(sn,vg,qn)];ho=pack(er.sim_equity(*arr,hob[0],hob[1],af,be,ml,tp,144));full=pack(er.sim_equity(*arr,fullb[0],fullb[1],af,be,ml,tp,144))
      out.append({'signal':sn,'vwap_gate':vg,'quality':qn,'af':af,'beR':be,'max_lots':ml,'tpR':tp,'train':tr,'val':va,'holdout':ho,'full':full,'score':sc})
    valid=[r for r in out if r['holdout']['ret']>0 and r['holdout']['pf']>=1.03]
    def minwr(r):return min(r['train']['wr'],r['val']['wr'],r['holdout']['wr'])
    bestwr=max(valid,key=minwr) if valid else None
    ge1000=[r for r in valid if r['full']['ret']>=1000]
    bestwr1000=max(ge1000,key=minwr) if ge1000 else None
    ge500=[r for r in valid if r['full']['ret']>=500]
    bestwr500=max(ge500,key=minwr) if ge500 else None
    print('RESULT_JSON_START');print(json.dumps({'risk':'0.36% current mark-to-market equity per fresh lot; older lots BE before new risk','selection':'Train+Validation only; Holdout frozen shortlist','quality_filters':list(qms.keys()),'best_robust_winrate':bestwr,'best_robust_winrate_full_ge_500pct':bestwr500,'best_robust_winrate_full_ge_1000pct':bestwr1000,'shortlist':out,'baseline':{'wr_full':17.39,'wr_holdout':16.32,'ret_full':4035.74}},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
