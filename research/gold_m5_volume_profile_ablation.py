import json
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS
RISK=g.RISK; COST=g.COST_R

@njit(cache=True)
def profile_levels(high, low, close, vol, lookback, bins=32, refresh=3, va_frac=.70):
    n=len(close); poc=np.full(n,np.nan); vah=np.full(n,np.nan); val=np.full(n,np.nan)
    hist=np.zeros(bins,np.float64)
    for i in range(lookback,n):
        if refresh>1 and i%refresh!=0 and np.isfinite(poc[i-1]):
            poc[i]=poc[i-1];vah[i]=vah[i-1];val[i]=val[i-1];continue
        lo0=1e100;hi0=-1e100
        for j in range(i-lookback,i):
            if low[j]<lo0:lo0=low[j]
            if high[j]>hi0:hi0=high[j]
        span=hi0-lo0
        if span<=0:continue
        for k in range(bins):hist[k]=0.0
        # Causal activity-profile proxy: assign each COMPLETED M5 bar's tick activity to its HLC3 bin.
        for j in range(i-lookback,i):
            typ=(high[j]+low[j]+close[j])/3.0
            k=int((typ-lo0)/span*bins)
            if k<0:k=0
            if k>=bins:k=bins-1
            w=vol[j]
            if not np.isfinite(w) or w<=0:w=1.0
            hist[k]+=w
        total=0.;p=0;best=-1.
        for k in range(bins):
            total+=hist[k]
            if hist[k]>best:best=hist[k];p=k
        if total<=0:continue
        left=p;right=p;acc=hist[p];target=va_frac*total
        while acc<target and (left>0 or right<bins-1):
            lv=hist[left-1] if left>0 else -1.
            rv=hist[right+1] if right<bins-1 else -1.
            if rv>lv:
                right+=1;acc+=hist[right]
            else:
                left-=1;acc+=hist[left]
        step=span/bins
        poc[i]=lo0+(p+.5)*step
        val[i]=lo0+left*step
        vah[i]=lo0+(right+1)*step
    return poc,vah,val

@njit(cache=True)
def sim_profile(o,h,l,c,atr,slo6,shi6,sigL,sigS,addL,addS,first,last,atr_floor=.75,beR=1.25,maxlots=4,tpR=18.,maxhold=144):
    dirs=np.zeros(8,np.int8);ent=np.zeros(8);stops=np.zeros(8);risks=np.zeros(8);rcs=np.zeros(8);targets=np.zeros(8);opened=np.zeros(8,np.int64);prot=np.zeros(8,np.uint8)
    nlot=0;pending_d=0;pending_i=-1;pending_add=0;cdir=0;last_add=-999
    bal=1.;peak=1.;dd=0.;nclosed=0;wins=0;pos=0.;neg=0.;rtot=0.;campaigns=0;adds=0
    for i in range(max(first,30),min(last,len(o)-2)+1):
        if pending_d!=0:
            av=atr[pending_i];e=o[i]
            if av>0 and np.isfinite(av):
                sw=slo6[pending_i] if pending_d==1 else shi6[pending_i]
                if pending_d==1:st=min(sw-.1*av,e-atr_floor*av);rrisk=e-st
                else:st=max(sw+.1*av,e+atr_floor*av);rrisk=st-e
                if rrisk>0 and rrisk/e<=.012 and nlot<maxlots:
                    dirs[nlot]=pending_d;ent[nlot]=e;stops[nlot]=st;risks[nlot]=rrisk;rcs[nlot]=bal*RISK;targets[nlot]=e+pending_d*tpR*rrisk;opened[nlot]=i;prot[nlot]=0;nlot+=1
                    if pending_add==1:adds+=1
                    else:campaigns+=1
                    cdir=pending_d;last_add=i
            pending_d=0;pending_i=-1;pending_add=0
        newn=0
        for k in range(nlot):
            d=dirs[k];closed=False;rr=0.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]):rr=d*(stops[k]-ent[k])/risks[k]-COST;closed=True
            elif (d==1 and h[i]>=targets[k]) or (d==-1 and l[i]<=targets[k]):rr=tpR-COST;closed=True
            elif i-opened[k]>=maxhold:rr=d*(c[i]-ent[k])/risks[k]-COST;closed=True
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
        if pending_d==0:
            if cdir==0:
                if sigL[i] and not sigS[i]:pending_d=1;pending_i=i;pending_add=0
                elif sigS[i] and not sigL[i]:pending_d=-1;pending_i=i;pending_add=0
            elif nlot<maxlots and allprot and i>last_add:
                if cdir==1 and addL[i]:pending_d=1;pending_i=i;pending_add=1
                elif cdir==-1 and addS[i]:pending_d=-1;pending_i=i;pending_add=1
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-COST;bal+=rcs[k]*rr;nclosed+=1;rtot+=rr
        if rr>0:wins+=1;pos+=rr
        elif rr<0:neg-=rr
    return nclosed,campaigns,adds,(bal-1)*100.,100.*wins/nclosed if nclosed else 0.,pos/neg if neg else 99.,rtot/nclosed if nclosed else 0.,rtot,dd*100.

def pack(v):return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8])}
def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return int(ids[0]),int(ids[-1])

def main():
    x=g.prep();ed=m.build_edges(x);baseL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);baseS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);conf=baseL&baseS;baseL&=~conf;baseS&=~conf
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo6=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi6=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    idx=x.index;trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    profiles={}
    for lb in (96,288):
        print('PROFILE_BUILD',lb,flush=True);profiles[lb]=profile_levels(h,lo,c,vol,lb,32,3,.70)
    candidates=[];cache={}
    # NONE is always benchmark. Profile modes are deliberately small to limit selection risk.
    specs=[('NONE',0,'none')]
    for lb in (96,288):
        for mode in ('POC_GATE','OUTSIDE_GATE','ACCEPT2_GATE','POC_ADD','OUTSIDE_ADD','ACCEPT2_ADD'):
            specs.append((mode,lb,mode))
    for name,lb,mode in specs:
        initL=baseL.copy();initS=baseS.copy();addL=pd.Series(True,index=idx);addS=pd.Series(True,index=idx)
        if mode!='none':
            poc,vah,val=profiles[lb]
            ok=np.isfinite(poc)&np.isfinite(vah)&np.isfinite(val)
            pocL=pd.Series(ok&(c>poc),index=idx);pocS=pd.Series(ok&(c<poc),index=idx)
            outL=pd.Series(ok&(c>vah),index=idx);outS=pd.Series(ok&(c<val),index=idx)
            accL=(outL&outL.shift(1,fill_value=False));accS=(outS&outS.shift(1,fill_value=False))
            if mode=='POC_GATE':initL&=pocL;initS&=pocS
            elif mode=='OUTSIDE_GATE':initL&=outL;initS&=outS
            elif mode=='ACCEPT2_GATE':initL&=accL;initS&=accS
            elif mode=='POC_ADD':addL=pocL;addS=pocS
            elif mode=='OUTSIDE_ADD':addL=outL;addS=outS
            elif mode=='ACCEPT2_ADD':addL=accL;addS=accS
        arr=(o,h,lo,c,atr,slo6,shi6,initL.to_numpy(np.bool_),initS.to_numpy(np.bool_),addL.to_numpy(np.bool_),addS.to_numpy(np.bool_))
        cache[(name,lb)]=arr
        tr=pack(sim_profile(*arr,trb[0],trb[1]));va=pack(sim_profile(*arr,vab[0],vab[1]))
        score=tr['ret']-1.5*tr['dd']+.85*va['ret']-1.25*va['dd']-50*abs(tr['avgR']-va['avgR'])
        candidates.append((score,name,lb,tr,va))
        print('SCREEN',name,lb,'TRAIN',round(tr['ret'],2),round(tr['pf'],3),'VAL',round(va['ret'],2),round(va['pf'],3),flush=True)
    candidates.sort(reverse=True,key=lambda z:z[0]);prom=[]
    # Always expose baseline plus top 3 profile modes. Holdout never used for selection.
    keys=[]
    for row in candidates:
        if row[1]=='NONE':keys.append(row);break
    for row in candidates:
        if row[1]!='NONE' and len(keys)<4:keys.append(row)
    for score,name,lb,tr,va in keys:
        arr=cache[(name,lb)];ho=pack(sim_profile(*arr,hob[0],hob[1]));full=pack(sim_profile(*arr,fullb[0],fullb[1]))
        prom.append({'mode':name,'lookback_m5':lb,'lookback_hours':lb*5/60 if lb else 0,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START')
    print(json.dumps({'risk_pct':.36,'strategy':'Frozen Sequential BRK+EXP AF0.75 BE1.25 max4 TP18 hold12h','profile_method':'CAUSAL 70% value area; 32 bins; previous completed M5 bars only; HLC3 assigned to bin weighted by tick_volume; refresh every 3 M5 bars','profile_warning':'This is an activity/tick-volume profile proxy, NOT COMEX GC true traded volume-at-price.','selection':'profile modes ranked on Train+Validation only; Holdout exposed for baseline + top3 profile modes','screen':[{'mode':n,'lookback':lb,'score':s,'train':tr,'val':va} for s,n,lb,tr,va in candidates],'promoted':prom,'hard_gate_policy':'Profile is promoted only if it improves robustness on Holdout; otherwise it remains context/visual evidence only.'},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
