import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_10000_equity_risk as er

LOCAL='/tmp/XAUUSD.csv'
EXT_START=pd.Timestamp('2026-07-23',tz='UTC')
EXT_END=pd.Timestamp('2026-09-05',tz='UTC')


def prepare_feed():
    z=pd.read_csv(LOCAL).rename(columns={'datetime':'time','volume':'tick_volume'})
    z['time']=pd.to_datetime(z['time'],utc=True)
    z=z[['time','open','high','low','close','tick_volume']].dropna().sort_values('time')
    path='/tmp/getdata_norm.csv'; z.to_csv(path,index=False)
    print('GETDATA_RANGE',z.time.min(),z.time.max(),'ROWS',len(z),flush=True)
    return path


def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b)))
    if len(ids)<20: raise RuntimeError('insufficient external bars')
    return int(ids[0]),int(ids[-1])


def main():
    path=prepare_feed()
    # Overwrite every imported module's data URL before feature construction.
    g.URLS=[path]; m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS; vc.g.URLS=g.URLS; er.g.URLS=g.URLS
    g.END=EXT_END
    x=g.prep(); idx=x.index
    ed=m.build_edges(x); names=('BRK','EXP','PULL','FRACTAL')
    L=pd.Series(False,index=idx); S=pd.Series(False,index=idx)
    for nm in names:
        L |= ed[nm][0]; S |= ed[nm][1]
    clash=L&S; L &= ~clash; S &= ~clash

    o=x.open.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); c=x.close.to_numpy(float)
    atr=x.atr14.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float)
    shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)

    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70)
    ok=np.isfinite(poc)
    fields=vw.vwap_ladder(x,3,True)
    wL,wS=vc.mk_masks(x,fields)['WEEK_PLUS_ANY']
    L=(L&wL&pd.Series(ok&(c>poc),index=idx)).to_numpy(np.bool_)
    S=(S&wS&pd.Series(ok&(c<poc),index=idx)).to_numpy(np.bool_)
    arr=(o,h,lo,c,atr,slo,shi,L,S)
    bd=bounds(idx,EXT_START,EXT_END)

    # Frozen before inspecting this run. These are the two historical pre-specified candidates.
    candidates={
        'METHOD_BEST_SCORE_AF060_TP26':(.60,1.25,3,26.,144),
        'HIST_BEST_FULL_AF0575_TP28':(.575,1.25,3,28.,144),
    }
    out={}
    for name,(af,be,ml,tp,hold) in candidates.items():
        r=er.pack(er.sim_equity(*arr,bd[0],bd[1],af,be,ml,tp,hold))
        r['params']={'atr_floor':af,'beR':be,'max_lots':ml,'targetR':tp,'hold_hours':hold*5/60}
        out[name]=r
        print('EXTERNAL',name,r,flush=True)

    mask=(idx>=EXT_START)&(idx<EXT_END)
    diag={
        'union_raw_long':int(sum(ed[n][0][mask].sum() for n in names)),
        'union_raw_short':int(sum(ed[n][1][mask].sum() for n in names)),
        'after_poc_vwap_long':int(L[mask].sum()),
        'after_poc_vwap_short':int(S[mask].sum()),
    }
    print('RESULT_JSON_START')
    print(json.dumps({
        'risk_rule':'Each fresh lot = exactly 0.36% of current mark-to-market equity; every older live lot must be protected at BE before another fresh risk lot.',
        'feed':'GetData XAUUSD M1 free independent broker/mid-quote sample',
        'window':[str(EXT_START),str(EXT_END)],
        'strategy':'Frozen UNION4 BRK+EXP+PULL+FRACTAL + causal 24h activity POC + Riyadh WEEK_PLUS_ANY VWAP + exact-equity protected recycling',
        'selection_note':'No parameter tuning on GetData in this run. A is historical Train+Validation score winner; B is historical full-return winner among previously promoted top30.',
        'results':out,'diagnostics':diag,
        'limitations':['GetData window is only about six weeks','M1 OHLC resampled to M5, not true bid/ask tick sequence','tick volume/profile are activity proxies, not COMEX traded volume','fixed 0.08R modeled cost; no variable spread/slippage/swap','because this GetData sample has already been used in prior research, it is now validation evidence, not a pristine final holdout']
    },default=float))
    print('RESULT_JSON_END')

if __name__=='__main__': main()
