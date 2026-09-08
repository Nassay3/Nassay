import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_numba_grid as ng

SIM=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
GET='/tmp/getdata_norm.csv'

def normalize_get():
    z=pd.read_csv('/tmp/XAUUSD.csv').rename(columns={'datetime':'time','volume':'tick_volume'})
    z['time']=pd.to_datetime(z.time,utc=True);z=z[['time','open','high','low','close','tick_volume']].dropna().sort_values('time');z.to_csv(GET,index=False)

def prep(urls,end):
    g.URLS=urls;m.g.URLS=urls;g.END=end
    return g.prep()

def signal(x):
    ed=m.build_edges(x);L=(ed['BRK'][0]|ed['EXP'][0]).fillna(False);S=(ed['BRK'][1]|ed['EXP'][1]).fillna(False);z=L&S;return (L&~z).fillna(False),(S&~z).fillna(False),ed

def arrays(x,L,S):
    return (x.open.to_numpy(float),x.high.to_numpy(float),x.low.to_numpy(float),x.close.to_numpy(float),x.atr14.to_numpy(float),x.low.rolling(4,min_periods=1).min().to_numpy(float),x.high.rolling(4,min_periods=1).max().to_numpy(float),x.low.rolling(7,min_periods=1).min().to_numpy(float),x.high.rolling(7,min_periods=1).max().to_numpy(float),L.to_numpy(np.bool_),S.to_numpy(np.bool_))
def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)));return None if not len(ids) else (int(ids[0]),int(ids[-1]))
def run(x,L,S,a,b):
    bd=bounds(x.index,a,b)
    if bd is None:return None
    return ng.pack(ng.sim_numba(*arrays(x,L,S),bd[0],bd[1],1.0,6,1.0,6,15.0,144))

def main():
    normalize_get()
    main_end=pd.Timestamp('2026-07-23',tz='UTC');x=prep(SIM,main_end);L,S,ed=signal(x)
    # Frozen quarterly diagnostics; no parameter selection here.
    periods=[];cur=pd.Timestamp('2021-09-08',tz='UTC')
    while cur<main_end:
        nxt=min(cur+pd.DateOffset(months=3),main_end);periods.append({'start':str(cur),'end':str(nxt),'metrics':run(x,L,S,cur,nxt)});cur=nxt
    # Recent monthly slices for regime deterioration.
    months=[];cur=pd.Timestamp('2025-01-01',tz='UTC')
    while cur<main_end:
        nxt=min(cur+pd.DateOffset(months=1),main_end);months.append({'start':str(cur),'end':str(nxt),'metrics':run(x,L,S,cur,nxt)});cur=nxt
    # Cross-feed overlap after GetData has enough H1/VWMA warm-up.
    ov_start=pd.Timestamp('2026-07-18',tz='UTC');ov_end=pd.Timestamp('2026-07-22 19:00',tz='UTC')
    sim_metric=run(x,L,S,ov_start,ov_end)
    gx=prep([GET],pd.Timestamp('2026-09-05',tz='UTC'));gL,gS,ged=signal(gx);get_metric=run(gx,gL,gS,ov_start,ov_end)
    # Common-bar price and raw signal agreement.
    a=x.loc[(x.index>=ov_start)&(x.index<ov_end),['close']].rename(columns={'close':'sim'})
    b=gx.loc[(gx.index>=ov_start)&(gx.index<ov_end),['close']].rename(columns={'close':'get'})
    q=a.join(b,how='inner').dropna();corr=float(q.sim.corr(q['get'])) if len(q)>2 else None;med_abs_rel=float(((q['get']-q.sim).abs()/q.sim).median()*100) if len(q) else None
    ix=x.index.intersection(gx.index);mask=(ix>=ov_start)&(ix<ov_end);ix=ix[mask]
    def agree(sa,sb):
        A=set(ix[sa.reindex(ix,fill_value=False).to_numpy()]);B=set(ix[sb.reindex(ix,fill_value=False).to_numpy()]);u=len(A|B);return {'a':len(A),'b':len(B),'intersection':len(A&B),'jaccard':(len(A&B)/u if u else 1.0)}
    agreement={'BRK_long':agree(ed['BRK'][0],ged['BRK'][0]),'BRK_short':agree(ed['BRK'][1],ged['BRK'][1]),'EXP_long':agree(ed['EXP'][0],ged['EXP'][0]),'combined_long':agree(L,gL),'combined_short':agree(S,gS)}
    print('RESULT_JSON_START');print(json.dumps({'strategy':'Frozen BRK+EXP ATR1 swing6 BE1 max6 TP15 hold12h','quarterly':periods,'monthly_2025_2026':months,'cross_feed_overlap':{'window':[str(ov_start),str(ov_end)],'simom1':sim_metric,'getdata':get_metric,'common_bars':len(q),'close_corr':corr,'median_abs_relative_price_diff_pct':med_abs_rel,'signal_agreement':agreement},'interpretation_guardrails':['GetData starts Jul10 so overlap begins Jul18 to allow H1 VWMA175 warm-up','monthly/quarterly slices are diagnostics only and must not be used to retune parameters','cross-feed signal disagreement indicates feed sensitivity, not automatically strategy failure']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
