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

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b))); return int(z[0]),int(z[-1])
def pack(v): return vp.pack(v)

def combine(ed,names,votes,idx):
    lc=np.zeros(len(idx),np.int8); sc=np.zeros(len(idx),np.int8)
    for nm in names:
        lc += ed[nm][0].to_numpy(np.int8)
        sc += ed[nm][1].to_numpy(np.int8)
    L=pd.Series(lc>=votes,index=idx); S=pd.Series(sc>=votes,index=idx)
    clash=L&S; return L&~clash,S&~clash

def robust_score(tr,va):
    # Win-rate is primary, but reject fragile/negative expectancy variants.
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.05 or va['pf']<1.05: return -1e9
    minwr=min(tr['wr'],va['wr'])
    return 4.0*minwr + 12*math.log1p(tr['ret']/100) + 18*math.log1p(va['ret']/100) - .45*tr['dd'] - .65*va['dd'] - 25*abs(tr['avgR']-va['avgR'])

def main():
    x=g.prep(); idx=x.index; ed=m.build_edges(x)
    o=x.open.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); c=x.close.to_numpy(float); atr=x.atr14.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float); shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70); ok=np.isfinite(poc)
    pocL=pd.Series(ok&(c>poc),index=idx); pocS=pd.Series(ok&(c<poc),index=idx)
    f=vw.vwap_ladder(x,3,True); vm=vc.mk_masks(x,f)
    sigspec=[
      ('UNION4',('BRK','EXP','PULL','FRACTAL'),1),
      ('VOTE2_4',('BRK','EXP','PULL','FRACTAL'),2),
      ('UNION3',('BRK','EXP','PULL'),1),
      ('VOTE2_3',('BRK','EXP','PULL'),2),
      ('EXP_PULL',('EXP','PULL'),1),
      ('BRK_EXP',('BRK','EXP'),1),
    ]
    gates=['WEEK_PLUS_ANY','STRICT2','REL2_PRICE2','DW_REL_PRICE2']
    trb=bounds(idx,g.START,g.TRAIN_END); vab=bounds(idx,g.TRAIN_END,g.VAL_END); hob=bounds(idx,g.VAL_END,g.END); fullb=bounds(idx,g.START,g.END)
    add=np.ones(len(x),dtype=np.bool_); rows=[]; cache={}
    for sname,names,votes in sigspec:
        bL,bS=combine(ed,names,votes,idx)
        for gname in gates:
            qL,qS=vm[gname]
            L=bL&pocL&qL; S=bS&pocS&qS
            arr=(o,h,lo,c,atr,slo,shi,L.to_numpy(np.bool_),S.to_numpy(np.bool_),add,add)
            cache[(sname,gname)]=arr
            for af,be,ml,tp in itertools.product([.55,.60,.65,.70],[.75,1.0,1.25],[2,3],[6.,8.,10.,12.,14.,16.,18.]):
                tr=pack(vp.sim_profile(*arr,trb[0],trb[1],af,be,ml,tp,144)); va=pack(vp.sim_profile(*arr,vab[0],vab[1],af,be,ml,tp,144)); sc=robust_score(tr,va)
                if sc>-1e8: rows.append((sc,sname,gname,af,be,ml,tp,tr,va))
        print('DONE_SIGNAL',sname,flush=True)
    rows.sort(reverse=True,key=lambda z:z[0])
    # Freeze multiple frontiers before exposing holdout: top robust score, top WR with >=100%, >=500%, >=1000% train+val combined proxy.
    picks=[]; seen=set()
    def addpick(r):
        key=r[1:7]
        if key not in seen: seen.add(key); picks.append(r)
    for r in rows[:10]: addpick(r)
    # High-WR frontiers with minimum Train and Validation quality.
    for floors in [(50,20),(100,30),(200,40),(300,50)]:
        eligible=[r for r in rows if r[7]['ret']>=floors[0] and r[8]['ret']>=floors[1] and r[7]['pf']>=1.1 and r[8]['pf']>=1.1]
        eligible.sort(key=lambda r:min(r[7]['wr'],r[8]['wr']),reverse=True)
        for r in eligible[:4]: addpick(r)
    promoted=[]
    for sc,sname,gname,af,be,ml,tp,tr,va in picks[:24]:
        arr=cache[(sname,gname)]
        ho=pack(vp.sim_profile(*arr,hob[0],hob[1],af,be,ml,tp,144)); full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],af,be,ml,tp,144))
        promoted.append({'signal':sname,'vwap_gate':gname,'af':af,'beR':be,'max_lots':ml,'tpR':tp,'score':sc,'train':tr,'val':va,'holdout':ho,'full':full})
    # Report Pareto-like champions after holdout reveal, but do NOT use holdout to retune parameters beyond this report.
    valid=[r for r in promoted if r['holdout']['ret']>0 and r['holdout']['pf']>=1.05]
    by_wr=max(valid,key=lambda r:min(r['train']['wr'],r['val']['wr'],r['holdout']['wr'])) if valid else None
    over1000=[r for r in valid if r['full']['ret']>=1000]
    by_wr_1000=max(over1000,key=lambda r:min(r['train']['wr'],r['val']['wr'],r['holdout']['wr'])) if over1000 else None
    by_return=max(valid,key=lambda r:r['full']['ret']) if valid else None
    print('RESULT_JSON_START')
    print(json.dumps({'risk_pct_fresh_lot':.36,'goal':'raise lot win-rate while preserving robust positive expectancy','selection':'parameter ranking uses Train+Validation only; Holdout exposed only for frozen shortlist','tested_signal_modes':[x[0] for x in sigspec],'tested_vwap_gates':gates,'tp_grid_R':[6,8,10,12,14,16,18],'promoted':promoted,'highest_robust_winrate':by_wr,'highest_robust_winrate_with_full_return_ge_1000pct':by_wr_1000,'highest_return_shortlist':by_return,'baseline_reference':{'full_ret_pct':4035.7429,'full_wr_pct':17.3933,'holdout_wr_pct':16.3209,'tpR':24},'warning':'Win rate is measured per closed lot. Lower TP mechanically raises WR, so PF, return, DD and untouched Holdout are kept alongside it.'},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__': main()
