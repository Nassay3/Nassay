import glob, json
import numpy as np
import pandas as pd

import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

CANDIDATE='SQ03_EXP_PULL_WREL2PRICE2_POC96'
EDGES=('EXP','PULL')
VWAP_MODE='W_REL2_PRICE2'
PROFILE_LB=96
AF=.80; BE_R=2.25; MAX_LOTS=3; TP_R=28.; HOLD_MIN=18*60
RISK=.0036
EXTRAS=np.array([0.0,.02,.05,.10,.15],float)
START=pd.Timestamp('2021-09-08',tz='UTC')
END=pd.Timestamp('2026-06-23 17:00',tz='UTC')
SPLITS=[
 ('ERA1',START,pd.Timestamp('2023-01-01',tz='UTC')),
 ('ERA2',pd.Timestamp('2023-01-01',tz='UTC'),pd.Timestamp('2024-01-01',tz='UTC')),
 ('ERA3',pd.Timestamp('2024-01-01',tz='UTC'),pd.Timestamp('2025-01-01',tz='UTC')),
 ('HOLDOUT_2025PLUS',pd.Timestamp('2025-01-01',tz='UTC'),END),
 ('FULL',START,END),
]


def wire_signal_source():
    g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
    m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS
    g.END=pd.Timestamp('2026-07-22 19:02',tz='UTC')


def build_signals():
    wire_signal_source(); x=g.prep(); idx=x.index; ed=m.build_edges(x)
    L=pd.Series(False,index=idx); S=pd.Series(False,index=idx)
    for nm in EDGES: L|=ed[nm][0]; S|=ed[nm][1]
    clash=L&S; L&=~clash; S&=~clash
    c=x.close.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,PROFILE_LB,32,3,.70); ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True); wL,wS=vc.mk_masks(x,f)[VWAP_MODE]
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).fillna(False); S=(S&wS&pd.Series(ok&(c<poc),index=idx)).fillna(False)
    x=x.copy(); x['sigL']=L; x['sigS']=S; x['slo7']=x.low.rolling(7,min_periods=1).min(); x['shi7']=x.high.rolling(7,min_periods=1).max()
    return x


def load_side(side):
    fs=sorted(glob.glob(f'/tmp/dukam1/{side}/xauusd_{side}_m1_*.csv'))
    if not fs: raise RuntimeError(f'no {side} files')
    z=pd.concat((pd.read_csv(f) for f in fs),ignore_index=True)
    z['time']=pd.to_datetime(z['timestamp'],unit='ms',utc=True)
    z=z[['time','open','high','low','close']].dropna().drop_duplicates('time').sort_values('time')
    return z


def load_execution():
    a=load_side('ask').rename(columns={q:f'{q}_ask' for q in ('open','high','low','close')})
    b=load_side('bid').rename(columns={q:f'{q}_bid' for q in ('open','high','low','close')})
    z=b.merge(a,on='time',how='inner').sort_values('time')
    z=z[(z.time>=START-pd.Timedelta(days=2))&(z.time<=END)].copy()
    finite=np.ones(len(z),dtype=bool)
    for col in ['open_bid','high_bid','low_bid','close_bid','open_ask','high_ask','low_ask','close_ask']:
        finite &= np.isfinite(z[col].to_numpy(float))
    z=z[finite].copy()
    # Basic executable-side consistency.
    good=(z.open_ask>=z.open_bid)&(z.close_ask>=z.close_bid)&(z.high_ask>=z.low_ask)&(z.high_bid>=z.low_bid)
    bad=int((~good).sum()); z=z[good].copy()
    spr=(z.close_ask-z.close_bid).to_numpy(float)
    diag={'rows':int(len(z)),'start':str(z.time.min()),'end':str(z.time.max()),'bad_rows_dropped':bad,
          'spread_median':float(np.nanmedian(spr)),'spread_p95':float(np.nanpercentile(spr,95)),'spread_p99':float(np.nanpercentile(spr,99)),
          'spread_max':float(np.nanmax(spr))}
    return z,diag


class Lot:
    __slots__=('d','entry','stop','risk','rc','target','opened','protected')
    def __init__(self,d,e,st,r,rc,tg,op):
        self.d=d; self.entry=e; self.stop=st; self.risk=r; self.rc=rc.copy(); self.target=tg; self.opened=op; self.protected=False


def sim_segment(sig,exe,start,end):
    ns=len(EXTRAS); dec=sig[(sig.index>=start-pd.Timedelta(minutes=5))&(sig.index<end)].copy()
    dtime=(dec.index+pd.Timedelta(minutes=5)).asi8
    dc=dec.close.to_numpy(float); datr=dec.atr14.to_numpy(float); dslo=dec.slo7.to_numpy(float); dshi=dec.shi7.to_numpy(float); dL=dec.sigL.to_numpy(bool); dS=dec.sigS.to_numpy(bool)
    q=exe[(exe.time>=start)&(exe.time<end)].copy()
    if len(q)==0:return None
    times=q.time.array.asi8
    ob=q.open_bid.to_numpy(float); hb=q.high_bid.to_numpy(float); lb=q.low_bid.to_numpy(float); cb=q.close_bid.to_numpy(float)
    oa=q.open_ask.to_numpy(float); ha=q.high_ask.to_numpy(float); la=q.low_ask.to_numpy(float); ca=q.close_ask.to_numpy(float)
    bal=np.ones(ns); peak=np.ones(ns); dd=np.zeros(ns); wins=np.zeros(ns,int); pos=np.zeros(ns); neg=np.zeros(ns); rtot=np.zeros(ns)
    lots=[]; cdir=0; pending=None; di=0; campaigns=adds=closed=maxopen=0

    def mtm(px_bid,px_ask):
        eq=bal.copy()
        for z in lots:
            px=px_bid if z.d==1 else px_ask
            eq += z.rc*(z.d*(px-z.entry)/z.risk)
        return eq

    for i,t in enumerate(times):
        # Apply every newly completed M5 decision before this minute opens.
        while di<len(dtime) and dtime[di]<=t:
            midc=dc[di]
            for z in lots:
                if (not z.protected) and z.d*(midc-z.entry)/z.risk>=BE_R:
                    z.stop=z.entry; z.protected=True
            if not lots:cdir=0
            allprot=bool(lots) and all(z.protected for z in lots)
            if cdir==0:
                if dL[di] and not dS[di]: pending=(1,di,False)
                elif dS[di] and not dL[di]: pending=(-1,di,False)
            elif len(lots)<MAX_LOTS and allprot:
                fresh=(cdir==1 and dL[di] and not dS[di]) or (cdir==-1 and dS[di] and not dL[di])
                if fresh: pending=(cdir,di,True)
            di+=1
        if pending is not None:
            direction,j,isadd=pending; e=oa[i] if direction==1 else ob[i]; av=datr[j]; sw=dslo[j] if direction==1 else dshi[j]
            if np.isfinite(av) and av>0:
                st=min(sw-.1*av,e-AF*av) if direction==1 else max(sw+.1*av,e+AF*av)
                rrisk=e-st if direction==1 else st-e
                if rrisk>0 and rrisk/e<=.012 and len(lots)<MAX_LOTS:
                    rc=np.maximum(0.,mtm(ob[i],oa[i]))*RISK; tg=e+direction*TP_R*rrisk
                    lots.append(Lot(direction,e,st,rrisk,rc,tg,t)); maxopen=max(maxopen,len(lots)); cdir=direction
                    if isadd:adds+=1
                    else:campaigns+=1
            pending=None
        surv=[]
        for z in lots:
            raw=None
            if z.d==1:
                if lb[i]<=z.stop:
                    fill=ob[i] if ob[i]<=z.stop else z.stop; raw=(fill-z.entry)/z.risk
                elif hb[i]>=z.target: raw=TP_R
            else:
                if ha[i]>=z.stop:
                    fill=oa[i] if oa[i]>=z.stop else z.stop; raw=(z.entry-fill)/z.risk
                elif la[i]<=z.target: raw=TP_R
            if raw is None and (t-z.opened)>=HOLD_MIN*60*1_000_000_000:
                px=cb[i] if z.d==1 else ca[i]; raw=z.d*(px-z.entry)/z.risk
            if raw is None:
                surv.append(z)
            else:
                rr=raw-EXTRAS; bal+=z.rc*rr; rtot+=rr; wins+=(rr>0); pos+=np.where(rr>0,rr,0.); neg+=np.where(rr<0,-rr,0.); closed+=1
        lots=surv
        if not lots:cdir=0
        eqc=mtm(cb[i],ca[i]); peak=np.maximum(peak,eqc)
        # Conservative intraminute adverse mark for drawdown.
        eqa=bal.copy()
        for z in lots:
            px=lb[i] if z.d==1 else ha[i]
            eqa += z.rc*(z.d*(px-z.entry)/z.risk)
        dd=np.maximum(dd,np.where(peak>0,(peak-eqa)/peak,0.))
    if lots:
        i=len(q)-1
        for z in lots:
            px=cb[i] if z.d==1 else ca[i]; raw=z.d*(px-z.entry)/z.risk; rr=raw-EXTRAS
            bal+=z.rc*rr; rtot+=rr; wins+=(rr>0); pos+=np.where(rr>0,rr,0.); neg+=np.where(rr<0,-rr,0.); closed+=1
    out={}
    for j,xtra in enumerate(EXTRAS):
        out[f'BIDASK_M1_PLUS_{xtra:.2f}R']={'lots':int(closed),'campaigns':int(campaigns),'adds':int(adds),'ret':float((bal[j]-1)*100),
             'wr':float(100*wins[j]/closed if closed else 0.),'pf':float(pos[j]/neg[j] if neg[j]>0 else 99.),'avgR':float(rtot[j]/closed if closed else 0.),
             'R_total':float(rtot[j]),'dd':float(100*dd[j]),'max_open':int(maxopen)}
    return {'minutes':int(len(q)),'signals_long':int(dL.sum()),'signals_short':int(dS.sum()),'results':out}


def main():
    sig=build_signals(); exe,diag=load_execution(); print('EXEC_DATA',diag,flush=True)
    results={}
    for name,a,b in SPLITS:
        r=sim_segment(sig,exe,a,b); results[name]=r; print(name,json.dumps(r,default=float),flush=True)
    print('RESULT_JSON_START')
    print(json.dumps({'candidate':CANDIDATE,'signal_source':'simom1 XAUUSD M1 tick-volume history; causal M5 signals','execution_source':'independent Dukascopy M1 BID/ASK monthly dataset','execution_data':diag,
        'window':[str(START),str(END)],'edges':list(EDGES),'filters':{'vwap':VWAP_MODE,'activity_profile':'POC96 based on signal-source tick activity'},
        'params':{'atr_floor':AF,'beR':BE_R,'max_lots':MAX_LOTS,'targetR':TP_R,'hold_hours':HOLD_MIN/60,'fresh_signal_add':True},
        'risk_rule':'0.36% current executable bid/ask MTM equity per fresh lot; existing lots protected before add',
        'execution':'decision after completed M5 bar; entry at next available M1 ask for long/bid for short; long exits bid, short exits ask; variable spread implicit; stop-first if stop and target both touch same M1; gap-through stop fills at M1 open; extra cost stress applied in R',
        'splits':results,
        'limitations':['M1 BID/ASK does not reveal intraminute tick order; stop-first is conservative when both levels touch.','Signal source is not Dukascopy because the public BID/ASK dataset has no tick-volume column; this test isolates execution/spread robustness rather than fully independent signal replication.','Dukascopy spot quote feed is not CME GC futures.']},default=float))
    print('RESULT_JSON_END')

if __name__=='__main__':main()
