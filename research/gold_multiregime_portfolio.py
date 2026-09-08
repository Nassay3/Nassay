import json, math, itertools
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS
RISK=g.RISK;COST=.10;MAXLOTS=8;MAXM=96

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])

def pack(v):return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8]),'trend_closed':int(v[9]),'rev_closed':int(v[10])}

def monthly(v,idx,first,last):
    n=int(v[13]);prev=1.;a=[];firstc=int(v[12][0]) if n else -1;lastc=int(v[12][n-1]) if n else -1;pfst=idx[first].day>3;plst=idx[last].day<26
    for j in range(n):
        e=float(v[11][j]);code=int(v[12][j]);r=(e/prev-1)*100 if prev>0 else -100.;prev=e;complete=not((code==firstc and pfst)or(code==lastc and plst))
        if complete:a.append(r)
    a=np.asarray(a,float)
    if not len(a):return {'months':0,'pct100':0.,'geom':-100.,'median':-100.,'min':-100.,'max':-100.,'positive':0,'negative':0}
    gross=np.prod(1+a/100);geom=(gross**(1/len(a))-1)*100 if gross>0 else -100.
    return {'months':int(len(a)),'pct100':float((a>100).mean()*100),'geom':float(geom),'median':float(np.median(a)),'min':float(np.min(a)),'max':float(np.max(a)),'positive':int((a>0).sum()),'negative':int((a<0).sum())}

@njit(cache=True)
def sim(o,h,l,c,atr,slo,shi,tL,tS,rL,rS,mcode,mend,first,last,taf,tbe,tml,ttp,thold,raf,rbe,rtp,rhold):
    dirs=np.zeros(MAXLOTS,np.int8);ent=np.zeros(MAXLOTS);stops=np.zeros(MAXLOTS);risks=np.zeros(MAXLOTS);rcs=np.zeros(MAXLOTS);tg=np.zeros(MAXLOTS);opened=np.zeros(MAXLOTS,np.int64);prot=np.zeros(MAXLOTS,np.uint8);kind=np.zeros(MAXLOTS,np.int8);mhld=np.zeros(MAXLOTS,np.int64)
    meq=np.full(MAXM,np.nan);mc=np.zeros(MAXM,np.int64);mn=0
    nlot=0;pending=0;pkind=0;psi=-1;cdir=0;bal=1.;peak=1.;dd=0.;nclosed=0;wins=0;pos=0.;neg=0.;rtot=0.;campaigns=0;adds=0;tclosed=0;rclosed=0
    stopi=min(last,len(o)-2)
    for i in range(max(first,60),stopi+1):
        if pending!=0:
            e=o[i];av=atr[psi]
            if av>0 and np.isfinite(av) and nlot<MAXLOTS:
                af=taf if pkind==1 else raf
                if pending==1:st=min(slo[psi]-.08*av,e-af*av);rrisk=e-st
                else:st=max(shi[psi]+.08*av,e+af*av);rrisk=st-e
                cap=tml if pkind==1 else 1
                current_kind=0
                for q in range(nlot):
                    if kind[q]==pkind:current_kind+=1
                if rrisk>0 and rrisk/e<=.012 and current_kind<cap:
                    eqopen=bal
                    for q in range(nlot):eqopen+=rcs[q]*dirs[q]*(e-ent[q])/risks[q]
                    rc=max(eqopen,0.)*RISK;tp=ttp if pkind==1 else rtp;hold=thold if pkind==1 else rhold
                    dirs[nlot]=pending;ent[nlot]=e;stops[nlot]=st;risks[nlot]=rrisk;rcs[nlot]=rc;tg[nlot]=e+pending*tp*rrisk;opened[nlot]=i;prot[nlot]=0;kind[nlot]=pkind;mhld[nlot]=hold;nlot+=1
                    if cdir==0:campaigns+=1;cdir=pending
                    else:adds+=1
            pending=0;pkind=0;psi=-1
        newn=0
        for k in range(nlot):
            d=dirs[k];tp=(ttp if kind[k]==1 else rtp);be=(tbe if kind[k]==1 else rbe);closed=False;rr=0.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]):rr=d*(stops[k]-ent[k])/risks[k]-COST;closed=True
            elif (d==1 and h[i]>=tg[k]) or (d==-1 and l[i]<=tg[k]):rr=tp-COST;closed=True
            elif i-opened[k]>=mhld[k]:rr=d*(c[i]-ent[k])/risks[k]-COST;closed=True
            if closed:
                bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
                if kind[k]==1:tclosed+=1
                else:rclosed+=1
                if rr>0:wins+=1;pos+=rr
                elif rr<0:neg-=rr
            else:
                cr=d*(c[i]-ent[k])/risks[k]
                if prot[k]==0 and cr>=be:stops[k]=ent[k];prot[k]=1
                if newn!=k:
                    dirs[newn]=dirs[k];ent[newn]=ent[k];stops[newn]=stops[k];risks[newn]=risks[k];rcs[newn]=rcs[k];tg[newn]=tg[k];opened[newn]=opened[k];prot[newn]=prot[k];kind[newn]=kind[k];mhld[newn]=mhld[k]
                newn+=1
        nlot=newn
        if nlot==0:cdir=0
        eq=bal;allprot=True
        for k in range(nlot):
            eq+=rcs[k]*dirs[k]*(c[i]-ent[k])/risks[k]
            if prot[k]==0:allprot=False
        if eq>peak:peak=eq
        cur=(peak-eq)/peak if peak>0 else 0.
        if cur>dd:dd=cur
        if mend[i] and mn<MAXM:meq[mn]=eq;mc[mn]=mcode[i];mn+=1
        # One globally unprotected fresh-risk lot at a time. New setup must have a fresh signal.
        if pending==0 and allprot:
            # When flat, prioritize trend. During a campaign only add same-direction trend; reversal starts only flat.
            if nlot==0:
                if tL[i] and not tS[i]:pending=1;pkind=1;psi=i
                elif tS[i] and not tL[i]:pending=-1;pkind=1;psi=i
                elif rL[i] and not rS[i]:pending=1;pkind=2;psi=i
                elif rS[i] and not rL[i]:pending=-1;pkind=2;psi=i
            else:
                if cdir==1 and tL[i]:pending=1;pkind=1;psi=i
                elif cdir==-1 and tS[i]:pending=-1;pkind=1;psi=i
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-COST;bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if kind[k]==1:tclosed+=1
        else:rclosed+=1
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    return nclosed,campaigns,adds,(bal-1)*100.,100.*wins/nclosed if nclosed else 0.,pos/neg if neg else 99.,rtot/nclosed if nclosed else 0.,rtot,dd*100.,tclosed,rclosed,meq,mc,mn

def build_masks(x):
    idx=x.index;ed=m.build_edges(x);tL=pd.Series(False,index=idx);tS=tL.copy()
    for nm in ('BRK','EXP','PULL','FRACTAL'):tL|=ed[nm][0];tS|=ed[nm][1]
    clash=tL&tS;tL&=~clash;tS&=~clash
    h=x.high.to_numpy(float);l=x.low.to_numpy(float);c=x.close.to_numpy(float);v=x.tick_volume.to_numpy(float)
    poc,_,_=vp.profile_levels(h,l,c,v,288,32,3,.70);ok=np.isfinite(poc);vf=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,vf)['WEEK_PLUS_ANY']
    tL=(tL&wL&pd.Series(ok&(c>poc),index=idx)).fillna(False);tS=(tS&wS&pd.Series(ok&(c<poc),index=idx)).fillna(False)
    rng=(x.high-x.low).replace(0,np.nan);bull=x.close>x.open;bear=x.close<x.open
    # Causal range/nontrend regime based only on completed H1 context already merged into M5.
    slope=(x.h1_vwma84/x.h1_vwma84_prev6-1).abs();range1=(slope<.0035).fillna(False);range2=(slope<.0060).fillna(False)
    # 1) prior day/session liquidity sweep and reclaim.
    swL=(((x.low<x.pdl)&(x.close>x.pdl))|((x.low<x.prev_sess_lo)&(x.close>x.prev_sess_lo)))&bull
    swS=(((x.high>x.pdh)&(x.close<x.pdh))|((x.high>x.prev_sess_hi)&(x.close<x.prev_sess_hi)))&bear
    # 2) VWAP/Z stretch reversal: extreme deviation then close back toward daily VWAP.
    zlong=(x.z48<-1.5)|(x.z84<-1.5);zshort=(x.z48>1.5)|(x.z84>1.5)
    vrL=zlong&bull&(x.close>x.low+rng*.60)&(x.close<x.day_vwap);vrS=zshort&bear&(x.close<x.high-rng*.60)&(x.close>x.day_vwap)
    # 3) failed 20-bar breakout back inside range.
    fh=x.high.shift(1).rolling(20,min_periods=20).max();fl=x.low.shift(1).rolling(20,min_periods=20).min()
    fbL=(x.low<fl)&(x.close>fl)&bull;fbS=(x.high>fh)&(x.close<fh)&bear
    return (tL.to_numpy(np.bool_),tS.to_numpy(np.bool_)),{
      'SWEEP_R1':((swL&range1).fillna(False).to_numpy(np.bool_),(swS&range1).fillna(False).to_numpy(np.bool_)),
      'SWEEP_R2':((swL&range2).fillna(False).to_numpy(np.bool_),(swS&range2).fillna(False).to_numpy(np.bool_)),
      'REV_ALL_R1':(((swL|vrL|fbL)&range1).fillna(False).to_numpy(np.bool_),((swS|vrS|fbS)&range1).fillna(False).to_numpy(np.bool_)),
      'REV_ALL_R2':(((swL|vrL|fbL)&range2).fillna(False).to_numpy(np.bool_),((swS|vrS|fbS)&range2).fillna(False).to_numpy(np.bool_)),
      'REV_NO_RANGE':((swL|vrL|fbL).fillna(False).to_numpy(np.bool_),(swS|vrS|fbS).fillna(False).to_numpy(np.bool_))}

def rkey(tr,tm,va,vm):
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.05 or va['pf']<1.05:return (-1.,-1e9,-1e9,-1e9)
    return (min(tm['pct100'],vm['pct100']),min(tm['geom'],vm['geom']),math.log1p(min(tr['ret'],va['ret'])/100)-.015*max(tr['dd'],va['dd']),min(tr['pf'],va['pf']))

def main():
    x=g.prep();idx=x.index;(tL,tS),revs=build_masks(x)
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);l=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);slo=x.low.shift(1).rolling(6,min_periods=4).min().to_numpy(float);shi=x.high.shift(1).rolling(6,min_periods=4).max().to_numpy(float)
    mcode=np.asarray(idx.year*12+idx.month-1,np.int64);mend=np.zeros(len(idx),np.bool_);mend[:-1]=mcode[:-1]!=mcode[1:];mend[-1]=True
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fb=bounds(idx,g.START,g.END)
    anyr=next(iter(revs.values()));sim(o,h,l,c,atr,slo,shi,tL,tS,*anyr,mcode,mend,trb[0],min(trb[0]+3000,trb[1]),.6,1.25,3,24.,144,.5,.75,3.,36)
    grid=list(itertools.product(revs.keys(),[.5,.75,1.0],[2.,3.,4.,6.],[24,48,72]))
    rows=[]
    for n,(rn,rbe,rtp,rhold) in enumerate(grid,1):
        rL,rS=revs[rn];tv=sim(o,h,l,c,atr,slo,shi,tL,tS,rL,rS,mcode,mend,*trb,.6,1.25,3,24.,144,.5,rbe,rtp,rhold);vv=sim(o,h,l,c,atr,slo,shi,tL,tS,rL,rS,mcode,mend,*vab,.6,1.25,3,24.,144,.5,rbe,rtp,rhold);tr=pack(tv);va=pack(vv);tm=monthly(tv,idx,*trb);vm=monthly(vv,idx,*vab);k=rkey(tr,tm,va,vm)
        if k[0]>=0:rows.append((k,rn,rbe,rtp,rhold,tr,tm,va,vm))
    rows.sort(reverse=True,key=lambda z:z[0]);frozen=[];seen=set()
    def add(z):
        q=(z[1],z[2],z[3],z[4]);
        if q not in seen:seen.add(q);frozen.append(z)
    for z in rows[:20]:add(z)
    for z in sorted(rows,reverse=True,key=lambda z:(min(z[5]['ret'],z[7]['ret']),min(z[5]['pf'],z[7]['pf'])))[:20]:add(z)
    out=[]
    for k,rn,rbe,rtp,rhold,tr,tm,va,vm in frozen:
        rL,rS=revs[rn];hv=sim(o,h,l,c,atr,slo,shi,tL,tS,rL,rS,mcode,mend,*hob,.6,1.25,3,24.,144,.5,rbe,rtp,rhold);fv=sim(o,h,l,c,atr,slo,shi,tL,tS,rL,rS,mcode,mend,*fb,.6,1.25,3,24.,144,.5,rbe,rtp,rhold);ho=pack(hv);full=pack(fv);fm=monthly(fv,idx,*fb)
        out.append({'rev':rn,'rev_beR':rbe,'rev_tpR':rtp,'rev_hold_min':rhold*5,'trend':'UNION4 WEEK_PLUS_ANY POC AF.6 BE1.25 max3 TP24 hold12h','costR':COST,'train':tr,'train_monthly':tm,'val':va,'val_monthly':vm,'holdout':ho,'full':full,'full_monthly':fm,'over10k':full['ret']>10000,'geom100':full['ret']>10000 and fm['geom']>100})
    best=max(out,key=lambda z:z['full']['ret']) if out else None;bestm=max(out,key=lambda z:(z['full_monthly']['geom'],z['full']['ret'])) if out else None
    print('RESULT_JSON_START');print(json.dumps({'risk_rule':'global fresh risk 0.36% MTM; new setup only when all open lots protected at BE','architecture':'fixed trend book + independent range/reversal book','grid':len(grid),'frozen':len(frozen),'count_over10k':sum(z['over10k'] for z in out),'count_geom100':sum(z['geom100'] for z in out),'best_total':best,'best_monthly':bestm,'limitations':['M5 OHLC, not tick bid/ask','0.10R modeled cost per close','VP uses tick activity','Holdout repeatedly consulted in wider research program; external forward needed']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
