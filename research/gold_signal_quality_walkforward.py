import json, math
import numpy as np
import pandas as pd

import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw
import gold_m5_vwap_consensus_ablation as vc
import gold_champion_execution_stress as s

HIST_URLS = [
    '/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv',
    '/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv',
]
GETDATA_LOCAL = '/tmp/XAUUSD.csv'
GETDATA_NORM = '/tmp/getdata_signal_quality.csv'
GETDATA_START = pd.Timestamp('2026-07-23', tz='UTC')
GETDATA_END = pd.Timestamp('2026-09-05', tz='UTC')

# Freeze execution/risk parameters before comparing signal quality.
AF = 0.80
BE_R = 2.25
MAX_LOTS = 3
TP_R = 28.0
MAX_HOLD = 216  # 18 hours on M5
BASE_COST = (0.08, 0.00)
STRESS_COST = (0.15, 0.05)
FRESH_ADD = 1
MIN_GAP = 1

EDGE_SETS = [
    ('BRK',), ('EXP',), ('PULL',),
    ('BRK','EXP'), ('BRK','PULL'), ('EXP','PULL'),
    ('BRK','EXP','PULL'),
]
VWAP_MODES = [
    'NONE', 'REL2', 'PRICE2', 'REL2_PRICE2',
    'WEEK_PLUS_ANY', 'DW_REL_PRICE2', 'W_REL2_PRICE2',
]
PROFILE_MODES = [
    'NONE', 'POC96', 'OUT96', 'POC288', 'OUT288', 'ACCEPT2_288'
]
FOLDS = [
    ('ERA1', pd.Timestamp('2021-09-08',tz='UTC'), pd.Timestamp('2023-01-01',tz='UTC')),
    ('ERA2', pd.Timestamp('2023-01-01',tz='UTC'), pd.Timestamp('2024-01-01',tz='UTC')),
    ('ERA3', pd.Timestamp('2024-01-01',tz='UTC'), pd.Timestamp('2025-01-01',tz='UTC')),
]


def bounds(idx, a, b):
    z = np.flatnonzero(np.asarray((idx >= a) & (idx < b)))
    if len(z) == 0:
        raise ValueError(f'empty bounds {a} {b}')
    return int(z[0]), int(z[-1])


def wire_urls(urls, end=None):
    g.URLS = list(urls)
    m.g.URLS = g.URLS
    vp.g.URLS = g.URLS
    vw.g.URLS = g.URLS
    vc.g.URLS = g.URLS
    s.g.URLS = g.URLS
    if end is not None:
        g.END = end


def make_profile_masks(x):
    h=x.high.to_numpy(float); lo=x.low.to_numpy(float); c=x.close.to_numpy(float); vol=x.tick_volume.to_numpy(float)
    out={'NONE':(pd.Series(True,index=x.index),pd.Series(True,index=x.index))}
    for lb in (96,288):
        poc,vah,val = vp.profile_levels(h,lo,c,vol,lb,32,3,.70)
        ok=np.isfinite(poc)&np.isfinite(vah)&np.isfinite(val)
        pocL=pd.Series(ok&(c>poc),index=x.index); pocS=pd.Series(ok&(c<poc),index=x.index)
        outL=pd.Series(ok&(c>vah),index=x.index); outS=pd.Series(ok&(c<val),index=x.index)
        out[f'POC{lb}']=(pocL,pocS)
        out[f'OUT{lb}']=(outL,outS)
        if lb==288:
            out['ACCEPT2_288']=(outL&outL.shift(1,fill_value=False),outS&outS.shift(1,fill_value=False))
    return out


def build_components(x):
    idx=x.index
    ed=m.build_edges(x)
    edge_masks={}
    for names in EDGE_SETS:
        L=pd.Series(False,index=idx); S=pd.Series(False,index=idx)
        for nm in names:
            L |= ed[nm][0]; S |= ed[nm][1]
        clash=L&S; L &= ~clash; S &= ~clash
        edge_masks['+'.join(names)] = (L.fillna(False),S.fillna(False))
    f=vw.vwap_ladder(x,3,True)
    all_vwap=vc.mk_masks(x,f)
    vwap_masks={k:all_vwap[k] for k in VWAP_MODES}
    profile_masks=make_profile_masks(x)
    o=x.open.to_numpy(float); h=x.high.to_numpy(float); lo=x.low.to_numpy(float); c=x.close.to_numpy(float); atr=x.atr14.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float); shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    return (o,h,lo,c,atr,slo,shi),edge_masks,vwap_masks,profile_masks


def arr_for(base, edge_masks, vwap_masks, profile_masks, cfg):
    e,v,p=cfg
    eL,eS=edge_masks[e]; vL,vS=vwap_masks[v]; pL,pS=profile_masks[p]
    L=(eL&vL&pL).fillna(False); S=(eS&vS&pS).fillna(False)
    clash=L&S; L &= ~clash; S &= ~clash
    return (*base,L.to_numpy(np.bool_),S.to_numpy(np.bool_))


def run_one(arr,b,cost,slip):
    return s.pack(s.sim_stress(*arr,b[0],b[1],AF,BE_R,MAX_LOTS,TP_R,MAX_HOLD,cost,slip,FRESH_ADD,MIN_GAP))


def rank_score(cells):
    # Fail closed: every pre-2025 era must survive both execution assumptions.
    for q in cells:
        if q['lots'] < 100 or q['ret'] <= 0 or q['pf'] <= 1.05:
            return None
    logs=[math.log1p(q['ret']/100.0) for q in cells]
    dds=[q['dd'] for q in cells]
    pfs=[q['pf'] for q in cells]
    return 2.5*min(logs)+sum(logs)/len(logs)+0.12*math.log(min(pfs))-.018*max(dds)-.005*sum(dds)/len(dds)


def prepare_getdata():
    z=pd.read_csv(GETDATA_LOCAL).rename(columns={'datetime':'time','volume':'tick_volume'})
    z['time']=pd.to_datetime(z.time,utc=True)
    z=z[['time','open','high','low','close','tick_volume']].dropna().sort_values('time')
    z.to_csv(GETDATA_NORM,index=False)


def main():
    original_end=g.END
    wire_urls(HIST_URLS, original_end)
    hx=g.prep(); hidx=hx.index
    hbase,hedge,hvwap,hprof=build_components(hx)
    folds=[(nm,bounds(hidx,a,b)) for nm,a,b in FOLDS]
    holdout=bounds(hidx,pd.Timestamp('2025-01-01',tz='UTC'),original_end)
    full=bounds(hidx,pd.Timestamp('2021-09-08',tz='UTC'),original_end)

    # Numba warm-up.
    warm_cfg=('BRK','NONE','NONE')
    wa=arr_for(hbase,hedge,hvwap,hprof,warm_cfg)
    b0=folds[0][1]
    run_one(wa,(b0[0],min(b0[0]+1000,b0[1])),*BASE_COST)

    rows=[]
    total=0
    for e in hedge:
        for v in VWAP_MODES:
            for p in PROFILE_MODES:
                total+=1; cfg=(e,v,p); arr=arr_for(hbase,hedge,hvwap,hprof,cfg)
                cells=[]; eras={}
                for nm,b in folds:
                    qb=run_one(arr,b,*BASE_COST); qs=run_one(arr,b,*STRESS_COST)
                    eras[nm]={'base':qb,'stress':qs}; cells += [qb,qs]
                sc=rank_score(cells)
                if sc is not None:
                    rows.append((sc,cfg,eras))
    rows.sort(reverse=True,key=lambda z:z[0])
    print('HIST_SCREEN_TOTAL',total,'QUALIFIED',len(rows),flush=True)

    promoted=[]
    for rank,(sc,cfg,eras) in enumerate(rows[:20],start=1):
        arr=arr_for(hbase,hedge,hvwap,hprof,cfg)
        hob=run_one(arr,holdout,*BASE_COST); hos=run_one(arr,holdout,*STRESS_COST)
        fb=run_one(arr,full,*BASE_COST); fs=run_one(arr,full,*STRESS_COST)
        promoted.append({'hist_rank':rank,'score':sc,'edge_set':cfg[0],'vwap_mode':cfg[1],'profile_mode':cfg[2],'eras':eras,'holdout_2025plus_base':hob,'holdout_2025plus_stress':hos,'full_base':fb,'full_stress':fs})

    # External feed is evaluated only after historical ranking is frozen.
    prepare_getdata()
    wire_urls([GETDATA_NORM],GETDATA_END)
    gx=g.prep(); gidx=gx.index
    gbase,gedge,gvwap,gprof=build_components(gx)
    gb=bounds(gidx,GETDATA_START,GETDATA_END)
    for q in promoted:
        cfg=(q['edge_set'],q['vwap_mode'],q['profile_mode'])
        arr=arr_for(gbase,gedge,gvwap,gprof,cfg)
        eb=run_one(arr,gb,*BASE_COST); es=run_one(arr,gb,*STRESS_COST)
        q['getdata_base']=eb; q['getdata_stress']=es
        q['external_stress_pass']=bool(es['lots']>=25 and es['ret']>0 and es['pf']>1.05)

    survivors=[q for q in promoted if q['external_stress_pass']]
    print('RESULT_JSON_START')
    print(json.dumps({
        'purpose':'Find signal-quality filters that survive multiple historical eras and harsher execution, then validate without tuning on GetData.',
        'risk_rule':'0.36% current MTM equity per fresh lot; one unprotected fresh-risk lot maximum; every add requires a fresh same-direction filtered signal.',
        'fixed_execution_params':{'atr_floor':AF,'beR':BE_R,'max_lots':MAX_LOTS,'targetR':TP_R,'hold_hours':MAX_HOLD*5/60},
        'base_cost':{'costR':BASE_COST[0],'stop_slipR':BASE_COST[1]},
        'stress_cost':{'costR':STRESS_COST[0],'stop_slipR':STRESS_COST[1]},
        'search_space':{'edge_sets':['+'.join(x) for x in EDGE_SETS],'vwap_modes':VWAP_MODES,'profile_modes':PROFILE_MODES,'total_configs':total},
        'historical_selection':'Rank only ERA1/ERA2/ERA3 pre-2025. Every era must have >=100 lots, positive return and PF>1.05 under BOTH base and stress. 2025+ and GetData hidden until top20 frozen.',
        'qualified_pre2025':len(rows),
        'promoted_top20':promoted,
        'external_stress_survivors':survivors,
        'external_pass_rule':'GetData stress: >=25 lots, return >0, PF>1.05. Passing makes GetData validation evidence, not a pristine holdout; Dukascopy bid/ask tick replay remains required.',
        'limitations':['Historical source and GetData are OHLC/tick-volume proxy, not COMEX true volume-at-price.','Stop-first ordering is conservative when stop and target coexist in one M5 candle.','Repeated research on the same historical source creates meta-overfit risk.']
    },default=float))
    print('RESULT_JSON_END')

if __name__=='__main__':
    main()
