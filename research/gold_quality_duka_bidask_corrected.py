import json
import numpy as np
import pandas as pd
import gold_quality_duka_bidask as qsel

# qsel imports and freezes the selected candidate into this shared module.
d=qsel.d


def build_signals_corrected():
    x=qsel.build_quality_signals()
    # Signal-source next M5 open is used ONLY to convert structural stop levels into a stop DISTANCE.
    # That distance is then translated onto the independent executable feed entry price.
    x=x.copy()
    x['next_open_signal']=x.open.shift(-1)
    return x


def sim_segment_corrected(sig,exe,start,end):
    ns=len(d.EXTRAS)
    dec=sig[(sig.index>=start-pd.Timedelta(minutes=5))&(sig.index<end)].copy()
    dtime=pd.DatetimeIndex(dec.index+pd.Timedelta(minutes=5)).as_unit('ns').asi8
    datr=dec.atr14.to_numpy(float); dslo=dec.slo7.to_numpy(float); dshi=dec.shi7.to_numpy(float)
    denext=dec.next_open_signal.to_numpy(float); dL=dec.sigL.to_numpy(bool); dS=dec.sigS.to_numpy(bool)
    q=exe[(exe.time>=start)&(exe.time<end)].copy()
    if len(q)==0:return None
    times=pd.DatetimeIndex(q.time).as_unit('ns').asi8
    ob=q.open_bid.to_numpy(float);hb=q.high_bid.to_numpy(float);lb=q.low_bid.to_numpy(float);cb=q.close_bid.to_numpy(float)
    oa=q.open_ask.to_numpy(float);ha=q.high_ask.to_numpy(float);la=q.low_ask.to_numpy(float);ca=q.close_ask.to_numpy(float)
    bal=np.ones(ns);peak=np.ones(ns);dd=np.zeros(ns);wins=np.zeros(ns,int);pos=np.zeros(ns);neg=np.zeros(ns);rtot=np.zeros(ns)
    lots=[];cdir=0;pending=None;di=0;campaigns=adds=closed=maxopen=0

    def mtm(px_bid,px_ask):
        eq=bal.copy()
        for z in lots:
            px=px_bid if z.d==1 else px_ask
            eq += z.rc*(z.d*(px-z.entry)/z.risk)
        return eq

    for i,t in enumerate(times):
        while di<len(dtime) and dtime[di]<=t:
            # BE is based on the executable side of the independent feed, never the signal-feed absolute price.
            if i>0:
                px_bid=cb[i-1];px_ask=ca[i-1]
            else:
                px_bid=ob[i];px_ask=oa[i]
            for z in lots:
                px=px_bid if z.d==1 else px_ask
                if (not z.protected) and z.d*(px-z.entry)/z.risk>=d.BE_R:
                    z.stop=z.entry;z.protected=True
            if not lots:cdir=0
            allprot=bool(lots) and all(z.protected for z in lots)
            if cdir==0:
                if dL[di] and not dS[di]:pending=(1,di,False)
                elif dS[di] and not dL[di]:pending=(-1,di,False)
            elif len(lots)<d.MAX_LOTS and allprot:
                fresh=(cdir==1 and dL[di] and not dS[di]) or (cdir==-1 and dS[di] and not dL[di])
                if fresh:pending=(cdir,di,True)
            di+=1

        if pending is not None:
            direction,j,isadd=pending
            e=oa[i] if direction==1 else ob[i]
            av=datr[j]; es=denext[j]
            if np.isfinite(av) and av>0 and np.isfinite(es) and es>0:
                sw=dslo[j] if direction==1 else dshi[j]
                if direction==1:
                    st_sig=min(sw-.1*av,es-d.AF*av); risk_sig=es-st_sig
                else:
                    st_sig=max(sw+.1*av,es+d.AF*av); risk_sig=st_sig-es
                # Preserve structural risk as a percentage across feeds; ratio is ~1 for XAUUSD but removes basis distortion.
                rrisk=risk_sig*(e/es)
                if rrisk>0 and rrisk/e<=.012 and len(lots)<d.MAX_LOTS:
                    st=e-direction*rrisk
                    rc=np.maximum(0.,mtm(ob[i],oa[i]))*d.RISK
                    tg=e+direction*d.TP_R*rrisk
                    lots.append(d.Lot(direction,e,st,rrisk,rc,tg,t));maxopen=max(maxopen,len(lots));cdir=direction
                    if isadd:adds+=1
                    else:campaigns+=1
            pending=None

        surv=[]
        for z in lots:
            raw=None
            if z.d==1:
                if lb[i]<=z.stop:
                    fill=ob[i] if ob[i]<=z.stop else z.stop;raw=(fill-z.entry)/z.risk
                elif hb[i]>=z.target:
                    raw=(z.target-z.entry)/z.risk
            else:
                if ha[i]>=z.stop:
                    fill=oa[i] if oa[i]>=z.stop else z.stop;raw=(z.entry-fill)/z.risk
                elif la[i]<=z.target:
                    raw=(z.entry-z.target)/z.risk
            if raw is None and (t-z.opened)>=d.HOLD_MIN*60*1_000_000_000:
                px=cb[i] if z.d==1 else ca[i];raw=z.d*(px-z.entry)/z.risk
            if raw is None:
                surv.append(z)
            else:
                rr=raw-d.EXTRAS;bal+=z.rc*rr;rtot+=rr;wins+=(rr>0);pos+=np.where(rr>0,rr,0.);neg+=np.where(rr<0,-rr,0.);closed+=1
        lots=surv
        if not lots:cdir=0
        eqc=mtm(cb[i],ca[i]);peak=np.maximum(peak,eqc)
        eqa=bal.copy()
        for z in lots:
            px=lb[i] if z.d==1 else ha[i]
            eqa += z.rc*(z.d*(px-z.entry)/z.risk)
        dd=np.maximum(dd,np.where(peak>0,(peak-eqa)/peak,0.))

    if lots:
        i=len(q)-1
        for z in lots:
            px=cb[i] if z.d==1 else ca[i];raw=z.d*(px-z.entry)/z.risk;rr=raw-d.EXTRAS
            bal+=z.rc*rr;rtot+=rr;wins+=(rr>0);pos+=np.where(rr>0,rr,0.);neg+=np.where(rr<0,-rr,0.);closed+=1

    out={}
    for j,xtra in enumerate(d.EXTRAS):
        out[f'BIDASK_M1_PLUS_{xtra:.2f}R']={'lots':int(closed),'campaigns':int(campaigns),'adds':int(adds),'ret':float((bal[j]-1)*100),
            'wr':float(100*wins[j]/closed if closed else 0.),'pf':float(pos[j]/neg[j] if neg[j]>0 else 99.),
            'avgR':float(rtot[j]/closed if closed else 0.),'R_total':float(rtot[j]),'dd':float(100*dd[j]),'max_open':int(maxopen)}
    return {'minutes':int(len(q)),'signals_long':int(dL.sum()),'signals_short':int(dS.sum()),'results':out}


def basis_diag(sig,exe):
    z=exe.copy();z['mid']=(z.close_bid+z.close_ask)/2
    mid5=z.set_index('time')['mid'].resample('5min',label='left',closed='left').last()
    j=pd.DataFrame({'signal_close':sig.close}).join(mid5.rename('exec_mid'),how='inner').dropna()
    j=j[(j.index>=d.START)&(j.index<=d.END)]
    diff=(j.exec_mid-j.signal_close).to_numpy(float);rel=diff/j.signal_close.to_numpy(float)
    return {'matched_m5':int(len(j)),'median_abs_price_diff':float(np.median(np.abs(diff))),
            'p95_abs_price_diff':float(np.percentile(np.abs(diff),95)),'median_signed_price_diff':float(np.median(diff)),
            'median_abs_rel_bps':float(np.median(np.abs(rel))*10000),'close_corr':float(j.signal_close.corr(j.exec_mid))}


def main():
    sig=build_signals_corrected();exe,ediag=d.load_execution();bdiag=basis_diag(sig,exe)
    print('EXEC_DATA',ediag,flush=True);print('BASIS_DIAG',bdiag,flush=True)
    results={}
    for name,a,b in d.SPLITS:
        r=sim_segment_corrected(sig,exe,a,b);results[name]=r;print(name,json.dumps(r,default=float),flush=True)
    print('RESULT_JSON_START')
    print(json.dumps({'candidate':d.CANDIDATE,'execution_engine':'CORRECTED_DISTANCE_TRANSLATION_V1','signal_source':'simom1 XAUUSD M1 tick-volume history; causal M5 signals',
      'execution_source':'independent Dukascopy M1 BID/ASK','execution_data':ediag,'basis_diag':bdiag,'window':[str(d.START),str(d.END)],
      'edges':['PULL'],'filters':{'vwap':'W_REL2_PRICE2','profile':'24h POC and >=0.25 ATR momentum away from POC'},
      'params':{'atr_floor':d.AF,'beR':d.BE_R,'max_lots':d.MAX_LOTS,'targetR':d.TP_R,'hold_hours':d.HOLD_MIN/60,'fresh_signal_add':True},
      'risk_rule':'0.36% current executable BID/ASK MTM equity per fresh lot; all prior lots protected before add',
      'corrections':['Structural stop converted to distance on signal feed then translated to executable entry','BE evaluated on executable bid/ask rather than signal-feed absolute price','Variable spread remains implicit in executable sides','Stop-first remains conservative inside each M1 bar'],
      'splits':results,'limitations':['M1 bid/ask still lacks intraminute tick ordering','Signal generation still uses separate tick-volume source','Dukascopy spot is not CME GC futures']},default=float))
    print('RESULT_JSON_END')

if __name__=='__main__':main()
