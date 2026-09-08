import json, math
import pandas as pd
import gold_m5_discovery_spike as g
import gold_m5_multiedge as m

g.URLS=['/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2020_2022.csv','/tmp/xau/Gold-Cash/XAUUSD/XAUUSD_M1_2023_2026.csv']
m.g.URLS=g.URLS

def clean_union(a,b):
    L=a[0]|b[0];S=a[1]|b[1];cl=L&S
    return (L&~cl).fillna(False),(S&~cl).fillna(False)

def main():
    x=g.prep();ctx=g.contexts(x);gs=g.gates(x)
    base=g.sig(x,g.Spec('BRK','med','vwap','8R','both',12.0),ctx,gs)
    variants=[
      ('CUR_MTF_FLOW_LONG',g.Spec('EXP','mtf','flow','8R','long',1.5)),
      ('MTF_FLOW_BOTH',g.Spec('EXP','mtf','flow','8R','both',1.5)),
      ('MED_FLOW_BOTH',g.Spec('EXP','med','flow','8R','both',1.5)),
      ('MTF_VWAP_BOTH',g.Spec('EXP','mtf','vwap','8R','both',1.5)),
      ('MTF_FLOW_LONG_18',g.Spec('EXP','mtf','flow','8R','long',1.8)),
      ('MTF_FLOW_BOTH_18',g.Spec('EXP','mtf','flow','8R','both',1.8)),
    ]
    screen=[];cache={}
    exit_spec=g.Spec('BRK','med','vwap','8R','both',12.0)
    for nm,sp in variants:
        ex=g.sig(x,sp,ctx,gs);L,S=clean_union(base,ex);cache[nm]=(L,S)
        tr=g.met(*g.simulate(x,L,S,exit_spec,g.START,g.TRAIN_END));va=g.met(*g.simulate(x,L,S,exit_spec,g.TRAIN_END,g.VAL_END))
        if tr and va:
            score=tr['ret']-1.1*tr['dd']+.7*va['ret']-.8*va['dd'];screen.append((score,nm,tr,va))
    screen.sort(reverse=True,key=lambda z:z[0]);prom=[]
    for score,nm,tr,va in screen[:2]:
        L,S=cache[nm];ed={nm:(L,S)}
        c_tr=m.simulate(x,ed,(nm,),g.START,g.TRAIN_END,1.,4,10.,144)
        c_va=m.simulate(x,ed,(nm,),g.TRAIN_END,g.VAL_END,1.,4,10.,144)
        c_ho=m.simulate(x,ed,(nm,),g.VAL_END,g.END,1.,4,10.,144)
        c_full=m.simulate(x,ed,(nm,),g.START,g.END,1.,4,10.,144)
        prom.append({'variant':nm,'screen_score':score,'single_train':tr,'single_val':va,'campaign_train':c_tr,'campaign_val':c_va,'campaign_holdout':c_ho,'campaign_full':c_full})
    print('RESULT_JSON_START');print(json.dumps({'risk_pct':.36,'base':'BRK med+VWAP 12-bar','campaign':'BE1 max4 TP10 hold12h','selection':'six expansion definitions screened on train+validation; campaign+holdout only top two','screen':[{'variant':nm,'score':sc,'train':tr,'val':va} for sc,nm,tr,va in screen],'promoted':prom,'target_1000_R':math.log(11)/g.RISK,'limitations':['M1 OHLC->M5','0.08R cost/lot','no news/DXY']},default=float));print('RESULT_JSON_END')
if __name__=='__main__':main()
