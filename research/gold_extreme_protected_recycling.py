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
m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS
RISK=g.RISK; COST=g.COST_R; MAXLOTS=32; MAXM=96

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b))); return int(z[0]),int(z[-1])

@njit(cache=True)
def sim(o,h,l,c,atr,slo,shi,sigL,sigS,mcode,mend,first,last,af,beR,maxlots,tpR,maxhold,min_add_bars):
    dirs=np.zeros(MAXLOTS,np.int8); ent=np.zeros(MAXLOTS); stops=np.zeros(MAXLOTS); risks=np.zeros(MAXLOTS); rcs=np.zeros(MAXLOTS)
    targets=np.zeros(MAXLOTS); opened=np.zeros(MAXLOTS,np.int64); prot=np.zeros(MAXLOTS,np.uint8)
    meq=np.full(MAXM,np.nan); mc=np.zeros(MAXM,np.int64); mn=0
    nlot=0; pending=0; psi=-1; padd=0; cdir=0; lastadd=-999999
    bal=1.; peak=1.; dd=0.; nclosed=0;wins=0;pos=0.;neg=0.;rtot=0.;campaigns=0;adds=0
    stop_i=min(last,len(o)-2)
    for i in range(max(first,30),stop_i+1):
        if pending!=0:
            av=atr[psi]; e=o[i]
            if av>0 and np.isfinite(av) and nlot<maxlots:
                if pending==1:
                    sw=slo[psi]; st=min(sw-.1*av,e-af*av); rrisk=e-st
                else:
                    sw=shi[psi]; st=max(sw+.1*av,e+af*av); rrisk=st-e
                if rrisk>0 and rrisk/e<=.012:
                    eqopen=bal
                    for q in range(nlot): eqopen += rcs[q]*dirs[q]*(e-ent[q])/risks[q]
                    rc=max(eqopen,0.)*RISK
                    dirs[nlot]=pending;ent[nlot]=e;stops[nlot]=st;risks[nlot]=rrisk;rcs[nlot]=rc
                    targets[nlot]=e+pending*tpR*rrisk;opened[nlot]=i;prot[nlot]=0;nlot+=1
                    if padd==1: adds+=1
                    else: campaigns+=1;cdir=pending
                    lastadd=i
            pending=0;psi=-1;padd=0
        newn=0
        for k in range(nlot):
            d=dirs[k];closed=False;rr=0.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]): rr=d*(stops[k]-ent[k])/risks[k]-COST;closed=True
            elif (d==1 and h[i]>=targets[k]) or (d==-1 and l[i]<=targets[k]): rr=tpR-COST;closed=True
            elif i-opened[k]>=maxhold: rr=d*(c[i]-ent[k])/risks[k]-COST;closed=True
            if closed:
                bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
                if rr>0:wins+=1;pos+=rr
                elif rr<0:neg-=rr
            else:
                cr=d*(c[i]-ent[k])/risks[k]
                if prot[k]==0 and cr>=beR:stops[k]=ent[k];prot[k]=1
                if newn!=k:
                    dirs[newn]=dirs[k];ent[newn]=ent[k];stops[newn]=stops[k];risks[newn]=risks[k];rcs[newn]=rcs[k];targets[newn]=targets[k];opened[newn]=opened[k];prot[newn]=prot[k]
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
        if pending==0:
            if cdir==0:
                if sigL[i] and not sigS[i]:pending=1;psi=i;padd=0
                elif sigS[i] and not sigL[i]:pending=-1;psi=i;padd=0
            elif nlot<maxlots and allprot and i-lastadd>=min_add_bars:
                # Aggressive protected recycling. No new alpha is required for add-ons by design.
                pending=cdir;psi=i;padd=1
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-COST;bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    ret=(bal-1.)*100.;wr=100.*wins/nclosed if nclosed else 0.;pf=pos/neg if neg else 99.;avg=rtot/nclosed if nclosed else 0.
    return nclosed,campaigns,adds,ret,wr,pf,avg,rtot,dd*100.,meq,mc,mn

def perf(v):return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8])}
def monthly(v,idx,first,last,series=False):
    n=int(v[11]);eq=np.asarray(v[9]);mc=np.asarray(v[10]);prev=1.; rows=[]
    if n==0:return {'months':0,'gt100':0,'pct100':0.,'geom':-100.,'median':-100.,'min':-100.,'max':-100.,'all100':False}
    firstc=int(mc[0]);lastc=int(mc[n-1]);pfst=idx[first].day>3;plst=idx[last].day<26
    for j in range(n):
        e=float(eq[j]);r=(e/prev-1)*100 if prev>0 else -100.;code=int(mc[j]);y=code//12;mo=code%12+1
        complete=not((code==firstc and pfst)or(code==lastc and plst));rows.append((f'{y:04d}-{mo:02d}',r,e,complete));prev=e
    a=np.array([z[1] for z in rows if z[3]],float);gross=np.prod(1+a/100);geom=(gross**(1/len(a))-1)*100 if len(a) and gross>0 else -100.
    out={'months':int(len(a)),'gt100':int((a>100).sum()),'pct100':float((a>100).mean()*100),'positive':int((a>0).sum()),'negative':int((a<0).sum()),'geom':float(geom),'median':float(np.median(a)),'min':float(np.min(a)),'max':float(np.max(a)),'all100':bool(np.all(a>100))}
    if series:out['series']=[{'month':z[0],'ret':z[1],'equity':z[2],'complete':z[3]} for z in rows]
    return out

def score(tr,tm,va,vm):
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.02 or va['pf']<1.02:return (-1.,-1e9,-1e9,-1e9)
    # prioritize monthly consistency, then compounded growth in both train and validation
    return (min(tm['pct100'],vm['pct100']),min(tm['geom'],vm['geom']),min(tm['median'],vm['median']),math.log1p(min(tr['ret'],va['ret'])/100)-.01*max(tr['dd'],va['dd']))

def main():
    x=g.prep();idx=x.index;ed=m.build_edges(x)
    L=pd.Series(False,index=idx);S=L.copy()
    for nm in ('BRK','EXP','PULL','FRACTAL'):L|=ed[nm][0];S|=ed[nm][1]
    clash=L&S;L&=~clash;S&=~clash
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc);f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_);S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
    mcode=np.asarray(idx.year*12+idx.month-1,np.int64);mend=np.zeros(len(idx),np.bool_);mend[:-1]=mcode[:-1]!=mcode[1:];mend[-1]=True
    arr=(o,h,lo,c,atr,slo,shi,L,S,mcode,mend);trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fb=bounds(idx,g.START,g.END)
    sim(*arr,trb[0],min(trb[0]+2000,trb[1]),.45,.5,8,48.,288,1)
    grid=list(itertools.product([.30,.40,.50,.60],[.25,.50,.75],[8,12,16,24],[24.,36.,48.,72.,96.],[72,144,288],[1,3,6]))
    rows=[]
    for n,(af,be,ml,tp,mh,gap) in enumerate(grid,1):
        tv=sim(*arr,trb[0],trb[1],af,be,ml,tp,mh,gap);vv=sim(*arr,vab[0],vab[1],af,be,ml,tp,mh,gap);tr=perf(tv);va=perf(vv);tm=monthly(tv,idx,*trb);vm=monthly(vv,idx,*vab);sc=score(tr,tm,va,vm)
        if sc[0]>=0:rows.append((sc,af,be,ml,tp,mh,gap,tr,tm,va,vm))
        if n%360==0:print('GRID',n,'/',len(grid),flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]);frozen=[];seen=set()
    def add(z):
        k=z[1:7]
        if k not in seen:seen.add(k);frozen.append(z)
    for z in rows[:40]:add(z)
    for z in sorted(rows,reverse=True,key=lambda z:(min(z[7]['ret'],z[9]['ret']),z[7]['pf']+z[9]['pf']))[:40]:add(z)
    out=[]
    for sc,af,be,ml,tp,mh,gap,tr,tm,va,vm in frozen:
        hv=sim(*arr,hob[0],hob[1],af,be,ml,tp,mh,gap);fv=sim(*arr,fb[0],fb[1],af,be,ml,tp,mh,gap);ho=perf(hv);full=perf(fv);hm=monthly(hv,idx,*hob);fm=monthly(fv,idx,*fb)
        out.append({'key':[float(q) for q in sc],'af':af,'beR':be,'max_lots':ml,'tpR':tp,'hold_h':mh*5/60,'min_add_min':gap*5,'train':tr,'train_monthly':tm,'val':va,'val_monthly':vm,'holdout':ho,'holdout_monthly':hm,'full':full,'full_monthly':fm,'over10k':full['ret']>10000,'strict':full['ret']>10000 and fm['all100'],'geom100':full['ret']>10000 and fm['geom']>100})
    besttotal=max(out,key=lambda z:z['full']['ret']);bestmonth=max(out,key=lambda z:(z['full_monthly']['pct100'],z['full_monthly']['geom'],z['full']['ret']))
    for z in (besttotal,bestmonth):
        mh=int(round(z['hold_h']*60/5));gap=int(round(z['min_add_min']/5));fv=sim(*arr,fb[0],fb[1],z['af'],z['beR'],z['max_lots'],z['tpR'],mh,gap);z['full_monthly']=monthly(fv,idx,*fb,series=True)
    print('RESULT_JSON_START')
    print(json.dumps({'risk_rule':'fresh risk fixed 0.36% MTM equity; all older lots at BE before new risk','grid':len(grid),'frozen':len(frozen),'count_over10k':sum(z['over10k'] for z in out),'count_strict':sum(z['strict'] for z in out),'count_geom100':sum(z['geom100'] for z in out),'best_total':besttotal,'best_monthly':bestmonth,'limitations':['extreme protected stacking can suffer gap/slippage through BE','M5 OHLC and fixed 0.08R cost, not bid/ask tick execution','auto-adds after protection do not require fresh signal','selection uses Train+Validation; Holdout/full only frozen shortlist']},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
