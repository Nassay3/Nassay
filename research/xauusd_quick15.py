#!/usr/bin/env python3
from dataclasses import asdict
from pathlib import Path
import argparse, json
import pandas as pd
import xauusd_real_grid as c


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',type=Path,required=True); ap.add_argument('--out',type=Path,default=Path('xau_quick')); a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    raw=c.read_data(a.data); vc=c.vwap_context(raw)
    f15=c.add_feat(c.resample(raw,15)); f60=c.add_feat(c.resample(raw,60)); f240=c.add_feat(c.resample(raw,240)); base={15:f15,60:f60,240:f240}
    x=c.attach_context(f15,15,vc,base); x.attrs['tf']=15
    cfgs=[c.SigCfg(15,se,tr,vw,z,zs) for se in ('SHALLOW','DEEP','BREAKOUT') for tr in ('CORE','FULL') for vw in ('NONE','DW','DWS','LADDER') for z in (.5,.875) for zs in ('NONE','BOTH')]
    rows=[]; cache={}; ex0=c.ExitCfg(2.0,'3R')
    for cfg in cfgs:
        s=c.signal(x,cfg); cache[cfg]=s; t=c.simulate(x,s,ex0); tr,va,oo=c.three(t)
        rows.append({**asdict(cfg),'score':c.score(tr,va),**{f'train_{k}':v for k,v in tr.items()},**{f'valid_{k}':v for k,v in va.items()},**{f'oos_{k}':v for k,v in oo.items()}})
    g=pd.DataFrame(rows).sort_values(['score','valid_exp_r','valid_pf'],ascending=False); g.to_csv(a.out/'signal_grid.csv',index=False)
    good=g[g.score>-1e8].head(6); diagnostic=False
    if good.empty: good=g.head(6); diagnostic=True
    rr=[]; trades={}
    for _,r in good.iterrows():
        cfg=c.SigCfg(15,str(r.setup),str(r.trend),str(r.vwap),float(r.zthr),str(r.zslow)); s=cache[cfg]
        for am in (1.5,2.0,2.5,3.0):
            for man in ('2R','3R','4R','FIB','EXT'):
                ex=c.ExitCfg(am,man); t=c.simulate(x,s,ex); tr,va,oo=c.three(t); key=f'{cfg.setup}-{cfg.trend}-{cfg.vwap}-z{cfg.zthr}-{cfg.zslow}-a{am}-{man}'; trades[key]=t
                rr.append({'key':key,**asdict(cfg),**asdict(ex),'score':c.score(tr,va),**{f'train_{k}':v for k,v in tr.items()},**{f'valid_{k}':v for k,v in va.items()},**{f'oos_{k}':v for k,v in oo.items()}})
    g2=pd.DataFrame(rr).sort_values(['score','valid_exp_r','valid_pf'],ascending=False); g2.to_csv(a.out/'exit_grid.csv',index=False)
    dep=g2[g2.score>-1e8]; sel=dep.iloc[0] if len(dep) else g2.iloc[0]; t=trades[str(sel.key)]; t.to_csv(a.out/'selected_trades.csv',index=False)
    yearly=[]
    if not t.empty:
        y=pd.to_datetime(t.entry_time,utc=True).dt.year
        for yy in sorted(y.unique()): yearly.append({'year':int(yy),**c.metrics(t[y==yy])})
    pd.DataFrame(yearly).to_csv(a.out/'yearly.csv',index=False)
    ab=[]
    for vw in ('NONE','DW','DWS','LADDER'):
        cfg=c.SigCfg(15,str(sel.setup),str(sel.trend),vw,float(sel.zthr),str(sel.zslow)); tt=c.simulate(x,c.signal(x,cfg),c.ExitCfg(float(sel.atr_mult),str(sel.management))); tr,va,oo=c.three(tt)
        ab.append({'vwap':vw,**{f'train_{k}':v for k,v in tr.items()},**{f'valid_{k}':v for k,v in va.items()},**{f'oos_{k}':v for k,v in oo.items()}})
    pd.DataFrame(ab).to_csv(a.out/'vwap_ablation.csv',index=False)
    summary={'status':'DIAGNOSTIC_ONLY' if diagnostic or len(dep)==0 else 'VALIDATED_TRAIN_VALIDATION','data_start':str(raw.time.min()),'data_end':str(raw.time.max()),'rows':len(raw),'risk':c.RISK,'grid':len(cfgs),'selected':sel.to_dict(),'all_metrics':c.metrics(t)}
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2,default=str)); print(json.dumps(summary,indent=2,default=str),flush=True)
if __name__=='__main__': main()
