import os, json, lzma, struct, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc

RAW='/tmp/duka_xau'
DL_START=pd.Timestamp('2026-07-10 00:00',tz='UTC')
TEST_START=pd.Timestamp('2026-07-23 00:00',tz='UTC')
END=pd.Timestamp('2026-09-05 00:00',tz='UTC')
RISK=.0036
REC=struct.Struct('>IIIff')
SCALE=1000.0


def url_for(ts):
    return f"https://datafeed.dukascopy.com/datafeed/XAUUSD/{ts.year}/{ts.month-1:02d}/{ts.day:02d}/{ts.hour:02d}h_ticks.bi5"

def path_for(ts):
    return os.path.join(RAW,ts.strftime('%Y%m%d_%H.bi5'))

def fetch_hour(ts):
    p=path_for(ts)
    if os.path.exists(p): return str(ts),p,os.path.getsize(p)
    try:
        req=urllib.request.Request(url_for(ts),headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=20) as r:data=r.read()
        if not data:return str(ts),None,0
        os.makedirs(RAW,exist_ok=True)
        with open(p,'wb') as f:f.write(data)
        return str(ts),p,len(data)
    except Exception:
        return str(ts),None,0

def hours_range():
    return list(pd.date_range(DL_START,END-pd.Timedelta(hours=1),freq='1h',tz='UTC'))

def decode_bytes(data,base):
    try: raw=lzma.decompress(data)
    except Exception:return []
    if len(raw)%REC.size:return []
    out=[]
    for off in range(0,len(raw),REC.size):
        ms,ask,bid,av,bv=REC.unpack_from(raw,off)
        if ask<=0 or bid<=0:continue
        out.append((base+pd.Timedelta(milliseconds=int(ms)),bid/SCALE,ask/SCALE,float(bv),float(av)))
    return out

def iter_hour_ticks(ts):
    p=path_for(ts)
    if not os.path.exists(p):return []
    with open(p,'rb') as f:data=f.read()
    return decode_bytes(data,ts)

def make_m1(hours):
    rows=[];spreads=[];nt=0;valid_hours=0
    for ix,ts in enumerate(hours,1):
        ticks=iter_hour_ticks(ts)
        if not ticks:continue
        valid_hours+=1;nt+=len(ticks)
        t=pd.DataFrame(ticks,columns=['time','bid','ask','bid_vol','ask_vol'])
        t['mid']=(t.bid+t.ask)/2.0;t['spread']=t.ask-t.bid
        spreads.extend(t.spread.iloc[::max(1,len(t)//100)].tolist())
        t['minute']=t.time.dt.floor('min')
        q=t.groupby('minute',sort=True).agg(open=('mid','first'),high=('mid','max'),low=('mid','min'),close=('mid','last'),tick_volume=('mid','size')).reset_index().rename(columns={'minute':'time'})
        rows.append(q)
        if ix%240==0:print('M1_HOURS',ix,'/',len(hours),'ticks',nt,flush=True)
    z=pd.concat(rows,ignore_index=True).drop_duplicates('time').sort_values('time')
    p='/tmp/duka_m1.csv';z.to_csv(p,index=False)
    a=np.asarray(spreads,float)
    diag={'download_hours':len(hours),'valid_hours':valid_hours,'ticks':nt,'m1_rows':len(z),'spread_median':float(np.nanmedian(a)),'spread_p95':float(np.nanpercentile(a,95)),'spread_p99':float(np.nanpercentile(a,99))}
    return p,diag

def build_signals(m1path):
    g.URLS=[m1path];m.g.URLS=g.URLS;vp.g.URLS=g.URLS;vw.g.URLS=g.URLS;vc.g.URLS=g.URLS;g.END=END
    x=g.prep();idx=x.index;ed=m.build_edges(x)
    # WF69 was frozen on UNION3 only. FRACTAL is deliberately excluded.
    names=('BRK','EXP','PULL')
    L=pd.Series(False,index=idx);S=pd.Series(False,index=idx)
    for nm in names:L|=ed[nm][0];S|=ed[nm][1]
    clash=L&S;L&=~clash;S&=~clash
    c=x.close.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);ok=np.isfinite(poc)
    f=vw.vwap_ladder(x,3,True);wL,wS=vc.mk_masks(x,f)['WEEK_PLUS_ANY']
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).fillna(False)
    S=(S&wS&pd.Series(ok&(c<poc),index=idx)).fillna(False)
    x=x.copy();x['sigL']=L;x['sigS']=S;x['slo7']=x.low.rolling(7,min_periods=1).min();x['shi7']=x.high.rolling(7,min_periods=1).max()
    return x

class Lot:
    __slots__=('d','entry','stop','risk','risk_cash','target','opened','protected')
    def __init__(self,d,e,st,r,rc,tg,op):self.d=d;self.entry=e;self.stop=st;self.risk=r;self.risk_cash=rc;self.target=tg;self.opened=op;self.protected=False

def sim_ticks(x,hours,af,beR,maxlots,tpR,hold_hours,extra_costR=0.0):
    # Decisions are made only after a completed M5 bar; first tick >= decision time is executable.
    # WF69 requires a fresh same-direction signal for every add.
    dec=x[(x.index>=TEST_START-pd.Timedelta(minutes=5))&(x.index<END)].copy()
    decisions=[]
    for ts,row in dec.iterrows():decisions.append((ts+pd.Timedelta(minutes=5),row))
    di=0;pending=None;lots=[];cdir=0;bal=1.0;peak=1.0;dd=0.;campaigns=adds=closed=wins=0;pos=neg=rtot=0.;maxopen=0
    last_bid=last_ask=np.nan
    def mtm(bid,ask):
        e=bal
        for z in lots:
            px=bid if z.d==1 else ask
            e+=z.risk_cash*z.d*(px-z.entry)/z.risk
        return e
    for hh,hts in enumerate(hours,1):
        ticks=iter_hour_ticks(hts)
        if not ticks:continue
        for t,bid,ask,bv,av in ticks:
            if t<TEST_START:continue
            if t>=END:break
            last_bid,last_ask=bid,ask
            while di<len(decisions) and decisions[di][0]<=t:
                dt,row=decisions[di];di+=1
                midc=float(row['close'])
                for z in lots:
                    if not z.protected and z.d*(midc-z.entry)/z.risk>=beR:
                        z.stop=z.entry;z.protected=True
                if not lots:cdir=0
                allprot=bool(lots) and all(z.protected for z in lots)
                if cdir==0:
                    if bool(row['sigL']) and not bool(row['sigS']):pending=(1,row,False)
                    elif bool(row['sigS']) and not bool(row['sigL']):pending=(-1,row,False)
                elif len(lots)<maxlots and allprot:
                    fresh=(cdir==1 and bool(row['sigL']) and not bool(row['sigS'])) or (cdir==-1 and bool(row['sigS']) and not bool(row['sigL']))
                    if fresh:pending=(cdir,row,True)
            if pending is not None:
                d,row,isadd=pending;e=ask if d==1 else bid;avv=float(row['atr14'])
                sw=float(row['slo7']) if d==1 else float(row['shi7'])
                if np.isfinite(avv) and avv>0:
                    st=min(sw-.1*avv,e-af*avv) if d==1 else max(sw+.1*avv,e+af*avv)
                    rrisk=e-st if d==1 else st-e
                    if rrisk>0 and rrisk/e<=.012 and len(lots)<maxlots:
                        eq=max(0.,mtm(bid,ask));rc=eq*RISK;tg=e+d*tpR*rrisk
                        lots.append(Lot(d,e,st,rrisk,rc,tg,t));maxopen=max(maxopen,len(lots));cdir=d
                        if isadd:adds+=1
                        else:campaigns+=1
                pending=None
            surv=[]
            for z in lots:
                rr=None
                if z.d==1:
                    if bid<=z.stop:rr=(bid-z.entry)/z.risk
                    elif bid>=z.target:rr=tpR
                else:
                    if ask>=z.stop:rr=(z.entry-ask)/z.risk
                    elif ask<=z.target:rr=tpR
                if rr is None and t-z.opened>=pd.Timedelta(hours=hold_hours):
                    px=bid if z.d==1 else ask;rr=z.d*(px-z.entry)/z.risk
                if rr is not None:
                    rr-=extra_costR
                    bal+=z.risk_cash*rr;closed+=1;rtot+=rr
                    if rr>0:wins+=1;pos+=rr
                    elif rr<0:neg-=rr
                else:surv.append(z)
            lots=surv
            if not lots:cdir=0
            eq=mtm(bid,ask);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak if peak>0 else 0.)
        if hh%240==0:print('SIM_HOURS',hh,'/',len(hours),'closed',closed,flush=True)
    if np.isfinite(last_bid):
        for z in lots:
            px=last_bid if z.d==1 else last_ask;rr=z.d*(px-z.entry)/z.risk-extra_costR
            bal+=z.risk_cash*rr;closed+=1;rtot+=rr
            if rr>0:wins+=1;pos+=rr
            elif rr<0:neg-=rr
    return {'lots':closed,'campaigns':campaigns,'adds':adds,'ret':(bal-1)*100,'wr':100*wins/closed if closed else 0.,'pf':pos/neg if neg else 99.,'avgR':rtot/closed if closed else 0.,'R_total':rtot,'dd':100*dd,'max_open':maxopen}

def main():
    os.makedirs(RAW,exist_ok=True);hours=hours_range()
    print('DOWNLOAD_HOURS',len(hours),flush=True)
    with ThreadPoolExecutor(max_workers=20) as ex:
        fut=[ex.submit(fetch_hour,t) for t in hours]
        done=0;valid=0;byt=0
        for f in as_completed(fut):
            _,p,n=f.result();done+=1;valid+=int(p is not None);byt+=n
            if done%240==0:print('DL',done,'/',len(hours),'valid',valid,'MB',round(byt/1e6,1),flush=True)
    m1path,datadiag=make_m1(hours);x=build_signals(m1path)
    print('DUKA_DATA',datadiag,flush=True)
    af,be,ml,tp,hold=.80,2.25,3,28.,18.
    out={}
    for extra in (0.0,.02,.05,.10):
        key=f'BIDASK_PLUS_{extra:.2f}R'
        out[key]=sim_ticks(x,hours,af,be,ml,tp,hold,extra)
        print('WF69',key,out[key],flush=True)
    print('RESULT_JSON_START')
    print(json.dumps({'candidate':'WF69_FROZEN','source':'Dukascopy public XAUUSD BI5 quote ticks','download_window':[str(DL_START),str(END)],'test_window':[str(TEST_START),str(END)],'data':datadiag,'edges':['BRK','EXP','PULL'],'params':{'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':hold,'fresh_signal_add':True},'filters':'causal 24h activity POC + Riyadh WEEK_PLUS_ANY VWAP consensus','risk_rule':'0.36% of current executable bid/ask MTM equity per fresh lot; prior live lots must be protected before add','execution':'long enters ask/exits bid; short enters bid/exits ask; variable spread implicit; stop can fill through level at observed quote; TP at limit level after executable-side cross; optional extra round-trip cost stress in R','results':out,'limitations':['Dukascopy is an independent broker quote feed, not CME futures','extra_costR is sensitivity stress, not a claim about exact broker commission','Signal levels/profile use quote activity rather than COMEX traded volume','Six-week validation cannot establish multi-year stability']},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
