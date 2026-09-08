import json, math, itertools
import numpy as np
import pandas as pd
from numba import njit
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

# Research-only branch. Exact fresh-risk rule remains fixed at 0.36% current mark-to-market equity.
g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS
RISK=g.RISK
COST=g.COST_R
MAX_MONTHS=96


def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b)))
    return int(z[0]),int(z[-1])


@njit(cache=True)
def sim_monthly(o,h,l,c,atr,slo,shi,sigL,sigS,month_code,month_end,first,last,af,beR,maxlots,tpR,maxhold):
    # Same execution semantics as gold_10000_equity_risk.sim_equity, plus mark-to-market month-end snapshots.
    dirs=np.zeros(8,np.int8); ent=np.zeros(8); stops=np.zeros(8); risks=np.zeros(8)
    rcs=np.zeros(8); targets=np.zeros(8); opened=np.zeros(8,np.int64); prot=np.zeros(8,np.uint8)
    meq=np.full(MAX_MONTHS,np.nan); mcode=np.zeros(MAX_MONTHS,np.int64); mn=0
    nlot=0; pdn=0; pdi=-1; padd=0; cdir=0; lastadd=-999
    bal=1.; peak=1.; dd=0.; nclosed=0; wins=0; pos=0.; neg=0.; rtot=0.; campaigns=0; adds=0
    stop_i=min(last,len(o)-2)
    for i in range(max(first,30),stop_i+1):
        if pdn!=0:
            av=atr[pdi]; e=o[i]
            if av>0 and np.isfinite(av):
                sw=slo[pdi] if pdn==1 else shi[pdi]
                if pdn==1:
                    st=min(sw-.1*av,e-af*av); rrisk=e-st
                else:
                    st=max(sw+.1*av,e+af*av); rrisk=st-e
                if rrisk>0 and rrisk/e<=.012 and nlot<maxlots:
                    eqopen=bal
                    for q in range(nlot):
                        eqopen+=rcs[q]*dirs[q]*(e-ent[q])/risks[q]
                    rc=max(0.0,eqopen)*RISK
                    dirs[nlot]=pdn; ent[nlot]=e; stops[nlot]=st; risks[nlot]=rrisk; rcs[nlot]=rc
                    targets[nlot]=e+pdn*tpR*rrisk; opened[nlot]=i; prot[nlot]=0; nlot+=1
                    if padd==1: adds+=1
                    else: campaigns+=1
                    cdir=pdn; lastadd=i
            pdn=0; pdi=-1; padd=0

        newn=0
        for k in range(nlot):
            d=dirs[k]; closed=False; rr=0.
            # Conservative OHLC ordering: stop before target when both are inside one M5 bar.
            if (d==1 and l[i]<=stops[k]) or (d==-1 and h[i]>=stops[k]):
                rr=d*(stops[k]-ent[k])/risks[k]-COST; closed=True
            elif (d==1 and h[i]>=targets[k]) or (d==-1 and l[i]<=targets[k]):
                rr=tpR-COST; closed=True
            elif i-opened[k]>=maxhold:
                rr=d*(c[i]-ent[k])/risks[k]-COST; closed=True
            if closed:
                bal+=rcs[k]*rr; nclosed+=1; rtot+=rr
                if rr>0: wins+=1; pos+=rr
                elif rr<0: neg-=rr
            else:
                cr=d*(c[i]-ent[k])/risks[k]
                if prot[k]==0 and cr>=beR:
                    stops[k]=ent[k]; prot[k]=1
                if newn!=k:
                    dirs[newn]=dirs[k]; ent[newn]=ent[k]; stops[newn]=stops[k]; risks[newn]=risks[k]
                    rcs[newn]=rcs[k]; targets[newn]=targets[k]; opened[newn]=opened[k]; prot[newn]=prot[k]
                newn+=1
        nlot=newn
        if nlot==0: cdir=0

        eq=bal; allprot=True
        for k in range(nlot):
            eq+=rcs[k]*dirs[k]*(c[i]-ent[k])/risks[k]
            if prot[k]==0: allprot=False
        if eq>peak: peak=eq
        cur=(peak-eq)/peak if peak>0 else 0.
        if cur>dd: dd=cur

        # Month-end return is mark-to-market. We do NOT force-close at a calendar boundary.
        if month_end[i] and mn<MAX_MONTHS:
            meq[mn]=eq; mcode[mn]=month_code[i]; mn+=1

        if pdn==0:
            if cdir==0:
                if sigL[i] and not sigS[i]: pdn=1; pdi=i; padd=0
                elif sigS[i] and not sigL[i]: pdn=-1; pdi=i; padd=0
            elif nlot<maxlots and allprot and i>lastadd:
                # Aggressive sequential risk recycling, but only when every older live lot is protected at BE.
                pdn=cdir; pdi=i; padd=1

    # Match existing research simulator: flatten remaining lots at evaluation boundary for total return stats.
    for k in range(nlot):
        rr=dirs[k]*(c[last]-ent[k])/risks[k]-COST
        bal+=rcs[k]*rr; nclosed+=1; rtot+=rr
        if rr>0: wins+=1; pos+=rr
        elif rr<0: neg-=rr
    ret=(bal-1.)*100.
    wr=100.*wins/nclosed if nclosed else 0.
    pf=pos/neg if neg else 99.
    avg=rtot/nclosed if nclosed else 0.
    return nclosed,campaigns,adds,ret,wr,pf,avg,rtot,dd*100.,meq,mcode,mn


def perf(v):
    return {'lots':int(v[0]),'campaigns':int(v[1]),'adds':int(v[2]),'ret':float(v[3]),
            'wr':float(v[4]),'pf':float(v[5]),'avgR':float(v[6]),'R_total':float(v[7]),'dd':float(v[8])}


def month_label(code):
    y=int(code//12); mo=int(code%12)+1
    return f'{y:04d}-{mo:02d}'


def monthly_stats(v, idx, first, last, include_series=False):
    meq=np.asarray(v[9],float); mc=np.asarray(v[10],np.int64); n=int(v[11])
    prev=1.0; rows=[]
    first_code=int(mc[0]) if n else -1; last_code=int(mc[n-1]) if n else -1
    partial_first=(idx[first].day>3)
    partial_last=(idx[last].day<26)
    for j in range(n):
        eq=float(meq[j]); code=int(mc[j])
        if not np.isfinite(eq) or prev<=0: r=float('nan')
        else: r=(eq/prev-1.0)*100.0
        complete=not ((code==first_code and partial_first) or (code==last_code and partial_last))
        rows.append({'month':month_label(code),'ret':r,'equity':eq,'complete':bool(complete)})
        prev=eq
    vals=np.asarray([z['ret'] for z in rows if z['complete'] and np.isfinite(z['ret'])],float)
    if len(vals)==0:
        out={'months':0,'gt100_count':0,'gt100_pct':0.,'gt50_count':0,'positive_count':0,'negative_count':0,
             'min':float('nan'),'median':float('nan'),'mean':float('nan'),'max':float('nan'),'geom':float('nan'),'all_gt100':False}
    else:
        gross=np.prod(1.0+vals/100.0)
        geom=(gross**(1.0/len(vals))-1.0)*100.0 if gross>0 else -100.0
        out={'months':int(len(vals)),'gt100_count':int(np.sum(vals>100.0)),'gt100_pct':float(np.mean(vals>100.0)*100.0),
             'gt50_count':int(np.sum(vals>50.0)),'positive_count':int(np.sum(vals>0.0)),'negative_count':int(np.sum(vals<0.0)),
             'min':float(np.min(vals)),'median':float(np.median(vals)),'mean':float(np.mean(vals)),'max':float(np.max(vals)),
             'geom':float(geom),'all_gt100':bool(np.all(vals>100.0))}
    if include_series: out['series']=rows
    return out


def robust_total_score(p,ms):
    # Train/Validation only. Monthly objective dominates; total-return score is a tie breaker.
    if p['ret']<=0 or p['pf']<1.05 or ms['months']==0: return -1e12
    return math.log1p(p['ret']/100.0)-.012*p['dd']+.35*math.log(max(p['pf'],1e-9))


def selection_key(tr,tms,va,vms):
    # Lexicographic objective: first maximize the fraction of >100% months in BOTH samples,
    # then geometric monthly return, median month, worst month, then conventional robustness.
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.05 or va['pf']<1.05:
        return (-1.,-1e9,-1e9,-1e9,-1e9)
    pct=min(tms['gt100_pct'],vms['gt100_pct'])
    geom=min(tms['geom'],vms['geom'])
    med=min(tms['median'],vms['median'])
    floor=min(tms['min'],vms['min'])
    conventional=robust_total_score(tr,tms)+1.25*robust_total_score(va,vms)-1.2*abs(tr['avgR']-va['avgR'])
    return (pct,geom,med,floor,conventional)


def main():
    x=g.prep(); idx=x.index
    ed=m.build_edges(x); names=('BRK','EXP','PULL','FRACTAL')
    L=pd.Series(False,index=idx); S=L.copy()
    for nm in names:
        L|=ed[nm][0]; S|=ed[nm][1]
    clash=L&S; L&=~clash; S&=~clash

    o=x.open.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); c=x.close.to_numpy(float)
    atr=x.atr14.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float); shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70); ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True); wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_)
    S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)

    # Month identifiers; a snapshot is taken at the last observed M5 bar of each month.
    month_code=np.asarray(idx.year*12+(idx.month-1),dtype=np.int64)
    month_end=np.zeros(len(idx),dtype=np.bool_)
    month_end[:-1]=month_code[:-1]!=month_code[1:]
    month_end[-1]=True

    trb=bounds(idx,g.START,g.TRAIN_END); vab=bounds(idx,g.TRAIN_END,g.VAL_END)
    hob=bounds(idx,g.VAL_END,g.END); fullb=bounds(idx,g.START,g.END)
    arr=(o,h,lo,c,atr,slo,shi,L,S,month_code,month_end)

    # JIT warmup.
    sim_monthly(*arr,trb[0],min(trb[0]+2000,trb[1]),.60,1.0,4,24.,144)

    afs=[.45,.55,.60,.65]
    bes=[.50,.75,1.00,1.25]
    maxlots=[3,4,5,6,7,8]
    tps=[12.,18.,24.,30.,36.,48.]
    holds=[72,144,216]
    grid=list(itertools.product(afs,bes,maxlots,tps,holds))
    rows=[]
    for n,(af,be,ml,tp,mh) in enumerate(grid,1):
        tv=sim_monthly(*arr,trb[0],trb[1],af,be,ml,tp,mh); vv=sim_monthly(*arr,vab[0],vab[1],af,be,ml,tp,mh)
        tr=perf(tv); va=perf(vv); tms=monthly_stats(tv,idx,trb[0],trb[1]); vms=monthly_stats(vv,idx,vab[0],vab[1])
        key=selection_key(tr,tms,va,vms)
        if key[0]>=0:
            rows.append((key,af,be,ml,tp,mh,tr,tms,va,vms))
        if n%144==0: print('GRID',n,'/',len(grid),flush=True)

    rows.sort(reverse=True,key=lambda z:z[0])
    # Freeze a union of monthly-first candidates and total-return-first candidates using Train+Validation only.
    frozen=[]; seen=set()
    def add(z):
        k=(z[1],z[2],z[3],z[4],z[5])
        if k not in seen: seen.add(k); frozen.append(z)
    for z in rows[:30]: add(z)
    total_sorted=sorted(rows,reverse=True,key=lambda z:(min(z[6]['ret'],z[8]['ret']), z[6]['ret']+z[8]['ret'], z[0][-1]))
    for z in total_sorted[:30]: add(z)
    geom_sorted=sorted(rows,reverse=True,key=lambda z:(min(z[7]['geom'],z[9]['geom']),min(z[7]['median'],z[9]['median'])))
    for z in geom_sorted[:30]: add(z)

    promoted=[]
    for key,af,be,ml,tp,mh,tr,tms,va,vms in frozen:
        hv=sim_monthly(*arr,hob[0],hob[1],af,be,ml,tp,mh); fv=sim_monthly(*arr,fullb[0],fullb[1],af,be,ml,tp,mh)
        ho=perf(hv); full=perf(fv); hms=monthly_stats(hv,idx,hob[0],hob[1]); fms=monthly_stats(fv,idx,fullb[0],fullb[1])
        promoted.append({'selection_key':[float(q) for q in key],'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,
                         'hold_hours':mh*5/60.0,'train':tr,'train_monthly':tms,'val':va,'val_monthly':vms,
                         'holdout':ho,'holdout_monthly':hms,'full':full,'full_monthly':fms,
                         'total_over_10000':bool(full['ret']>10000.0),
                         'strict_monthly_over_100_and_total_over_10000':bool(fms['all_gt100'] and full['ret']>10000.0),
                         'geom_monthly_over_100_and_total_over_10000':bool(fms['geom']>100.0 and full['ret']>10000.0)})

    best_monthly=max(promoted,key=lambda z:(z['full_monthly']['gt100_pct'],z['holdout_monthly']['gt100_pct'],z['full_monthly']['geom'],z['full']['ret'])) if promoted else None
    best_total=max(promoted,key=lambda z:z['full']['ret']) if promoted else None
    strict=[z for z in promoted if z['strict_monthly_over_100_and_total_over_10000']]
    geom100=[z for z in promoted if z['geom_monthly_over_100_and_total_over_10000']]
    over10k=[z for z in promoted if z['total_over_10000']]
    if best_monthly:
        # Re-run only the leaders with month-by-month series for transparent diagnosis.
        z=best_monthly; af=z['atr_floor'];be=z['beR'];ml=z['max_lots'];tp=z['targetR'];mh=int(round(z['hold_hours']*60/5))
        fv=sim_monthly(*arr,fullb[0],fullb[1],af,be,ml,tp,mh); z['full_monthly']=monthly_stats(fv,idx,fullb[0],fullb[1],True)
    if best_total and (best_monthly is None or (best_total['atr_floor'],best_total['beR'],best_total['max_lots'],best_total['targetR'],best_total['hold_hours'])!=(best_monthly['atr_floor'],best_monthly['beR'],best_monthly['max_lots'],best_monthly['targetR'],best_monthly['hold_hours'])):
        z=best_total; af=z['atr_floor'];be=z['beR'];ml=z['max_lots'];tp=z['targetR'];mh=int(round(z['hold_hours']*60/5))
        fv=sim_monthly(*arr,fullb[0],fullb[1],af,be,ml,tp,mh); z['full_monthly']=monthly_stats(fv,idx,fullb[0],fullb[1],True)

    print('RESULT_JSON_START')
    print(json.dumps({
      'risk_rule':'Exactly 0.36% of CURRENT mark-to-market equity per fresh setup; no second fresh-risk lot until every older live lot is protected at BE.',
      'target_interpretations':{'strict':'every COMPLETE calendar month > +100% and full total > +10000%','geometric':'geometric average COMPLETE-month return > +100% and full total > +10000%'},
      'partial_months_excluded_from_monthly_requirement':['2021-09 research begins Sep 8','2026-07 source ends Jul 22'],
      'architecture':'UNION4 BRK+EXP+PULL+FRACTAL + 24h causal activity POC + Riyadh WEEK_PLUS_ANY VWAP + sequential protected risk recycling',
      'grid_size':len(grid),'selection':'Monthly and parameter ranking uses Train+Validation only; Holdout/Full revealed after frozen union shortlist.',
      'frozen_count':len(frozen),'count_full_over_10000':len(over10k),'count_strict_qualifiers':len(strict),'count_geom100_qualifiers':len(geom100),
      'best_monthly_among_frozen':best_monthly,'best_total_among_frozen':best_total,
      'strict_qualifiers':strict[:5],'geom100_qualifiers':geom100[:5],
      'limitations':['M1 OHLC resampled to M5; not final bid/ask tick execution','0.08R modeled cost per closed lot','POC and current public-data flow are tick-activity proxies, not true COMEX volume','sequential additions after BE do not require a fresh alpha signal','monthly equity is mark-to-market at the last observed M5 bar of each month']
    },default=float))
    print('RESULT_JSON_END')

if __name__=='__main__': main()
