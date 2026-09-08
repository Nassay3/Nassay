import pandas as pd
import gold_m1_microstructure_score as s

def add_micro_exact(x,f5,f15):
    b=x.copy()
    b['decision']=b.index+pd.Timedelta(minutes=5)
    b=b.reset_index().rename(columns={'bar_time':'m5_time','time':'m5_time'})
    f5=f5.rename(columns={'available':'avail5'}).sort_values('avail5')
    f15=f15.rename(columns={'available':'avail15'}).sort_values('avail15')
    # A 5m feature is visible only at its 5m close; a 15m feature only at its 15m close.
    b=pd.merge_asof(b.sort_values('decision'),f5,left_on='decision',right_on='avail5',direction='backward')
    b=pd.merge_asof(b.sort_values('decision'),f15,left_on='decision',right_on='avail15',direction='backward',suffixes=('','_15x'))
    if 'm5_time' in b.columns:
        b=b.set_index('m5_time')
    else:
        b.index=x.index
    return b.sort_index()

s.add_micro=add_micro_exact

if __name__=='__main__':
    s.main()
