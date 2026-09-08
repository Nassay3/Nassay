import json, math, itertools
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
RISK=g.RISK; COST=.15; MAXLOTS=8; MAXM=96

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(z[0]),int(z[-1])

def prep():
    m1=g.prev_levels(g.vwaps(g.core(g.read_all(),[84,175])))
    m5=g.prep(); ctx=g.contexts(m5)
    # Causal M5 volume-profile/VWAP regime. No current M5 value is exposed to M1 until the M5 bar closes.
    h=m5.high.to_numpy(float);l=m5.low.to_numpy(float);c=m5.close.to_numpy(float);v=m5.tick_volume.to_numpy(float)
    poc,_,_=vp.profile_levels(h,l,c,v,288,32,3,.70); ok=np.isfinite(poc)
    vf=vw.vwap_ladder(m5,3,True); wL,wS=vc.mk_masks(m5,vf)['WEEK_PLUS_ANY']
    medL,medS=ctx['med'];mtfL,mtfS=ctx['mtf']
    above=(m5.close>m5.vwma84)&(m5.vwma84>m5.vwma175);below=(m5.close<m5.vwma84)&(m5.vwma84<m5.vwma175)
    q=pd.DataFrame(index=m5.index)
    q['medL']=(medL&above).fillna(False);q['medS']=(medS&below).fillna(False)
    q['mtfL']=(mtfL&above).fillna(False);q['mtfS']=(mtfS&below).fillna(False)
    q['strictL']=(medL&above&wL&pd.Series(ok&(c>poc),index=m5.index)).fillna(False)
    q['strictS']=(medS&below&wS&pd.Series(ok&(c<poc),index=m5.index)).fillna(False)
    q['avail']=q.index+pd.Timedelta(minutes=5);q=q.reset_index(drop=True)
    b=m1.copy();b['decision']=b.index+pd.Timedelta(minutes=1);b=b.reset_index().rename(columns={'time':'bar_time'})
    b=pd.merge_asof(b.sort_values('decision'),q.sort_values('avail'),left_on='decision',right_on='avail',direction='backward').set_index('bar_time').sort_index()
    # Microstructure proxies from broker tick activity; explicitly not CME trade flow.
    rng=(b.high-b.low).replace(0,np.nan);b['clv']=((2*b.close-b.high-b.low)/rng).clip(-1,1).fillna(0)
    b['volrel30']=b.tick_volume/b.tick_volume.shift(1).rolling(30,min_periods=15).median().replace(0,np.nan)
    b['volchg']=b.tick_volume/b.tick_volume.shift(1).replace(0,np.nan)-1
    b['rngmed20']=(b.high-b.low).shift(1).rolling(20,min_periods=12).median()
    for n in [6,10,20]:
        b[f'rh{n}']=b.high.shift(1).rolling(n,min_periods=n).max();b[f'rl{n}']=b.low.shift(1).rolling(n,min_periods=n).min()
    b['slo6']=b.low.shift(1).rolling(6,min_periods=4).min();b['shi6']=b.high.shift(1).rolling(6,min_periods=4).max()
    return b

def signals(x):
    up=(x.close>x.vwma84)&(x.vwma84>x.vwma175);dn=(x.close<x.vwma84)&(x.vwma84<x.vwma175);rng=(x.high-x.low).replace(0,np.nan)
    br10L=(x.close>x.rh10)&up;br10S=(x.close<x.rl10)&dn
    br20L=(x.close>x.rh20)&up;br20S=(x.close<x.rl20)&dn
    expL=((x.high-x.low)/x.rngmed20>=1.5)&(x.close>x.open)&(((x.close-x.low)/rng)>=.78)&up
    expS=((x.high-x.low)/x.rngmed20>=1.5)&(x.close<x.open)&(((x.high-x.close)/rng)>=.78)&dn
    pullL=(x.low.shift(1)<=x.vwma84.shift(1)*1.0007)&(x.close>x.vwma84)&(x.close>x.high.shift(1))&up
    pullS=(x.high.shift(1)>=x.vwma84.shift(1)*.9993)&(x.close<x.vwma84)&(x.close<x.low.shift(1))&dn
    flowL=(x.clv>.55)&(x.volrel30>1.20)&(x.volchg>0)&(x.close>x.rh6)&up
    flowS=(x.clv<-.55)&(x.volrel30>1.20)&(x.volchg>0)&(x.close<x.rl6)&dn
    return {
      'ALL':((br10L|expL|pullL|flowL).fillna(False),(br10S|expS|pullS|flowS).fillna(False)),
      'TREND':((br20L|expL|pullL).fillna(False),(br20S|expS|pullS).fillna(False)),
      'FLOW_PULL':((flowL|pullL).fillna(False),(flowS|pullS).fillna(False))}

def regime(x,name):
    if name=='MED':return x.medL.fillna(False),x.medS.fillna(False)
    if name=='MTF':return x.mtfL.fillna(False),x.mtfS.fillna(False)
    return x.strictL.fillna(False),x.strictS.fillna(False)

@njit(cache=True)
def sim(o,h,l,c,atr,slo,shi,L,S,mcode,mend,first,last,af,beR,maxlots,tpR,maxhold):
    dirs=np.zeros(MAXLOTS,np.int8);ent=np.zeros(MAXLOTS);stops=np.zeros(MAXLOTS);risks=np.zeros(MAXLOTS);rcs=np.zeros(MAXLOTS);tg=np.zeros(MAXLOTS);opened=np.zeros(MAXLOTS,np.int64);prot=np.zeros(MAXLOTS,np.uint8)
    meq=np.full(MAXM,np.nan);mc=np.zeros(MAXM,np.int64);mn=0
    nlot=0;pending=0;psi=-1;cdir=0;bal=1.;peak=1.;dd=0.;nclosed=0;wins=0;pos=0.;neg=0.;rtot=0.;campaigns=0;adds=0
    stopi=min(last,len(o)-2)
    for i in range(max(first,200),stopi+1):
        if pending!=0:
            e=o[i];av=atr[psi]
            if av>0 and np.isfinite(av) and nlot<maxlots:
                if pending==1:st=min(slo[psi]-.05*av,e-af*av);rrisk=e-st
                else:st=max(shi[psi]+.05*av,e+af*av);rrisk=st-e
                if rrisk>0 and rrisk/e<=.006:
                    eqopen=bal
                    for q in range(nlot):eqopen+=rcs[q]*dirs[q]*(e-ent[q])/risks[q]
                    rc=max(eqopen,0.)*RISK;dirs[nlot]=pending;ent[nlot]=e;stops[nlot]=st;risks[nlot]=rrisk;rcs[nlot]=rc;tg[nlot]=e+pending*tpR*rrisk;opened[nlot]=i;prot[nlot]=0;nlot+=1
                    if cdir==0:campaigns+=1;cdir=pending
                    else:adds+=1
            pending=0;psi=-1
        newn=0
        for k in range(nlot):
            d=dirs[k];closed=False;rr=0.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]):rr=d*(stops[k]-ent[k])/risks[k]-COST;closed=True
            elif (d==1 and h[i]>=tg[k]) or (d==-1 and l[i]<=tg[k]):rr=tpR-COST;closed=True
            elif i-opened[k]>=maxhold:rr=d*(c[i]-ent[k])/risks[k]-COST;closed=True
            if closed:
                bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
                if rr>0:wins+=1;pos+=rr
                elif rr<0:neg-=rr
            else:
                cr=d*(c[i]-ent[k])/risks[k]
                if prot[k]==0 and cr>=beR:stops[k]=ent[k];prot[k]=1
                if newn!=k:
                    dirs[newn]=dirs[k];ent[newn]=ent[k];stops[newn]=stops[k];risks[newn]=risks[k];rcs[newn]=rcs[k];tg[newn]=tg[k];opened[newn]=opened[k];prot[newn]=prot[k]
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
        # Fresh M1 signal is required for both campaign starts and protected add-ons.
        if pending==0:
            if cdir==0:
                if L[i] and not S[i]:pending=1;psi=i
                elif S[i] and not L[i]:pending=-1;psi=i
            elif nlot<maxlots and allprot:
                if cdir==1 and L[i]:pending=1;psi=i
                elif cdir==-1 and S[i]:pending=-1;psi=i
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-COST;bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    return nclosed,campaigns,adds,(bal-1)*100.,100.*wins/nclosed if nclosed else 0.,pos/neg if neg else 99.,rtot/nclosed if nclosed else 0.,rtot,dd*100.,meq,mc,mn

def perf(v):return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8])}
def monthly(v,idx,first,last):
    n=int(v[11]);prev=1.;a=[];firstc=int(v[10][0]) if n else -1;lastc=int(v[10][n-1]) if n else -1;pfst=idx[first].day>3;plst=idx[last].day<26
    for j in range(n):
        e=float(v[9][j]);code=int(v[10][j]);r=(e/prev-1)*100 if prev>0 else -100.;prev=e;complete=not((code==firstc and pfst)or(code==lastc and plst))
        if complete:a.append(r)
    a=np.asarray(a,float)
    if not len(a):return {'months':0,'pct100':0.,'geom':-100.,'median':-100.,'min':-100.,'max':-100.}
    gross=np.prod(1+a/100);geom=(gross**(1/len(a))-1)*100 if gross>0 else -100.
    return {'months':len(a),'pct100':float((a>100).mean()*100),'geom':float(geom),'median':float(np.median(a)),'min':float(np.min(a)),'max':float(np.max(a))}
def rank(tr,tm,va,vm):
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.04 or va['pf']<1.04:return (-1.,-1e9,-1e9,-1e9)
    return (min(tm['pct100'],vm['pct100']),min(tm['geom'],vm['geom']),math.log1p(min(tr['ret'],va['ret'])/100)-.012*max(tr['dd'],va['dd']),min(tr['pf'],va['pf']))

def main():
    x=prep();idx=x.index;sigs=signals(x);o=x.open.to_numpy(float);h=x.high.to_numpy(float);l=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);slo=x.slo6.to_numpy(float);shi=x.shi6.to_numpy(float)
    mcode=np.asarray(idx.year*12+idx.month-1,np.int64);mend=np.zeros(len(idx),np.bool_);mend[:-1]=mcode[:-1]!=mcode[1:];mend[-1]=True
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fb=bounds(idx,g.START,g.END)
    masks={}
    for sn,(bL,bS) in sigs.items():
      for rn in ['MED','MTF','STRICT']:
        rL,rS=regime(x,rn);L=(bL&rL).to_numpy(np.bool_);S=(bS&rS).to_numpy(np.bool_);masks[(sn,rn)]=(L,S)
    anymask=next(iter(masks.values()));sim(o,h,l,c,atr,slo,shi,*anymask,mcode,mend,trb[0],min(trb[0]+5000,trb[1]),.5,.5,2,3.,30)
    grid=list(itertools.product(masks.keys(),[.5,.75],[.5,.75],[2,4],[3.,6.,10.],[30,60]))
    rows=[]
    for n,(mk,af,be,ml,tp,mh) in enumerate(grid,1):
        L,S=masks[mk];tv=sim(o,h,l,c,atr,slo,shi,L,S,mcode,mend,*trb,af,be,ml,tp,mh);vv=sim(o,h,l,c,atr,slo,shi,L,S,mcode,mend,*vab,af,be,ml,tp,mh);tr=perf(tv);va=perf(vv);tm=monthly(tv,idx,*trb);vm=monthly(vv,idx,*vab);sc=rank(tr,tm,va,vm)
        if sc[0]>=0:rows.append((sc,mk,af,be,ml,tp,mh,tr,tm,va,vm))
        if n%100==0:print('GRID',n,'/',len(grid),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);frozen=[];seen=set()
    def add(z):
        k=(z[1],z[2],z[3],z[4],z[5],z[6]);
        if k not in seen:seen.add(k);frozen.append(z)
    for z in rows[:30]:add(z)
    for z in sorted(rows,reverse=True,key=lambda z:(min(z[7]['ret'],z[9]['ret']),min(z[7]['pf'],z[9]['pf'])))[:30]:add(z)
    out=[]
    for sc,mk,af,be,ml,tp,mh,tr,tm,va,vm in frozen:
        L,S=masks[mk];hv=sim(o,h,l,c,atr,slo,shi,L,S,mcode,mend,*hob,af,be,ml,tp,mh);fv=sim(o,h,l,c,atr,slo,shi,L,S,mcode,mend,*fb,af,be,ml,tp,mh);ho=perf(hv);full=perf(fv);fm=monthly(fv,idx,*fb)
        out.append({'signal':mk[0],'regime':mk[1],'af':af,'beR':be,'max_lots':ml,'tpR':tp,'hold_min':mh,'costR':COST,'train':tr,'train_monthly':tm,'val':va,'val_monthly':vm,'holdout':ho,'full':full,'full_monthly':fm,'over10k':full['ret']>10000,'geom100':full['ret']>10000 and fm['geom']>100})
    best=max(out,key=lambda z:z['full']['ret']) if out else None;bestm=max(out,key=lambda z:(z['full_monthly']['geom'],z['full']['ret'])) if out else None
    print('RESULT_JSON_START');print(json.dumps({'risk_rule':'0.36% MTM equity per fresh M1 setup; old lots all BE + fresh same-direction M1 alpha required before add','data_truth':'M1 price/tick-volume real broker-history bars; volume/pressure are quote-activity proxies, not CME aggressor/order-book data','grid':len(grid),'frozen':len(frozen),'count_over10k':sum(z['over10k'] for z in out),'count_geom100':sum(z['geom100'] for z in out),'best_total':best,'best_monthly':bestm,'limitations':['M1 OHLC not bid/ask ticks','fixed 0.15R modeled cost per closed lot','M5 profile uses tick activity','true CME orderflow pipeline exists separately but needs authenticated Databento data']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
