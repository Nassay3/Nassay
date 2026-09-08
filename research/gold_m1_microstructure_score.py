import json, math, itertools
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_10000_equity_risk as er

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS; er.g.URLS=g.URLS

def bounds(idx,a,b):
    z=np.flatnonzero(np.asarray((idx>=a)&(idx<b))); return int(z[0]),int(z[-1])
def pack(v): return er.pack(v)

def raw_m1():
    out=[]
    for p in g.URLS:
        d=pd.read_csv(p,usecols=['time','open','high','low','close','tick_volume'])
        d['time']=pd.to_datetime(d.time,utc=True)
        d=d[(d.time>=g.WARMUP)&(d.time<g.END)]
        for c in ['open','high','low','close','tick_volume']: d[c]=pd.to_numeric(d[c],errors='coerce')
        out.append(d.dropna())
    return pd.concat(out,ignore_index=True).drop_duplicates('time').sort_values('time').set_index('time')

def micro_features(m1):
    d=m1.copy(); rng=(d.high-d.low).replace(0,np.nan)
    # Explicit proxies only: source has broker tick_volume, not exchange trades/aggressor side.
    tick_dir=np.sign(d.close.diff()).fillna(0.0)
    d['signed_tv']=d.tick_volume*tick_dir
    d['clv']=((2*d.close-d.high-d.low)/rng).clip(-1,1).fillna(0.0)
    d['pressure_tv']=d.tick_volume*d.clv
    d['buy_proxy']=d.tick_volume*(d.clv+1)/2
    d['sell_proxy']=d.tick_volume*(1-d.clv)/2
    d['bull_min']=(d.close>d.open).astype(int); d['bear_min']=(d.close<d.open).astype(int)
    d['last1_tvchg']=d.tick_volume/d.tick_volume.shift(1).replace(0,np.nan)-1
    d['last1_pressure']=d.clv

    def agg(rule,mins):
        z=d.resample(rule,origin='epoch',label='left',closed='left').agg(
            tv=('tick_volume','sum'), signed=('signed_tv','sum'), pressure=('pressure_tv','sum'),
            buy=('buy_proxy','sum'), sell=('sell_proxy','sum'), bull=('bull_min','sum'), bear=('bear_min','sum'),
            last1_tvchg=('last1_tvchg','last'), last1_pressure=('last1_pressure','last'))
        z['qps']=z.tv/(mins*60.0)
        z['tvchg']=z.tv/z.tv.shift(1).replace(0,np.nan)-1
        z['qpschg']=z.qps/z.qps.shift(1).replace(0,np.nan)-1
        z['activity_rel30']=z.tv/z.tv.shift(1).rolling(30,min_periods=10).median().replace(0,np.nan)
        z['cvd_proxy']=z.signed/z.tv.replace(0,np.nan)
        z['pressure']=z.pressure/z.tv.replace(0,np.nan)
        z['bs_imb_proxy']=(z.buy-z.sell)/(z.buy+z.sell).replace(0,np.nan)
        z['minute_imb']=(z.bull-z.bear)/(z.bull+z.bear).replace(0,np.nan)
        z['available']=z.index+pd.Timedelta(minutes=mins)
        return z
    f5=agg('5min',5).add_prefix('f5_'); f5['available']=f5.index+pd.Timedelta(minutes=5)
    f15=agg('15min',15).add_prefix('f15_'); f15['available']=f15.index+pd.Timedelta(minutes=15)
    return f5.reset_index(drop=False),f15.reset_index(drop=False)

def add_micro(x,f5,f15):
    b=x.copy(); b['decision']=b.index+pd.Timedelta(minutes=5); b=b.reset_index().rename(columns={'bar_time':'m5_time','time':'m5_time'})
    b=pd.merge_asof(b.sort_values('decision'),f5.sort_values('available'),on='decision',direction='backward')
    b=pd.merge_asof(b.sort_values('decision'),f15.sort_values('available'),on='decision',direction='backward',suffixes=('','_15x'))
    # restore original bar index robustly
    if 'm5_time' in b.columns: b=b.set_index('m5_time')
    else: b.index=x.index
    return b.sort_index()

def union(ed,names,idx):
    L=pd.Series(False,index=idx); S=L.copy()
    for nm in names: L|=ed[nm][0]; S|=ed[nm][1]
    clash=L&S; return L&~clash,S&~clash

def flow_scores(x):
    # Directional score; activity components are non-directional but require participation acceleration.
    long=np.zeros(len(x),np.int8); short=np.zeros(len(x),np.int8)
    def adddir(condL,condS):
        nonlocal long,short
        long += np.asarray(condL.fillna(False),np.int8); short += np.asarray(condS.fillna(False),np.int8)
    adddir(x.f5_cvd_proxy>0, x.f5_cvd_proxy<0)
    adddir(x.f15_cvd_proxy>0, x.f15_cvd_proxy<0)
    adddir(x.f5_pressure>.05, x.f5_pressure<-.05)
    adddir(x.f15_pressure>.03, x.f15_pressure<-.03)
    adddir(x.f5_bs_imb_proxy>.05, x.f5_bs_imb_proxy<-.05)
    adddir(x.f5_minute_imb>0, x.f5_minute_imb<0)
    adddir(x.f5_last1_pressure>.10, x.f5_last1_pressure<-.10)
    active=((x.f5_tvchg>0)|(x.f5_qpschg>0)|(x.f5_activity_rel30>1.10)).fillna(False)
    long += np.asarray(active,np.int8); short += np.asarray(active,np.int8)
    accel=((x.f5_activity_rel30>1.25)&(x.f5_last1_tvchg>0)).fillna(False)
    long += np.asarray(accel,np.int8); short += np.asarray(accel,np.int8)
    return long,short

def robust_score(tr,va):
    if tr['ret']<=0 or va['ret']<=0 or tr['pf']<1.06 or va['pf']<1.06:return -1e9
    return 2.8*min(tr['wr'],va['wr']) + 12*math.log1p(tr['ret']/100)+18*math.log1p(va['ret']/100)-.35*tr['dd']-.55*va['dd']-20*abs(tr['avgR']-va['avgR'])

def main():
    x=g.prep(); m1=raw_m1(); f5,f15=micro_features(m1); x=add_micro(x,f5,f15); idx=x.index
    ed=m.build_edges(x)
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70);pocL=pd.Series(np.isfinite(poc)&(c>poc),index=idx);pocS=pd.Series(np.isfinite(poc)&(c<poc),index=idx)
    vf=vw.vwap_ladder(x,3,True);vms=vc.mk_masks(x,vf)
    fsL,fsS=flow_scores(x)
    zL=((x.z48>0)&(x.z84>0)).fillna(False); zS=((x.z48<0)&(x.z84<0)).fillna(False)
    sigs={'UNION4':('BRK','EXP','PULL','FRACTAL'),'EXP_PULL':('EXP','PULL'),'UNION3':('BRK','EXP','PULL')}
    trb=bounds(idx,g.START,g.TRAIN_END);vab=bounds(idx,g.TRAIN_END,g.VAL_END);hob=bounds(idx,g.VAL_END,g.END);fullb=bounds(idx,g.START,g.END)
    rows=[]; cache={}
    for sn,names in sigs.items():
        bL,bS=union(ed,names,idx)
        for vg in ['WEEK_PLUS_ANY','STRICT2','DW_REL_PRICE2']:
            vL,vS=vms[vg]
            for k in [0,3,4,5,6,7]:
                for usez in [False,True]:
                    L=(bL&pocL&vL&pd.Series(fsL>=k,index=idx));S=(bS&pocS&vS&pd.Series(fsS>=k,index=idx))
                    if usez: L&=zL;S&=zS
                    key=(sn,vg,k,usez);arr=(o,h,lo,c,atr,slo,shi,L.to_numpy(np.bool_),S.to_numpy(np.bool_));cache[key]=arr
                    for af,be,ml,tp in itertools.product([.55,.60,.65],[1.0,1.25],[2,3],[4.,6.,8.,10.,12.,16.,20.,24.]):
                        tr=pack(er.sim_equity(*arr,trb[0],trb[1],af,be,ml,tp,144));va=pack(er.sim_equity(*arr,vab[0],vab[1],af,be,ml,tp,144));sc=robust_score(tr,va)
                        if sc>-1e8: rows.append((sc,key,af,be,ml,tp,tr,va))
        print('DONE',sn,flush=True)
    rows.sort(reverse=True,key=lambda z:z[0]); picks=[];seen=set()
    def add(r):
        k=(r[1],r[2],r[3],r[4],r[5])
        if k not in seen:seen.add(k);picks.append(r)
    for r in rows[:12]:add(r)
    # Freeze Pareto-like WR/return frontiers using Train+Validation only.
    for trf,vaf in [(30,10),(100,25),(200,50),(300,75),(500,100)]:
        e=[r for r in rows if r[6]['ret']>=trf and r[7]['ret']>=vaf and r[6]['pf']>=1.10 and r[7]['pf']>=1.10]
        e.sort(key=lambda r:min(r[6]['wr'],r[7]['wr']),reverse=True)
        for r in e[:5]:add(r)
    out=[]
    for sc,key,af,be,ml,tp,tr,va in picks[:32]:
        arr=cache[key];ho=pack(er.sim_equity(*arr,hob[0],hob[1],af,be,ml,tp,144));full=pack(er.sim_equity(*arr,fullb[0],fullb[1],af,be,ml,tp,144))
        sn,vg,k,usez=key
        out.append({'signal':sn,'vwap_gate':vg,'flow_score_min':k,'zdir':usez,'af':af,'beR':be,'max_lots':ml,'tpR':tp,'train':tr,'val':va,'holdout':ho,'full':full,'score':sc})
    valid=[r for r in out if r['holdout']['ret']>0 and r['holdout']['pf']>=1.05]
    def minwr(r):return min(r['train']['wr'],r['val']['wr'],r['holdout']['wr'])
    wr=max(valid,key=minwr) if valid else None
    ge1000=[r for r in valid if r['full']['ret']>=1000]; wr1000=max(ge1000,key=minwr) if ge1000 else None
    ge2000=[r for r in valid if r['full']['ret']>=2000]; wr2000=max(ge2000,key=minwr) if ge2000 else None
    print('RESULT_JSON_START')
    print(json.dumps({'risk_rule':'0.36% of current mark-to-market equity per fresh lot; previous live lots protected before recycled risk','feature_truth':'All microstructure fields here are M1/tick-volume proxies, NOT CME trade/order-book CVD or true TPS/imbalance','features':['tick-volume change 1m/5m/15m','quote-activity proxy QPS and change','signed tick-volume proxy CVD 5m/15m','CLV pressure 1m/5m/15m','buy/sell pressure proxy','bull/bear minute imbalance','activity acceleration','Z48/Z84 direction'], 'selection':'Train+Validation only; Holdout frozen shortlist','best_robust_winrate':wr,'best_robust_winrate_full_ge_1000pct':wr1000,'best_robust_winrate_full_ge_2000pct':wr2000,'shortlist':out,'baseline':{'full_ret':4035.74,'full_wr':17.39,'holdout_wr':16.32}},default=float))
    print('RESULT_JSON_END')
if __name__=='__main__':main()
