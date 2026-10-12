import sqlite3
from datetime import date, datetime, timedelta
from calendar import monthrange

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "db/income.db")
ASSET_TYPES = ("Bond","Stock","FD","RD","Mutual Fund","Other")
STATUSES = ("Active","Disabled","Closed")
INCOME_TYPES = ("Interest","Dividend","Coupon","Capital Gain","Other")
FREQUENCIES = ("Monthly","Quarterly","Half-Yearly","Yearly","One-Time")

def db():
    c=sqlite3.connect(DB_FILE); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def init_db():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS investments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,asset_type TEXT NOT NULL,name TEXT NOT NULL,
    issuer TEXT,isin TEXT,account_reference TEXT,principal_amount REAL NOT NULL DEFAULT 0,
    units REAL,purchase_price REAL,current_value REAL,interest_rate REAL,
    income_type TEXT NOT NULL DEFAULT 'Interest',income_frequency TEXT NOT NULL DEFAULT 'Yearly',
    income_amount REAL,purchase_date TEXT,maturity_type TEXT NOT NULL DEFAULT 'Fixed Maturity',
    maturity_date TEXT,next_income_date TEXT,currency TEXT NOT NULL DEFAULT 'INR',
    status TEXT NOT NULL DEFAULT 'Active',notes TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS income_records(
    id INTEGER PRIMARY KEY AUTOINCREMENT,investment_id INTEGER NOT NULL,income_date TEXT NOT NULL,
    amount REAL NOT NULL,income_type TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Received',
    notes TEXT,received_date TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
    FOREIGN KEY(investment_id) REFERENCES investments(id) ON DELETE CASCADE)""")
    c.commit(); c.close()

def _dt(v,label):
    if not v:return None
    try:return datetime.strptime(str(v),"%Y-%m-%d").date().isoformat()
    except:raise ValueError(f"Invalid {label}. Use YYYY-MM-DD.")
def _num(v,label,required=False):
    if v in (None,""):
        if required:raise ValueError(f"{label} is required.")
        return None
    try:x=float(v)
    except:raise ValueError(f"{label} must be a number.")
    if x<0:raise ValueError(f"{label} cannot be negative.")
    return x

def validate(d):
    if d.get("asset_type") not in ASSET_TYPES: raise ValueError("Invalid asset type.")
    if not str(d.get("name","")).strip(): raise ValueError("Investment name is required.")
    p=_num(d.get("principal_amount"),"Principal amount",True)
    mt=d.get("maturity_type") or "Fixed Maturity"
    if mt not in ("Fixed Maturity","Perpetual","No Maturity"):raise ValueError("Invalid maturity type.")
    md=_dt(d.get("maturity_date"),"maturity date")
    if mt=="Fixed Maturity" and not md:raise ValueError("Maturity date is required.")
    if mt!="Fixed Maturity":md=None
    if d.get("income_type") not in INCOME_TYPES:raise ValueError("Invalid income type.")
    if d.get("income_frequency") not in FREQUENCIES:raise ValueError("Invalid income frequency.")
    if d.get("status") not in STATUSES:raise ValueError("Invalid status.")
    return dict(asset_type=d["asset_type"],name=str(d["name"]).strip(),issuer=str(d.get("issuer") or "").strip(),
      isin=str(d.get("isin") or "").strip(),account_reference=str(d.get("account_reference") or "").strip(),
      principal_amount=p,units=_num(d.get("units"),"Units"),purchase_price=_num(d.get("purchase_price"),"Purchase price"),
      current_value=_num(d.get("current_value"),"Current value"),interest_rate=_num(d.get("interest_rate"),"Interest rate"),
      income_type=d["income_type"],income_frequency=d["income_frequency"],income_amount=_num(d.get("income_amount"),"Income amount"),
      purchase_date=_dt(d.get("purchase_date"),"purchase date"),maturity_type=mt,maturity_date=md,
      next_income_date=_dt(d.get("next_income_date"),"next income date"),currency=str(d.get("currency") or "INR").upper(),
      status=d["status"],notes=str(d.get("notes") or "").strip())

def add_investment(d):
    v=validate(d); now=datetime.now().isoformat(timespec="seconds"); c=db()
    cur=c.execute("""INSERT INTO investments(asset_type,name,issuer,isin,account_reference,principal_amount,units,purchase_price,current_value,interest_rate,income_type,income_frequency,income_amount,purchase_date,maturity_type,maturity_date,next_income_date,currency,status,notes,created_at,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",tuple(v.values())+(now,now))
    c.commit(); i=cur.lastrowid;c.close();return get_investment(i)
def update_investment(i,d):
    v=validate(d); now=datetime.now().isoformat(timespec="seconds"); c=db()
    cols=list(v.keys()); cur=c.execute("UPDATE investments SET "+",".join(f"{x}=?" for x in cols)+",updated_at=? WHERE id=?",tuple(v.values())+(now,int(i)))
    if not cur.rowcount:c.close();raise ValueError("Investment not found.")
    c.commit();c.close();return get_investment(i)
def get_investment(i):
    c=db();r=c.execute("SELECT * FROM investments WHERE id=?",(i,)).fetchone();c.close();return dict(r) if r else None
def list_investments(status="All",asset_type="All",search=""):
    c=db();q="SELECT * FROM investments WHERE 1=1";p=[]
    if status!="All":q+=" AND status=?";p.append(status)
    if asset_type!="All":q+=" AND asset_type=?";p.append(asset_type)
    if search:q+=" AND (lower(name) LIKE ? OR lower(coalesce(issuer,'')) LIKE ? OR lower(coalesce(isin,'')) LIKE ?)";t="%"+search.lower()+"%";p += [t,t,t]
    q+=" ORDER BY CASE status WHEN 'Active' THEN 1 WHEN 'Disabled' THEN 2 ELSE 3 END,coalesce(maturity_date,'9999-12-31'),name"
    r=c.execute(q,p).fetchall();c.close();return [dict(x) for x in r]
def set_status(i,s):
    if s not in STATUSES:raise ValueError("Invalid status.")
    c=db();cur=c.execute("UPDATE investments SET status=?,updated_at=? WHERE id=?",(s,datetime.now().isoformat(timespec="seconds"),i))
    if not cur.rowcount:c.close();raise ValueError("Investment not found.")
    c.commit();c.close();return get_investment(i)

def record_income(i,d):
    if not get_investment(i):raise ValueError("Investment not found.")
    dt=_dt(d.get("income_date"),"income date")
    amount=_num(d.get("amount"),"Income amount",True)
    if amount<=0:raise ValueError("Income amount must be greater than zero.")
    typ=d.get("income_type") or "Other";status=d.get("status") or "Received"
    if typ not in INCOME_TYPES or status not in ("Expected","Received","Cancelled"):raise ValueError("Invalid income data.")
    now=datetime.now().isoformat(timespec="seconds");c=db()
    cur=c.execute("INSERT INTO income_records(investment_id,income_date,amount,income_type,status,notes,received_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
      (i,dt,amount,typ,status,str(d.get("notes") or ""),_dt(d.get("received_date"),"received date"),now,now))
    c.commit();rid=cur.lastrowid;c.close();return get_income(rid)
def get_income(i):
    c=db();r=c.execute("SELECT ir.*,i.name investment_name,i.asset_type FROM income_records ir JOIN investments i ON i.id=ir.investment_id WHERE ir.id=?",(i,)).fetchone();c.close();return dict(r) if r else None
def list_income(status="All",investment_id=None):
    c=db();q="SELECT ir.*,i.name investment_name,i.asset_type FROM income_records ir JOIN investments i ON i.id=ir.investment_id WHERE 1=1";p=[]
    if status!="All":q+=" AND ir.status=?";p.append(status)
    if investment_id is not None:q+=" AND ir.investment_id=?";p.append(investment_id)
    q+=" ORDER BY ir.income_date DESC,ir.id DESC";r=c.execute(q,p).fetchall();c.close();return [dict(x) for x in r]

def upcoming_income(days=90):
    today=date.today();end=today+timedelta(days=int(days));out=[]
    for r in list_income("Expected"):
        d=date.fromisoformat(r["income_date"])
        if today<=d<=end:r["days_until"]=(d-today).days;out.append(r)
    for i in list_investments("Active"):
        if i["next_income_date"] and i["income_amount"]:
            d=date.fromisoformat(i["next_income_date"])
            if today<=d<=end and not any(x["investment_id"]==i["id"] and x["income_date"]==i["next_income_date"] for x in out):
                out.append(dict(investment_id=i["id"],investment_name=i["name"],asset_type=i["asset_type"],income_date=i["next_income_date"],amount=i["income_amount"],income_type=i["income_type"],status="Scheduled",days_until=(d-today).days))
    return sorted(out,key=lambda x:(x["income_date"],x["investment_name"]))
def maturities(days=90):
    today=date.today();end=today+timedelta(days=int(days));out=[]
    for i in list_investments("Active"):
        if i["maturity_date"]:
            d=date.fromisoformat(i["maturity_date"])
            if today<=d<=end:i["days_until"]=(d-today).days;out.append(i)
    return out

def dashboard():
    a=list_investments("Active"); invested=sum(x["principal_amount"] or 0 for x in a);value=sum(x["current_value"] if x["current_value"] is not None else x["principal_amount"] for x in a);annual=0
    for x in a:
        m={"Monthly":1,"Quarterly":3,"Half-Yearly":6,"Yearly":12}.get(x["income_frequency"])
        if x["income_amount"]:annual += x["income_amount"]*(12/m if m else 1)
    today=date.today();y=list_income("Received");year=sum(x["amount"] for x in y if x["income_date"][:4]==str(today.year))
    mat=maturities(90)
    return dict(active_count=len(a),total_invested=round(invested,2),current_value=round(value,2),annual_income=round(annual,2),monthly_income=round(annual/12,2),received_this_year=round(year,2),maturing_90_value=round(sum(x["principal_amount"] for x in mat),2),maturing_90_count=len(mat))
def asset_summary():
    c=db();r=c.execute("""SELECT asset_type,count(*) count,sum(principal_amount) invested,sum(coalesce(current_value,principal_amount)) current_value FROM investments WHERE status='Active' GROUP BY asset_type ORDER BY invested DESC""").fetchall();c.close();return [dict(x) for x in r]
init_db()
