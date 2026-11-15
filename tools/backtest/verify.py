"""Independent checks of what run.js recorded, straight from the price table:
1. every row's price and every forward move (7 to 90 days, with the 5-day look-back);
2. which came first, the sell level or the cut level, on a sample;
3. the as-of price series, rebuilt here for sample days and items and run through the live code again (a small script it writes and runs)."""
import os as _os
ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
BT = _os.environ.get("BT_DIR") or _os.path.join(ROOT, "bt-work")            # working folder (not in git): days/, prices.i32, sig/
DATA = _os.environ.get("DATA_DIR") or _os.path.join(ROOT, "data")           # the data branch's data/ folder
import glob, json, os, subprocess, numpy as np
sig=BT+'/sig'
infos=[json.load(open(p)) for p in sorted(glob.glob(sig+'/info.*.json'))]; info=infos[0]
DT={"Int32Array":np.int32,"Int16Array":np.int16,"Uint8Array":np.uint8,"Float32Array":np.float32}
col={n:np.concatenate([np.fromfile(f"{sig}/{n}.{i['shard']}.bin",dtype=DT[t]) for i in infos]) for n,t in info['types'].items()}
days=json.load(open(BT+'/days.json')); keys=json.load(open(BT+'/keys.json'))
nK,nD=len(keys),len(days)
M=np.memmap(BT+'/prices.i32',dtype=np.int32,mode='r',shape=(nK,nD))
k=col['key'].astype(np.int64); d=col['day'].astype(np.int64); v=col['v'].astype(np.int64)
print('rows',len(k),'; price on the decision day equals the table:',bool((M[k,d]==v).all()),'; all $1+:',bool((v>=100).all()))
bad_total=0
for h in info['horizons']:
    j=d+h; inside=j<nD; want=np.full(len(k),np.nan)
    px=np.zeros(len(k),dtype=np.int64)
    for back in range(0,6):
        jj=np.clip(j-back,0,nD-1); cand=np.where(inside,M[k,jj],0); px=np.where((px==0)&(cand>0),cand,px)
    want[inside]=np.where(px[inside]>0,px[inside]/v[inside]-1,-2)
    got=col[f'r{h}'].astype(np.float64)
    same=(np.isnan(want)&np.isnan(got))|(np.abs(want-got)<=1e-5*np.maximum(1,np.abs(want)))
    bad=int((~same).sum()); bad_total+=bad
    print(f'forward move {h:>2} days: {int(inside.sum())} inside the data, differences {bad}')
# 2. sell level or cut level first, on a sample (levels rebuilt from the recorded percentages, so cases within a cent of a level are left out)
rng=np.random.default_rng(7); has=np.where((col['touch']<=3)&~np.isnan(col['sell1']))[0]; pick=rng.choice(has,40000,replace=False)
chk=skip=diff=0
for i in pick:
    vv=int(v[i]); sell=vv*(1+float(col['sell1'][i])/100); cut=vv*(1-float(col['cut'][i])/100); kk,dd=int(k[i]),int(d[i])
    path=np.asarray(M[kk,dd+1:min(dd+61,nD)]); path=path[path>0]
    if len(path) and (np.abs(path-sell).min()<1.5 or np.abs(path-cut).min()<1.5): skip+=1; continue
    t=0 if dd+60<nD else 3
    for x in path:
        if x<=cut: t=2; break
        if x>=sell: t=1; break
    chk+=1; diff+= int(t!=int(col['touch'][i]))
print(f'sell-or-cut first: {chk} checked, {skip} left out (within a cent of a level), differences {diff}')
# 3. the as-of series rebuilt here
from datetime import date
sunday=[date.fromisoformat(x).weekday()==6 for x in days]
cases=[]
for dd in (365+7*3, 600, 801, nD-1-7*9):
    dd=int(d[np.argmin(np.abs(d-dd))])                      # the nearest decision day
    rows=np.where(d==dd)[0]; rows=rng.choice(rows,2500,replace=False)
    start=max(0,dd-119); wk=[j for j in range(max(0,dd-366),dd-120) if sunday[j]]
    for i in rows:
        kk=int(k[i]); row=M[kk]
        cases.append({'i':int(i),'sDates':[days[j] for j in wk]+[days[dd]],'sVals':[int(row[j]) or None for j in wk]+[int(row[dd])],
                      'dDates':days[start:dd+1],'dVals':[int(x) or None for x in row[start:dd+1]],'setup':info['setups'][int(col['setup'][i])],'risk':int(col['risk'][i])})
json.dump(cases,open(BT+'/verify_cases.json','w'))
js = """const TA=require(ROOT+"/site/assets/edge-ta.js"),ST=require(ROOT+"/site/assets/edge-strat.js");
const cases=require(BT+"/verify_cases.json");let diff=0;const by={};
for(const c of cases){const a=TA.analyse(c.sDates,c.sVals,{dates:c.dDates,values:c.dVals});const f=ST.facts(a),pk=ST.pick(f);by[pk.id]=(by[pk.id]||0)+1;if(pk.id!==c.setup)diff++;}
console.log("as-of series rebuilt separately: "+cases.length+" cases on 4 days, setup differences "+diff+"; setups seen "+Object.keys(by).length);"""
open(BT+'/verify_setups.js','w').write(f"const ROOT={json.dumps(ROOT)},BT={json.dumps(BT)};\n"+js)
print(subprocess.run(['node',BT+'/verify_setups.js'],capture_output=True,text=True).stdout.strip())
print('TOTAL forward-move differences',bad_total)
