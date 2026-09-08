import os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import gold_dukascopy_tick_validation as d

CANDIDATE='SQ03_EXP_PULL_WREL2PRICE2_POC96'
EDGES=('EXP','PULL')
VWAP_MODE='W_REL2_PRICE2'
PROFILE_LB=96
AF=.80; BE_R=2.25; MAX_LOTS=3; TP_R=28.; HOLD_HOURS=18.
EXTRAS=np.array([0.0,.02,.05,.10],dtype=float)


def build_signals(m1path):
    d.g.URLS=[m1path]; d.m.g.URLS=d.g.URLS; d.vp.g.URLS=d.g.URLS; d.vw.g.URLS=d.g.URLS; d.vc.g.URLS=d.g.URLS; d.g.END=d.END
    x=d.g.prep(); idx=x.index; ed=d.m.build_edges(x)
    L=pd.Series(False,index=idx); S=pd.Series(False,index=idx)
    for nm in EDGES: L|=ed[nm][0]; S|=ed[nm][1]
    clash=L&S; L&=~clash; S&=~clash
    c=x.close.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    poc,_,_=d.vp.profile_levels(h,lo,c,vol,PROFILE_LB,32,3,.70); ok=np.isfinite(poc)
    f=d.vw.vwap_ladder(x,3,True); wL,wS=d.vc.mk_masks(x,f)[VWAP_MODE]
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).fillna(False); S=(S&wS&pd.Series(ok&(c<poc),index=idx)).fillna(False)
    x=x.copy(); x['sigL']=L; x['sigS']=S; x['slo7']=x.low.rolling(7,min_periods=1).min(); x['shi7']=x.high.rolling(7,min_periods=1).max()
    return x


class Lot:
    __slots__=('d','entry','stop','risk','risk_cash','target','opened','protected')
    def __init__(self,direction,entry,stop,risk,risk_cash,target,opened):
        self.d=direction; self.entry=entry; self.stop=stop; self.risk=risk; self.risk_cash=risk_cash.copy(); self.target=target; self.opened=opened; self.protected=False


def sim_multi(x,hours):
    ns=len(EXTRAS)
    dec=x[(x.index>=d.TEST_START-pd.Timedelta(minutes=5))&(x.index<d.END)].copy()
    decisions=[(ts+pd.Timedelta(minutes=5),row) for ts,row in dec.iterrows()]
    di=0; pending=None; lots=[]; cdir=0
    bal=np.ones(ns,float); peak=np.ones(ns,float); dd=np.zeros(ns,float)
    campaigns=adds=closed=0; wins=np.zeros(ns,int); pos=np.zeros(ns,float); neg=np.zeros(ns,float); rtot=np.zeros(ns,float); maxopen=0
    last_bid=last_ask=np.nan

    def mtm_vec(bid,ask):
        eq=bal.copy()
        for z in lots:
            px=bid if z.d==1 else ask
            norm=z.d*(px-z.entry)/z.risk
            eq += z.risk_cash*norm
        return eq

    for hh,hts in enumerate(hours,1):
        ticks=d.iter_hour_ticks(hts)
        if not ticks: continue
        for t,bid,ask,bv,av in ticks:
            if t<d.TEST_START: continue
            if t>=d.END: break
            last_bid,last_ask=bid,ask
            while di<len(decisions) and decisions[di][0]<=t:
                dt,row=decisions[di]; di+=1
                midc=float(row['close'])
                for z in lots:
                    if (not z.protected) and z.d*(midc-z.entry)/z.risk>=BE_R:
                        z.stop=z.entry; z.protected=True
                if not lots: cdir=0
                allprot=bool(lots) and all(z.protected for z in lots)
                if cdir==0:
                    if bool(row['sigL']) and not bool(row['sigS']): pending=(1,row,False)
                    elif bool(row['sigS']) and not bool(row['sigL']): pending=(-1,row,False)
                elif len(lots)<MAX_LOTS and allprot:
                    fresh=(cdir==1 and bool(row['sigL']) and not bool(row['sigS'])) or (cdir==-1 and bool(row['sigS']) and not bool(row['sigL']))
                    if fresh: pending=(cdir,row,True)
            if pending is not None:
                direction,row,isadd=pending; e=ask if direction==1 else bid; avv=float(row['atr14']); sw=float(row['slo7']) if direction==1 else float(row['shi7'])
                if np.isfinite(avv) and avv>0:
                    st=min(sw-.1*avv,e-AF*avv) if direction==1 else max(sw+.1*avv,e+AF*avv)
                    rrisk=e-st if direction==1 else st-e
                    if rrisk>0 and rrisk/e<=.012 and len(lots)<MAX_LOTS:
                        eq=np.maximum(0.,mtm_vec(bid,ask)); rc=eq*d.RISK; tg=e+direction*TP_R*rrisk
                        lots.append(Lot(direction,e,st,rrisk,rc,tg,t)); maxopen=max(maxopen,len(lots)); cdir=direction
                        if isadd: adds+=1
                        else: campaigns+=1
                pending=None
            surv=[]
            for z in lots:
                raw_rr=None
                if z.d==1:
                    if bid<=z.stop: raw_rr=(bid-z.entry)/z.risk
                    elif bid>=z.target: raw_rr=TP_R
                else:
                    if ask>=z.stop: raw_rr=(z.entry-ask)/z.risk
                    elif ask<=z.target: raw_rr=TP_R
                if raw_rr is None and t-z.opened>=pd.Timedelta(hours=HOLD_HOURS):
                    px=bid if z.d==1 else ask; raw_rr=z.d*(px-z.entry)/z.risk
                if raw_rr is not None:
                    rrs=raw_rr-EXTRAS
                    bal += z.risk_cash*rrs; closed+=1; rtot+=rrs
                    wins += (rrs>0)
                    pos += np.where(rrs>0,rrs,0.)
                    neg += np.where(rrs<0,-rrs,0.)
                else: surv.append(z)
            lots=surv
            if not lots: cdir=0
            eq=mtm_vec(bid,ask); peak=np.maximum(peak,eq); cur=np.where(peak>0,(peak-eq)/peak,0.); dd=np.maximum(dd,cur)
        if hh%240==0: print('SIM_HOURS',hh,'/',len(hours),'closed',closed,flush=True)
    if np.isfinite(last_bid):
        for z in lots:
            px=last_bid if z.d==1 else last_ask; raw_rr=z.d*(px-z.entry)/z.risk; rrs=raw_rr-EXTRAS
            bal+=z.risk_cash*rrs; closed+=1; rtot+=rrs; wins+=(rrs>0); pos+=np.where(rrs>0,rrs,0.); neg+=np.where(rrs<0,-rrs,0.)
    out={}
    for j,extra in enumerate(EXTRAS):
        key=f'BIDASK_PLUS_{extra:.2f}R'
        out[key]={'lots':int(closed),'campaigns':int(campaigns),'adds':int(adds),'ret':float((bal[j]-1)*100),'wr':float(100*wins[j]/closed if closed else 0.),'pf':float(pos[j]/neg[j] if neg[j]>0 else 99.),'avgR':float(rtot[j]/closed if closed else 0.),'R_total':float(rtot[j]),'dd':float(100*dd[j]),'max_open':int(maxopen)}
    return out


def main():
    os.makedirs(d.RAW,exist_ok=True); hours=d.hours_range(); print('DOWNLOAD_HOURS',len(hours),flush=True)
    with ThreadPoolExecutor(max_workers=28) as ex:
        fut=[ex.submit(d.fetch_hour,t) for t in hours]; done=valid=byt=0
        for f in as_completed(fut):
            _,p,n=f.result(); done+=1; valid+=int(p is not None); byt+=n
            if done%240==0: print('DL',done,'/',len(hours),'valid',valid,'MB',round(byt/1e6,1),flush=True)
    m1path,diag=d.make_m1(hours); x=build_signals(m1path); print('DUKA_DATA',diag,flush=True)
    out=sim_multi(x,hours)
    for k,v in out.items(): print(CANDIDATE,k,v,flush=True)
    print('RESULT_JSON_START')
    print(json.dumps({'candidate':CANDIDATE,'source':'Dukascopy public XAUUSD BI5 bid/ask quote ticks','download_window':[str(d.DL_START),str(d.END)],'test_window':[str(d.TEST_START),str(d.END)],'data':diag,'edges':list(EDGES),'filters':{'vwap':VWAP_MODE,'activity_profile':'POC96 causal 32-bin proxy'},'params':{'atr_floor':AF,'beR':BE_R,'max_lots':MAX_LOTS,'targetR':TP_R,'hold_hours':HOLD_HOURS,'fresh_signal_add':True},'risk_rule':'0.36% executable bid/ask MTM equity per fresh lot; prior lots protected before add','results':out,'engine':'single tick pass, parallel equity accounting for all extra-cost scenarios; identical price-level trade events across scenarios','limitations':['Independent broker quote feed, not CME GC futures','Profile is quote-activity proxy, not COMEX traded volume-at-price','Six-week window validates execution sensitivity, not multi-year stability']},default=float))
    print('RESULT_JSON_END')

if __name__=='__main__': main()
