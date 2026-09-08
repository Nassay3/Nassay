import gold_m5_discovery_spike as g

def quick_specs():
    out=[]
    for fam,pars in [("EXP",[1.5,1.8,2.1]),("PULL",[0]),("BRK",[12,24])]:
        gates=["none","vwap","flow"] if fam!="BRK" else ["none","vwap"]
        exits=["3R","5R","runner"] if fam!="PULL" else ["3R","runner"]
        for c in ["med","mtf"]:
            for gate in gates:
                for side in ["both","long"]:
                    for ex in exits:
                        for p in pars: out.append(g.Spec(fam,c,gate,ex,side,float(p)))
    return out

g.specs=quick_specs
g.main()
