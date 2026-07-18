#!/usr/bin/env python3
"""Task6_2: Full 8-model comparison + feature engineering + threshold analysis"""
import json, warnings, pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, AdaBoostClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from xgboost import XGBClassifier
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, confusion_matrix, roc_curve)

warnings.filterwarnings('ignore')
np.random.seed(42)

CSV = '/Users/skyler/workspace/stock_selection/ai_quant/data/stock_analysis/002281_202307_202607.csv'
BASE = Path('/Users/skyler/workspace/stock_selection/ai_quant')
OUT = BASE / 'data/results/task5'
OUT.mkdir(parents=True, exist_ok=True)
MDL = BASE / 'models'
MDL.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════
# 1. DATA
# ══════════════════════════════════════════
df = pd.read_csv(CSV)
df['trade_date'] = pd.to_datetime(df['trade_date'])
df = df.sort_values('trade_date').reset_index(drop=True)
df['Label'] = (df['pct_chg'].shift(-1) > 0).astype(int)
df.dropna(subset=['Label'], inplace=True)

# ══════════════════════════════════════════
# 2. FEATURE ENGINEERING
# ══════════════════════════════════════════
for w in [5,10,20]:
    m=df['close'].rolling(w).mean()
    df[f'ma_d{w}']=(df['close']-m)/(m+1e-10)*100
    df[f'ma_s{w}']=m.pct_change(5)*100
for a,b in [(5,10),(5,20),(10,20)]:
    ma,mb=df['close'].rolling(a).mean(),df['close'].rolling(b).mean()
    df[f'ma{a}{b}']=(ma-mb)/(mb+1e-10)*100
for w in [5,10,20]:
    df[f'vol{w}']=df['close'].rolling(w).std()/(df['close']+1e-10)*100
vm20=df['vol'].rolling(20).mean()
df['vr']=df['vol']/(vm20+1e-10)
df['vr5_20']=df['vol'].rolling(5).mean()/(df['vol'].rolling(20).mean()+1e-10)
df['vr8_89']=df['vol'].rolling(8).mean()/(df['vol'].rolling(89).mean()+1e-10)
df['ver']=df['vol']/(df['vol'].ewm(span=20,adjust=False).mean()+1e-10)

def rsi(s,p):
    d=s.diff();g=d.where(d>0,0).rolling(p).mean();l=(-d.where(d<0,0)).rolling(p).mean()
    return 100-(100/(1+g/(l+1e-10)))
for p in [6,12,24,56]:
    df[f'rsi{p}']=rsi(df['close'],p)

e12=df['close'].ewm(span=12,adjust=False).mean()
e26=df['close'].ewm(span=26,adjust=False).mean()
df['macd']=e12-e26;df['macds']=df['macd'].ewm(span=9,adjust=False).mean();df['macdh']=df['macd']-df['macds']

df['e5']=df['close'].ewm(span=5,adjust=False).mean()
df['e29']=df['close'].ewm(span=29,adjust=False).mean()
df['ed5']=(df['close']-df['e5'])/(df['e5']+1e-10)*100
df['ed29']=(df['close']-df['e29'])/(df['e29']+1e-10)*100

for p in [10,14]:
    h,l=df['high'].rolling(p).max(),df['low'].rolling(p).min()
    df[f'wr{p}']=(df['close']-h)/(h-l+1e-10)*(-100)

lo9,hi9=df['low'].rolling(9).min(),df['high'].rolling(9).max()
df['rsv']=(df['close']-lo9)/(hi9-lo9+1e-10)*100
df['K']=df['rsv'].ewm(com=2,adjust=False).mean()
df['D']=df['K'].ewm(com=2,adjust=False).mean()
df['J']=3*df['K']-2*df['D']

pc=df['close'].shift(1)
df['cr']=(df['high']-pc).clip(lower=0).rolling(26).sum()/((pc-df['low']).clip(lower=0).rolling(26).sum()+1e-10)*100

for w in [5,10,20]:
    df[f'mom{w}']=df['close']/df['close'].shift(w)-1

for w in [20,60]:
    h,l=df['high'].rolling(w).max(),df['low'].rolling(w).min()
    df[f'pp{w}']=(df['close']-l)/(h-l+1e-10)

tr=pd.concat([df['high']-df['low'],(df['high']-pc).abs(),(df['low']-pc).abs()],axis=1).max(axis=1)
df['atr']=tr.rolling(14).mean()/(df['close']+1e-10)*100

bm20,bv20=df['close'].rolling(20).mean(),df['close'].rolling(20).std()
df['bbp']=(df['close']-(bm20-2*bv20))/((bm20+2*bv20)-(bm20-2*bv20)+1e-10)

df['gap']=(df['open']-pc)/(pc+1e-10)*100
df['intd']=(df['close']-df['open'])/(df['open']+1e-10)*100
bd=(df['close']-df['open']).abs()
us=df['high']-df[['open','close']].max(axis=1)
ls2=df[['open','close']].min(axis=1)-df['low']
df['sr']=(us-ls2)/(bd+1e-10)
df['crp']=(df['close']-df['low'])/(df['high']-df['low']+1e-10)

for w in [5,10,20]:
    df[f'rm{w}']=df['pct_chg'].rolling(w).mean()
    df[f'ru{w}']=(df['pct_chg']>0).rolling(w).mean()

df['tm5']=df['turnover_rate'].rolling(5).mean()
df['td']=df['turnover_rate']/(df['tm5']+1e-10)
df['dow']=df['trade_date'].dt.dayofweek

for l in range(1,6):
    df[f'rl{l}']=df['pct_chg'].shift(l)

excl=['trade_date','股票代码','Label']
feats=[c for c in df.columns if c not in excl]
nc=df[feats].isna().sum()
drop=nc[nc>len(df)*0.3].index.tolist()
feats=[c for c in feats if c not in drop]
n0=len(df)
df=df.dropna(subset=feats+['Label']).reset_index(drop=True)
print(f"Features: {len(feats)}, Samples: {len(df)} (from {n0})")
print(f"Dropped features (>30% NaN): {drop}")

# ═══ SPLITS ═══
X=df[feats].values.astype(np.float64); y=df['Label'].values
Xtr,Xte,ytr,yte,idxtr,idxte=train_test_split(X,y,np.arange(len(X)),test_size=0.2,random_state=42,stratify=y)
sc=StandardScaler()
Xtrs,Xtes=sc.fit_transform(Xtr),sc.transform(Xte)

# ═══ 8 MODELS ═══
from sklearn.model_selection import GridSearchCV

models = {}

# 1. LogisticRegression
mdl = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
mdl.fit(Xtrs, ytr)
qp = mdl.predict_proba(Xtes)[:,1]
models['LogisticRegression'] = dict(model=mdl, preds=mdl.predict(Xtes), probs=qp,
    auc=roc_auc_score(yte,qp), acc=accuracy_score(yte,mdl.predict(Xtes)),
    prec=precision_score(yte,mdl.predict(Xtes),zero_division=0),
    rec=recall_score(yte,mdl.predict(Xtes)),
    f1=f1_score(yte,mdl.predict(Xtes)),
    cm=confusion_matrix(yte,mdl.predict(Xtes)).tolist())

# 2. DecisionTree
mdl = DecisionTreeClassifier(max_depth=4, random_state=42)
mdl.fit(Xtr, ytr)
qp = mdl.predict_proba(Xte)[:,1]
models['DecisionTree'] = dict(model=mdl, preds=mdl.predict(Xte), probs=qp,
    auc=roc_auc_score(yte,qp), acc=accuracy_score(yte,mdl.predict(Xte)),
    prec=precision_score(yte,mdl.predict(Xte),zero_division=0),
    rec=recall_score(yte,mdl.predict(Xte)),
    f1=f1_score(yte,mdl.predict(Xte)),
    cm=confusion_matrix(yte,mdl.predict(Xte)).tolist())

# 3. KNN
mdl = KNeighborsClassifier(n_neighbors=7, weights='distance')
mdl.fit(Xtrs, ytr)
qp = mdl.predict_proba(Xtes)[:,1]
models['KNN'] = dict(model=mdl, preds=mdl.predict(Xtes), probs=qp,
    auc=roc_auc_score(yte,qp), acc=accuracy_score(yte,mdl.predict(Xtes)),
    prec=precision_score(yte,mdl.predict(Xtes),zero_division=0),
    rec=recall_score(yte,mdl.predict(Xtes)),
    f1=f1_score(yte,mdl.predict(Xtes)),
    cm=confusion_matrix(yte,mdl.predict(Xtes)).tolist())

# 4. SVM
mdl = SVC(probability=True, kernel='rbf', C=1.0, random_state=42)
mdl.fit(Xtrs, ytr)
qp = mdl.predict_proba(Xtes)[:,1]
models['SVM'] = dict(model=mdl, preds=mdl.predict(Xtes), probs=qp,
    auc=roc_auc_score(yte,qp), acc=accuracy_score(yte,mdl.predict(Xtes)),
    prec=precision_score(yte,mdl.predict(Xtes),zero_division=0),
    rec=recall_score(yte,mdl.predict(Xtes)),
    f1=f1_score(yte,mdl.predict(Xtes)),
    cm=confusion_matrix(yte,mdl.predict(Xtes)).tolist())

# 5. AdaBoost
mdl = AdaBoostClassifier(n_estimators=50, learning_rate=0.1, random_state=42)
mdl.fit(Xtr, ytr)
qp = mdl.predict_proba(Xte)[:,1]
models['AdaBoost'] = dict(model=mdl, preds=mdl.predict(Xte), probs=qp,
    auc=roc_auc_score(yte,qp), acc=accuracy_score(yte,mdl.predict(Xte)),
    prec=precision_score(yte,mdl.predict(Xte),zero_division=0),
    rec=recall_score(yte,mdl.predict(Xte)),
    f1=f1_score(yte,mdl.predict(Xte)),
    cm=confusion_matrix(yte,mdl.predict(Xte)).tolist())

# 6. XGBoost
mdl = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42, eval_metric='logloss')
mdl.fit(Xtr, ytr)
qp = mdl.predict_proba(Xte)[:,1]
models['XGBoost'] = dict(model=mdl, preds=mdl.predict(Xte), probs=qp,
    auc=roc_auc_score(yte,qp), acc=accuracy_score(yte,mdl.predict(Xte)),
    prec=precision_score(yte,mdl.predict(Xte),zero_division=0),
    rec=recall_score(yte,mdl.predict(Xte)),
    f1=f1_score(yte,mdl.predict(Xte)),
    cm=confusion_matrix(yte,mdl.predict(Xte)).tolist())

# 7. RandomForest (GridSearchCV)
gsrf = GridSearchCV(RandomForestClassifier(random_state=42),
    {'n_estimators':[50,100,200],'max_depth':[3,5,7,10],'min_samples_split':[2,5,10],'min_samples_leaf':[1,3,5]},
    cv=5, n_jobs=-1, scoring='roc_auc')
gsrf.fit(Xtr, ytr)
mdl = gsrf.best_estimator_
qp = mdl.predict_proba(Xte)[:,1]
models['RandomForest'] = dict(model=mdl, preds=mdl.predict(Xte), probs=qp,
    auc=roc_auc_score(yte,qp), acc=accuracy_score(yte,mdl.predict(Xte)),
    prec=precision_score(yte,mdl.predict(Xte),zero_division=0),
    rec=recall_score(yte,mdl.predict(Xte)),
    f1=f1_score(yte,mdl.predict(Xte)),
    cm=confusion_matrix(yte,mdl.predict(Xte)).tolist(),
    best_params=gsrf.best_params_, cv_auc=float(gsrf.best_score_))
print(f"RF best params: {gsrf.best_params_}, CV AUC: {gsrf.best_score_:.4f}, Test AUC: {roc_auc_score(yte,qp):.4f}")

# 8. GradientBoosting (GridSearchCV)
gsg = GridSearchCV(GradientBoostingClassifier(random_state=42),
    {'n_estimators':[50,100,200],'max_depth':[2,3,4],'learning_rate':[0.01,0.05,0.1],'min_samples_split':[2,5]},
    cv=5, n_jobs=-1, scoring='roc_auc')
gsg.fit(Xtr, ytr)
mdl = gsg.best_estimator_
qp = mdl.predict_proba(Xte)[:,1]
models['GradientBoosting'] = dict(model=mdl, preds=mdl.predict(Xte), probs=qp,
    auc=roc_auc_score(yte,qp), acc=accuracy_score(yte,mdl.predict(Xte)),
    prec=precision_score(yte,mdl.predict(Xte),zero_division=0),
    rec=recall_score(yte,mdl.predict(Xte)),
    f1=f1_score(yte,mdl.predict(Xte)),
    cm=confusion_matrix(yte,mdl.predict(Xte)).tolist(),
    best_params=gsg.best_params_, cv_auc=float(gsg.best_score_))
print(f"GB best params: {gsg.best_params_}, CV AUC: {gsg.best_score_:.4f}, Test AUC: {roc_auc_score(yte,qp):.4f}")

# Best model
bn = max(models, key=lambda k: models[k]['auc'])
print(f"\nBest model: {bn} (AUC={models[bn]['auc']:.4f})")
probs = models[bn]['probs']
n_te = len(yte)

# ═══ FEATURE IMPORTANCE (RandomForest) ═══
rf_model = models['RandomForest']['model']
importances = rf_model.feature_importances_
feat_imp = sorted(zip(feats, importances), key=lambda x: x[1], reverse=True)
top10 = feat_imp[:10]
print(f"\nTop 10 features:")
for i,(f,v) in enumerate(top10):
    print(f"  {i+1}. {f}: {v:.4f}")

# ═══ THRESHOLD ANALYSIS ═══
te_rets = np.array([df.loc[idxte[j]+1,'pct_chg']/100 if idxte[j]<len(df)-1 else 0 for j in range(n_te)])
bench_ret = np.prod(1+te_rets)-1

def run_full(probs, rets, buy_t, name):
    pos=np.array([1.0 if p>=buy_t else 0.0 for p in probs])
    sr=pos*rets-abs(pos*rets*0.001)
    cum=np.cumprod(1+sr); dd=(cum-np.maximum.accumulate(cum))/np.maximum.accumulate(cum)
    active=pos>0; trades=int(active.sum()); wins=int((sr[active]>0).sum()) if trades else 0
    return {'name':name,'type':'full','buy':buy_t,'trades':trades,'wins':wins,
        'wr':wins/trades*100 if trades else 0,
        'ret':float(cum[-1]-1),'excess':float((cum[-1]-1)-bench_ret),
        'sharpe':float(np.mean(sr)/(np.std(sr)+1e-10)*np.sqrt(252)) if trades else 0,
        'mdd':float(dd.min())}

def run_pos(probs, rets, buy_t, sell_t, name):
    n=len(probs); pos=0.0; pos_arr=[]; sr=[]
    for j in range(n):
        if probs[j]>=buy_t: pos=min(1.0,(probs[j]-0.5)*2)
        elif probs[j]<=sell_t: pos=0.0
        pos_arr.append(pos); sr.append(pos*rets[j]-abs(pos*rets[j]*0.001))
    pos_arr=np.array(pos_arr); sr=np.array(sr)
    cum=np.cumprod(1+sr); dd=(cum-np.maximum.accumulate(cum))/np.maximum.accumulate(cum)
    active=pos_arr>0.01; trades=int(active.sum()); wins=int((sr[active]>0).sum()) if trades else 0
    return {'name':name,'type':'pos','buy':buy_t,'sell':sell_t,'trades':trades,'wins':wins,
        'wr':wins/trades*100 if trades else 0,
        'ret':float(cum[-1]-1),'excess':float((cum[-1]-1)-bench_ret),
        'sharpe':float(np.mean(sr)/(np.std(sr)+1e-10)*np.sqrt(252)) if trades else 0,
        'mdd':float(dd.min()),'avg_pos':float(pos_arr.mean()*100)}

S = {
    'f060': run_full(probs, te_rets, 0.60, '0.60/0.40 全仓'),
    'p060': run_pos(probs, te_rets, 0.60, 0.40, '0.60/0.40 仓位控制'),
}

print(f"\nBenchmark: {bench_ret:.2%}")
print(f"Probs: mean={probs.mean():.4f} min={probs.min():.4f} max={probs.max():.4f}")
for k in ['f060','p060']:
    s=S[k]; print(f"{s['name']}: {s['trades']} trades, WR={s['wr']:.1f}%, Ret={s['ret']*100:+.1f}%, Sharpe={s['sharpe']:.2f}")

# ═══ SAVE ALL DATA ═══
model_data = {}
for n,m in models.items():
    model_data[n] = {
        'auc': round(m['auc'],4), 'acc': round(m['acc'],4),
        'prec': round(m['prec'],4), 'rec': round(m['rec'],4), 'f1': round(m['f1'],4),
        'cm': m['cm'],
    }
    if 'cv_auc' in m: model_data[n]['cv_auc'] = round(m['cv_auc'],4)
    if 'best_params' in m: model_data[n]['best_params'] = m['best_params']

save_data = {
    'models': model_data,
    'best_model': bn,
    'features': feats,
    'n_features': len(feats),
    'n_samples': len(df),
    'strategies': {k: {kk:vv for kk,vv in v.items() if kk not in ('cum','daily','pos_arr')} for k,v in S.items()},
    'benchmark': round(bench_ret,4),
    'top10_features': [(f,round(float(v),4)) for f,v in top10],
}

with open(OUT/'task6_2_full_data.json','w',encoding='utf-8') as f:
    json.dump(save_data, f, indent=2, ensure_ascii=False)
print(f"\nSaved: task6_2_full_data.json")
