import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS; vp.g.URLS=g.URLS


def pack(v): return vp.pack(v)
def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b))); return int(ids[0]),int(ids[-1])


def vwap_ladder(x, offset_hours=0, same_session=False):
    """Causal VWAPs. offset_hours shifts UTC into the anchor clock (0=UTC, 3=Riyadh).
    Sessions on anchor clock: Asia 00:00-08:00, London 08:00-14:30, NY 14:30-24:00.
    prior session is either immediately previous completed session (chain) or prior same-type session.
    """
    idx=x.index
    loc=idx+pd.Timedelta(hours=offset_hours)
    typ=(x.high+x.low+x.close)/3.0
    vol=x.tick_volume.clip(lower=1).astype(float)
    pv=typ*vol
    daykey=pd.Series(loc.strftime('%Y-%m-%d'),index=idx)
    iso=loc.isocalendar()
    weekkey=pd.Series(iso.year.astype(str)+'-'+iso.week.astype(str),index=idx)
    mins=loc.hour*60+loc.minute
    sn=np.where(mins<480,'A',np.where(mins<870,'L','N'))
    sesskey=pd.Series(loc.strftime('%Y-%m-%d')+'_'+sn,index=idx)
    slabel=pd.Series(sn,index=idx)

    def current_and_prior(group):
        cur=pv.groupby(group).cumsum()/vol.groupby(group).cumsum()
        finals=cur.groupby(group).last()
        keys=list(pd.unique(group))
        mp={keys[i]:float(finals.loc[keys[i-1]]) for i in range(1,len(keys))}
        return cur,group.map(mp).astype(float)

    sv, sprior_chain=current_and_prior(sesskey)
    dv, dprior=current_and_prior(daykey)
    wv, wprior=current_and_prior(weekkey)

    if not same_session:
        sprior=sprior_chain
    else:
        finals=sv.groupby(sesskey).last()
        meta=pd.DataFrame({'key':list(pd.unique(sesskey))})
        meta['lab']=meta['key'].str.rsplit('_',n=1).str[-1]
        mp={}
        for lab,sub in meta.groupby('lab',sort=False):
            ks=sub['key'].tolist()
            for i in range(1,len(ks)): mp[ks[i]]=float(finals.loc[ks[i-1]])
        sprior=sesskey.map(mp).astype(float)

    return {'sv':sv.astype(float),'sp':sprior.astype(float),
            'dv':dv.astype(float),'dp':dprior.astype(float),
            'wv':wv.astype(float),'wp':wprior.astype(float)}


def layer_masks(x,f):
    c=x.close.astype(float)
    # A layer is bullish only if price is above BOTH current VWAP and prior VWAP close,
    # AND current VWAP is above that prior close; bearish is the exact inverse.
    sL=(c>f['sv'])&(c>f['sp'])&(f['sv']>f['sp'])
    sS=(c<f['sv'])&(c<f['sp'])&(f['sv']<f['sp'])
    dL=(c>f['dv'])&(c>f['dp'])&(f['dv']>f['dp'])
    dS=(c<f['dv'])&(c<f['dp'])&(f['dv']<f['dp'])
    wL=(c>f['wv'])&(c>f['wp'])&(f['wv']>f['wp'])
    wS=(c<f['wv'])&(c<f['wp'])&(f['wv']<f['wp'])
    relL=(f['sv']>f['sp'])&(f['dv']>f['dp'])&(f['wv']>f['wp'])
    relS=(f['sv']<f['sp'])&(f['dv']<f['dp'])&(f['wv']<f['wp'])
    priceL=(c>f['sv'])&(c>f['dv'])&(c>f['wv'])
    priceS=(c<f['sv'])&(c<f['dv'])&(c<f['wv'])
    scoreL=sL.astype(int)+dL.astype(int)+wL.astype(int)
    scoreS=sS.astype(int)+dS.astype(int)+wS.astype(int)
    return {k:(v.fillna(False) if hasattr(v,'fillna') else v) for k,v in {
      'sessL':sL,'sessS':sS,'dayL':dL,'dayS':dS,'weekL':wL,'weekS':wS,
      'allL':sL&dL&wL,'allS':sS&dS&wS,
      'relL':relL,'relS':relS,'priceL':priceL,'priceS':priceS,
      'score2L':scoreL>=2,'score2S':scoreS>=2}.items()}


def run():
    x=g.prep(); idx=x.index
    ed=m.build_edges(x)
    rawL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False); rawS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False)
    z=rawL&rawS; rawL&=~z; rawS&=~z
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float)
    atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)

    print('PROFILE_BUILD_24H',flush=True)
    poc,vah,val=vp.profile_levels(h,lo,c,vol,288,32,3,.70)
    pok=np.isfinite(poc)
    pocL=pd.Series(pok&(c>poc),index=idx); pocS=pd.Series(pok&(c<poc),index=idx)
    baseL=rawL&pocL; baseS=rawS&pocS

    trb=bounds(idx,g.START,g.TRAIN_END); vab=bounds(idx,g.TRAIN_END,g.VAL_END); hob=bounds(idx,g.VAL_END,g.END); fullb=bounds(idx,g.START,g.END)
    fields={}
    for off in (0,3):
        for same in (False,True):
            fields[(off,same)]=layer_masks(x,vwap_ladder(x,off,same))

    specs=[('POC_ONLY',0,False,'none','none')]
    # Hard-entry ablations, each isolated.
    for off in (0,3):
      for same in (False,True):
        tag=f"{'UTC' if off==0 else 'RUH'}_{'SAME' if same else 'CHAIN'}"
        for mode in ('sess','day','week','dayweek','all','score2','rel','price'):
            specs.append((tag+'_'+mode.upper(),off,same,mode,'none'))
        # Preserve campaigns and use VWAP only to qualify sequential additions.
        for mode in ('all','score2','dayweek'):
            specs.append((tag+'_ADD_'+mode.upper(),off,same,'none',mode))
        # Moderate hybrid: score-2 to start, strict all-3 for adds.
        specs.append((tag+'_INIT2_ADDALL',off,same,'score2','all'))

    def mask(mode,Lside,f):
        if mode=='none': return pd.Series(True,index=idx)
        if mode=='sess': return f['sessL' if Lside else 'sessS']
        if mode=='day': return f['dayL' if Lside else 'dayS']
        if mode=='week': return f['weekL' if Lside else 'weekS']
        if mode=='dayweek': return (f['dayL']&f['weekL']) if Lside else (f['dayS']&f['weekS'])
        if mode=='all': return f['allL' if Lside else 'allS']
        if mode=='score2': return f['score2L' if Lside else 'score2S']
        if mode=='rel': return f['relL' if Lside else 'relS']
        if mode=='price': return f['priceL' if Lside else 'priceS']
        raise ValueError(mode)

    rows=[]; cache={}
    for name,off,same,imode,amode in specs:
        f=fields[(off,same)] if name!='POC_ONLY' else fields[(0,False)]
        initL=baseL & mask(imode,True,f); initS=baseS & mask(imode,False,f)
        addL=mask(amode,True,f); addS=mask(amode,False,f)
        arr=(o,h,lo,c,atr,slo,shi,initL.to_numpy(np.bool_),initS.to_numpy(np.bool_),addL.to_numpy(np.bool_),addS.to_numpy(np.bool_))
        cache[name]=arr
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],.75,1.25,4,18.,144)); va=pack(vp.sim_profile(*arr,vab[0],vab[1],.75,1.25,4,18.,144))
        score=tr['ret']-1.5*tr['dd']+.85*va['ret']-1.25*va['dd']-50*abs(tr['avgR']-va['avgR'])
        rows.append((score,name,off,same,imode,amode,tr,va))
        print('SCREEN',name,'TR',round(tr['ret'],2),round(tr['pf'],3),'VA',round(va['ret'],2),round(va['pf'],3),flush=True)

    rows.sort(reverse=True,key=lambda r:r[0])
    # Holdout is exposed only for benchmark + top 6 selected on Train+Validation.
    promoted=[]; picked=[]
    baseline=[r for r in rows if r[1]=='POC_ONLY'][0]; picked.append(baseline)
    for r in rows:
        if r[1]!='POC_ONLY' and len(picked)<7: picked.append(r)
    for score,name,off,same,imode,amode,tr,va in picked:
        arr=cache[name]
        ho=pack(vp.sim_profile(*arr,hob[0],hob[1],.75,1.25,4,18.,144)); full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],.75,1.25,4,18.,144))
        promoted.append({'name':name,'offset_hours':off,'session_prior':'same_type' if same else 'immediate_chain','init_mode':imode,'add_mode':amode,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})

    print('RESULT_JSON_START')
    print(json.dumps({
      'risk_pct':.36,
      'frozen_strategy':'Sequential BRK+EXP + 24h POC_GATE | AF0.75 BE1.25 max4 TP18 hold12h',
      'vwap_formula':'HLC3*completed-bar tick_volume cumulative / cumulative tick_volume',
      'strict_layer_long':'price > current VWAP > prior completed VWAP close AND price > prior close; short exact inverse',
      'sessions':'Asia 00:00-08:00, London 08:00-14:30, NY 14:30-24:00 on tested anchor clock',
      'anchors_tested':['UTC','Riyadh UTC+3'],
      'session_prior_tested':['immediately previous session close','previous same-type session close'],
      'selection':'ranked on Train+Validation only; Holdout exposed for POC benchmark + top6 VWAP configurations',
      'screen':[{'name':r[1],'score':r[0],'train':r[6],'val':r[7]} for r in rows],
      'promoted':promoted,
      'warning':'tick_volume is XAUUSD quote activity, not COMEX GC traded volume; POC remains a proxy.'},default=float))
    print('RESULT_JSON_END')

if __name__=='__main__': run()
