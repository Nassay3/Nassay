import json
import numpy as np
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m
import gold_m5_volume_profile_ablation as vp
import gold_m5_vwap_ladder_ablation as vw

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS; vp.g.URLS=g.URLS; vw.g.URLS=g.URLS

def bounds(idx,a,b):
    ids=np.flatnonzero(np.asarray((idx>=a)&(idx<b))); return int(ids[0]),int(ids[-1])

def pack(v): return vp.pack(v)

def components(x,f):
    c=x.close.astype(float)
    rpS=(f['sv']>f['sp']); rpD=(f['dv']>f['dp']); rpW=(f['wv']>f['wp'])
    rnS=(f['sv']<f['sp']); rnD=(f['dv']<f['dp']); rnW=(f['wv']<f['wp'])
    ppS=(c>f['sv']); ppD=(c>f['dv']); ppW=(c>f['wv'])
    pnS=(c<f['sv']); pnD=(c<f['dv']); pnW=(c<f['wv'])
    prpS=(c>f['sp']); prpD=(c>f['dp']); prpW=(c>f['wp'])
    prnS=(c<f['sp']); prnD=(c<f['dp']); prnW=(c<f['wp'])
    strictL=[rpS&ppS&prpS,rpD&ppD&prpD,rpW&ppW&prpW]
    strictS=[rnS&pnS&prnS,rnD&pnD&prnD,rnW&pnW&prnW]
    return locals()

def mk_masks(x,f):
    q=components(x,f)
    Ls=q['strictL']; Ss=q['strictS']
    def ntrue(xs):
        z=xs[0].astype(np.int8)
        for a in xs[1:]: z=z+a.astype(np.int8)
        return z
    relL=ntrue([q['rpS'],q['rpD'],q['rpW']]); relS=ntrue([q['rnS'],q['rnD'],q['rnW']])
    pxL=ntrue([q['ppS'],q['ppD'],q['ppW']]); pxS=ntrue([q['pnS'],q['pnD'],q['pnW']])
    priorL=ntrue([q['prpS'],q['prpD'],q['prpW']]); priorS=ntrue([q['prnS'],q['prnD'],q['prnW']])
    strictL=ntrue(Ls); strictS=ntrue(Ss)
    # Six-component consensus = current-vs-prior direction + price-vs-current VWAP.
    sixL=relL+pxL; sixS=relS+pxS
    # Nine-component consensus additionally requires price to agree with prior VWAP close.
    nineL=sixL+priorL; nineS=sixS+priorS
    out={
      'NONE':(pd.Series(True,index=x.index),pd.Series(True,index=x.index)),
      'STRICT2':(strictL>=2,strictS>=2),
      'REL2':(relL>=2,relS>=2),
      'PRICE2':(pxL>=2,pxS>=2),
      'REL2_PRICE2':((relL>=2)&(pxL>=2),(relS>=2)&(pxS>=2)),
      'REL2_PRICE2_PRIOR2':((relL>=2)&(pxL>=2)&(priorL>=2),(relS>=2)&(pxS>=2)&(priorS>=2)),
      'SIX4':(sixL>=4,sixS>=4),
      'SIX5':(sixL>=5,sixS>=5),
      'NINE6':(nineL>=6,nineS>=6),
      'NINE7':(nineL>=7,nineS>=7),
      # Daily/weekly are structural; session is confirmation rather than a veto.
      'DW_CORE_SESS_ANY':((Ls[1]&Ls[2])&(q['rpS']|q['ppS']),(Ss[1]&Ss[2])&(q['rnS']|q['pnS'])),
      'WEEK_PLUS_ANY':(Ls[2]&(Ls[1]|Ls[0]),Ss[2]&(Ss[1]|Ss[0])),
      'DAY_PLUS_ANY':(Ls[1]&(Ls[2]|Ls[0]),Ss[1]&(Ss[2]|Ss[0])),
      # Require daily+weekly direction, but allow price to be on either 2/3 current VWAPs.
      'DW_REL_PRICE2':(q['rpD']&q['rpW']&(pxL>=2),q['rnD']&q['rnW']&(pxS>=2)),
      # Weekly direction mandatory + total two directional relations + price consensus.
      'W_REL2_PRICE2':(q['rpW']&(relL>=2)&(pxL>=2),q['rnW']&(relS>=2)&(pxS>=2)),
    }
    return {k:(a.fillna(False),b.fillna(False)) for k,(a,b) in out.items()}

def run():
    x=g.prep(); idx=x.index
    ed=m.build_edges(x); rawL=(ed['BRK'][0]|ed['EXP'][0]).fillna(False); rawS=(ed['BRK'][1]|ed['EXP'][1]).fillna(False)
    z=rawL&rawS; rawL&=~z; rawS&=~z
    o=x.open.to_numpy(float);h=x.high.to_numpy(float);lo=x.low.to_numpy(float);c=x.close.to_numpy(float);atr=x.atr14.to_numpy(float);vol=x.tick_volume.to_numpy(float)
    slo=x.low.rolling(7,min_periods=1).min().to_numpy(float);shi=x.high.rolling(7,min_periods=1).max().to_numpy(float)
    poc,_,_=vp.profile_levels(h,lo,c,vol,288,32,3,.70); ok=np.isfinite(poc)
    baseL=rawL&pd.Series(ok&(c>poc),index=idx); baseS=rawS&pd.Series(ok&(c<poc),index=idx)
    # Freeze the anchor/session choice selected by prior Train+Validation ablation: Riyadh +3, previous same-type session.
    f=vw.vwap_ladder(x,3,True); masks=mk_masks(x,f)
    trb=bounds(idx,g.START,g.TRAIN_END); vab=bounds(idx,g.TRAIN_END,g.VAL_END); hob=bounds(idx,g.VAL_END,g.END); fullb=bounds(idx,g.START,g.END)
    rows=[]; cache={}
    for name,(ml,ms) in masks.items():
        L=baseL&ml; S=baseS&ms; ones=pd.Series(True,index=idx)
        arr=(o,h,lo,c,atr,slo,shi,L.to_numpy(np.bool_),S.to_numpy(np.bool_),ones.to_numpy(np.bool_),ones.to_numpy(np.bool_));cache[name]=arr
        tr=pack(vp.sim_profile(*arr,trb[0],trb[1],.75,1.25,4,18.,144));va=pack(vp.sim_profile(*arr,vab[0],vab[1],.75,1.25,4,18.,144))
        score=tr['ret']-1.5*tr['dd']+.85*va['ret']-1.25*va['dd']-50*abs(tr['avgR']-va['avgR'])
        rows.append((score,name,tr,va));print('SCREEN',name,'TR',round(tr['ret'],2),round(tr['pf'],3),'VA',round(va['ret'],2),round(va['pf'],3),flush=True)
    rows.sort(reverse=True,key=lambda r:r[0]);picked=[]
    base=[r for r in rows if r[1]=='NONE'][0];picked.append(base)
    for r in rows:
        if r[1]!='NONE' and len(picked)<7:picked.append(r)
    promoted=[]
    for score,name,tr,va in picked:
        arr=cache[name];ho=pack(vp.sim_profile(*arr,hob[0],hob[1],.75,1.25,4,18.,144));full=pack(vp.sim_profile(*arr,fullb[0],fullb[1],.75,1.25,4,18.,144))
        promoted.append({'name':name,'score':score,'train':tr,'val':va,'holdout':ho,'full':full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'base':'BRK+EXP + 24h POC_GATE AF.75 BE1.25 max4 TP18 hold12h','vwap_anchor':'Riyadh UTC+3','session_prior':'previous same-type session close','selection':'Train+Validation only; holdout baseline+top6','screen':[{'name':n,'score':s,'train':tr,'val':va} for s,n,tr,va in rows],'promoted':promoted},default=float));print('RESULT_JSON_END')
if __name__=='__main__':run()
