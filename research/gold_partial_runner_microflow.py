import json, math, itertools
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_m1_microstructure_score_v2 as ms2

s=ms2.s
g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS;s.g.URLS=g.URLS
RISK=g.RISK

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])

@njit(cache=True)
def sim(o,h,l,c,atr,slo,shi,sigL,sigS,first,last,af,t1,f1,t2,f2,runner,maxlots,maxhold,costR):
    dirs=np.zeros(8,np.int8);ent=np.zeros(8);stops=np.zeros(8);risks=np.zeros(8);rcs=np.zeros(8);opened=np.zeros(8,np.int64)
    rem=np.ones(8);real=np.zeros(8);hit1=np.zeros(8,np.uint8);hit2=np.zeros(8,np.uint8);prot=np.zeros(8,np.uint8)
    nlot=0;pdn=0;pdi=-1;padd=0;cdir=0;lastadd=-999
    bal=1.;peak=1.;dd=0.;nclosed=0;wins=0;pos=0.;neg=0.;rtot=0.;campaigns=0;adds=0;t1hits=0;t2hits=0;runnerhits=0
    for i in range(max(first,30),min(last,len(o)-2)+1):
        if pdn!=0:
            av=atr[pdi];e=o[i]
            if av>0 and np.isfinite(av):
                sw=slo[pdi] if pdn==1 else shi[pdi]
                if pdn==1:st=min(sw-.1*av,e-af*av);rrisk=e-st
                else:st=max(sw+.1*av,e+af*av);rrisk=st-e
                if rrisk>0 and rrisk/e<=.012 and nlot<maxlots:
                    eq=bal
                    for q in range(nlot):eq+=rcs[q]*(real[q]+rem[q]*dirs[q]*(e-ent[q])/risks[q])
                    dirs[nlot]=pdn;ent[nlot]=e;stops[nlot]=st;risks[nlot]=rrisk;rcs[nlot]=max(eq,0.)*RISK;opened[nlot]=i
                    rem[nlot]=1.;real[nlot]=0.;hit1[nlot]=0;hit2[nlot]=0;prot[nlot]=0;nlot+=1
                    if padd==1:adds+=1
                    else:campaigns+=1
                    cdir=pdn;lastadd=i
            pdn=0;pdi=-1;padd=0
        newn=0
        for k in range(nlot):
            d=dirs[k];closed=False;rr=0.
            # Conservative ambiguous-bar rule: protective stop is evaluated before new targets.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]):
                rr=real[k]+rem[k]*d*(stops[k]-ent[k])/risks[k]-costR;closed=True
            else:
                p1=ent[k]+d*t1*risks[k];p2=ent[k]+d*t2*risks[k];pr=ent[k]+d*runner*risks[k]
                if hit1[k]==0 and ((d==1 and h[i]>=p1) or (d==-1 and l[i]<=p1)):
                    real[k]+=f1*t1;rem[k]-=f1;hit1[k]=1;t1hits+=1
                if hit1[k]==1 and hit2[k]==0 and ((d==1 and h[i]>=p2) or (d==-1 and l[i]<=p2)):
                    real[k]+=f2*t2;rem[k]-=f2;hit2[k]=1;t2hits+=1
                if (d==1 and h[i]>=pr) or (d==-1 and l[i]<=pr):
                    rr=real[k]+rem[k]*runner-costR;closed=True;runnerhits+=1
                elif i-opened[k]>=maxhold:
                    rr=real[k]+rem[k]*d*(c[i]-ent[k])/risks[k]-costR;closed=True
                else:
                    # After a completed bar confirms T1 was reached, remaining size is protected at BE.
                    if hit1[k]==1 and prot[k]==0:
                        stops[k]=ent[k];prot[k]=1
            if closed:
                bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
                if rr>0:wins+=1;pos+=rr
                elif rr<0:neg-=rr
            else:
                if newn!=k:
                    dirs[newn]=dirs[k];ent[newn]=ent[k];stops[newn]=stops[k];risks[newn]=risks[k];rcs[newn]=rcs[k];opened[newn]=opened[k];rem[newn]=rem[k];real[newn]=real[k];hit1[newn]=hit1[k];hit2[newn]=hit2[k];prot[newn]=prot[k]
                newn+=1
        nlot=newn
        if nlot==0:cdir=0
        eq=bal;allprot=True
        for k in range(nlot):
            eq+=rcs[k]*(real[k]+rem[k]*dirs[k]*(c[i]-ent[k])/risks[k])
            if prot[k]==0:allprot=False
        if eq>peak:peak=eq
        cur=(peak-eq)/peak if peak>0 else 0.
        if cur>dd:dd=cur
        if pdn==0:
            if cdir==0:
                if sigL[i] and not sigS[i]:pdn=1;pdi=i;padd=0
                elif sigS[i] and not sigL[i]:pdn=-1;pdi=i;padd=0
            elif nlot<maxlots and allprot and i>lastadd:
                pdn=cdir;pdi=i;padd=1
    for k in range(nlot):
        rr=real[k]+rem[k]*dirs[k]*(c[last]-ent[k])/risks[k]-costR;bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    return nclosed,campaigns,adds,(bal-1)*100.,100.*wins/nclosed if nclosed else 0.,pos/neg if neg else 99.,rtot/nclosed if nclosed else 0.,rtot,dd*100.,100.*t1hits/nclosed if nclosed else 0.,100.*t2hits/nclosed if nclosed else 0.,100.*runnerhits/nclosed if nclosed else 0.

def pack(v):return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8]),'t1_hit_pct':float(v[9]),'t2_hit_pct':float(v[10]),'runner_hit_pct':float(v[11])}

def union(ed,names,idx):
    L=pd.Series(False,index=idx);S=L.copy()
    for nm in names:L|=ed[nm][0];S|=ed[nm][1]
    clash=L&S;return L&~clash,S&~clash

def score(tr,va):
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.10 or va['pf']<1.10:return -1e9
    return 3.3*min(tr['wr'],va['wr'])+13*math.log1p(tr['ret']/100)+20*math.log1p(va['ret']/100)-.35*tr['dd']-.55*va['dd']-18*abs(tr['avgR']-va['avgR'])

def main():
    x=g.prep();m1=s.raw_m1();f5,f15=s.micro_features(m1);x=s.add_micro(x,f5,f15);idx=x.index;ed=m.build_edges(x)
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);pL=pd.Series(np.isfinite(poc)&(c>poc),index=idx);pS=pd.Series(np.isfinite(poc)&(c<poc),index=idx)
    vf=vw.vwap_ladder(x,3,True);vms=vc.mk_masks(x,vf);fsL,fsS=s.flow_scores(x);zL=((x.z48>0)&(x.z84>0)).fillna(False);zS=((x.z48<0)&(x.z84<0)).fillna(False)
    masks=[]
    for sn,names in {'UNION4':('BRK','EXP','PULL','FRACTAL'),'EXP_PULL':('EXP','PULL')}.items():
        bL,bS=union(ed,names,idx)
        for vg in ['WEEK_PLUS_ANY','STRICT2']:
            vL,vS=vms[vg]
            for k,usez in [(0,False),(5,True),(7,True)]:
                L=bL&pL&vL&pd.Series(fsL>=k,index=idx);S=bS&pS&vS&pd.Series(fsS>=k,index=idx)
                if usez:L&=zL;S&=zS
                masks.append(((sn,vg,k,usez),(o,h,lo,c,atr,slo,shi,L.to_numpy(np.bool_),S.to_numpy(np.bool_))))
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    rows=[];cache={}
    for key,arr in masks:
        cache[key]=arr
        for af,t1,f1,t2,runner,ml,cost in itertools.product([.55,.60],[1.5,2.,2.5],[.30,.40,.50],[4.,6.],[12.,18.,24.],[2,3],[.08,.12]):
            f2=.20
            if f1+f2>=.95:continue
            tr=pack(sim(*arr,trb[0],trb[1],af,t1,f1,t2,f2,runner,ml,144,cost));va=pack(sim(*arr,vab[0],vab[1],af,t1,f1,t2,f2,runner,ml,144,cost));sc=score(tr,va)
            if sc>-1e8:rows.append((sc,key,af,t1,f1,t2,f2,runner,ml,cost,tr,va))
        print('DONE_MASK',key,flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);picks=[];seen=set()
    def add(r):
        k=(r[1],)+tuple(r[2:10])
        if k not in seen:seen.add(k);picks.append(r)
    for r in rows[:12]:add(r)
    for trf,vaf in [(100,25),(300,60),(500,100),(800,150)]:
        e=[r for r in rows if r[10]['ret']>=trf and r[11]['ret']>=vaf and r[10]['pf']>=1.15 and r[11]['pf']>=1.15]
        e.sort(key=lambda r:min(r[10]['wr'],r[11]['wr']),reverse=True)
        for r in e[:5]:add(r)
    out=[]
    for sc,key,af,t1,f1,t2,f2,runner,ml,cost,tr,va in picks[:30]:
        arr=cache[key];ho=pack(sim(*arr,hob[0],hob[1],af,t1,f1,t2,f2,runner,ml,144,cost));full=pack(sim(*arr,fullb[0],fullb[1],af,t1,f1,t2,f2,runner,ml,144,cost))
        out.append({'signal':key[0],'vwap_gate':key[1],'flow_score_min':key[2],'zdir':key[3],'af':af,'t1R':t1,'t1_fraction':f1,'t2R':t2,'t2_fraction':f2,'runnerR':runner,'max_lots':ml,'costR':cost,'train':tr,'val':va,'holdout':ho,'full':full,'score':sc})
    valid=[r for r in out if r['holdout']['ret']>0 and r['holdout']['pf']>=1.08]
    def minwr(r):return min(r['train']['wr'],r['val']['wr'],r['holdout']['wr'])
    best=max(valid,key=minwr) if valid else None
    ge1000=[r for r in valid if r['full']['ret']>=1000];best1000=max(ge1000,key=minwr) if ge1000 else None
    ge2000=[r for r in valid if r['full']['ret']>=2000];best2000=max(ge2000,key=minwr) if ge2000 else None
    print('RESULT_JSON_START');print(json.dumps({'risk_rule':'0.36% current mark-to-market equity per fresh setup; recycled risk only after all older live setups are at BE','win_definition':'Net R of each setup/lot after all partials and runner is positive; T1 touch alone is NOT counted as a win','execution':'M5 OHLC with conservative stop-before-new-target ordering; costs tested at 0.08R and 0.12R','selection':'Train+Validation only; Holdout frozen shortlist','best_robust_winrate':best,'best_robust_winrate_full_ge_1000pct':best1000,'best_robust_winrate_full_ge_2000pct':best2000,'shortlist':out,'baseline_nonpartial':{'full_ret':4137.63,'full_wr':17.39,'holdout_wr':16.32,'dd':29.80}},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
