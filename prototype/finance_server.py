"""Pema local finance demo. No production authentication; do not use real records."""
import argparse, csv, io, json, sqlite3, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

TZ = timezone(timedelta(hours=7))
def today(): return datetime.now(TZ).date().isoformat()
def uid(): return str(uuid.uuid4())
def check(ok, message):
    if not ok: raise ValueError(message)
def integer(v, low=0, high=10**12):
    check(type(v) is int and low <= v <= high, 'Số tiền/tỷ lệ không hợp lệ')
    return v
def valid_day(v):
    try: return date.fromisoformat(v).isoformat() == v
    except (ValueError, TypeError): return False
def money(base, rate): return (base * rate + 5000) // 10000

def seed():
    now = today(); prev = (date.fromisoformat(now).replace(day=1)-timedelta(days=1)).isoformat()[:7]
    s = dict(doctors=[dict(id='D'+str(i), name=n) for i,n in enumerate(['BS. Tâm','BS. Mai','BS. An','BS. Lan'])],
      services=[dict(id='S'+str(i),name=n,price=p,rate=r,basis='net',version=1) for i,(n,p,r) in enumerate([
        ('Tái khám & đánh giá',300000,1000),('Tư vấn da liễu',500000,1500),('Laser theo chỉ định',2500000,2000),('Chăm sóc theo chỉ định',1200000,1200)])],
      entries=[], invoices=[], payments=[], notifications=[], periods={}, audit=[])
    for i in range(24):
        service=s['services'][i%4]; day=(prev if i<12 else now[:7])+'-'+str((i%12)+1).zfill(2)
        if day>now: day=now
        net=service['price']- (100000 if i%4==2 else 0); inv='FIN-HD-'+str(i+1)
        s['invoices'].append(dict(id=inv,patient='P'+str(i%36+1).zfill(3),name='Khách mẫu '+str(i+1),amount=net,received=net if i%3 else net//2,source='finance',date=day))
        s['entries'].append(dict(id='TT-'+str(i+1),patient='P'+str(i%36+1).zfill(3),service=service['id'],serviceName=service['name'],date=day,invoice=inv,list=service['price'],discount=service['price']-net,net=net,basis='net',policyVersion=1,status='approved',note='Lượt hoàn tất minh họa',people=[dict(doctor='D'+str(i%4),share=10000,rate=service['rate'])]))
        pay=dict(id='SEED-'+str(i),invoice=inv,patient='P'+str(i%36+1).zfill(3),amount=net if i%3 else net//2,method='Chuyển khoản' if i%2 else 'Tiền mặt',date=day,source='finance')
        s['payments'].append(pay)
    return s

class Finance:
    def __init__(self,path):
        self.path=str(path); Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO state VALUES(1,?)',(json.dumps(seed(),ensure_ascii=False),))
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        try:
            with db: yield db
        finally: db.close()
    def load(self):
        with self.connect() as db: return json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
    def actor(self,role,doctor):
        check(role in ['owner','accountant','doctor'], 'Vai trò không hợp lệ')
        check(doctor in ['D0','D1','D2','D3'], 'Bác sĩ không hợp lệ')
        check(role!='owner' or doctor=='D0','Chủ phòng khám là BS. Tâm')
    def rows(self,s,month,doctor=None):
        rows=[]
        for e in s['entries']:
            if e['date'][:7]!=month: continue
            inv=next(i for i in s['invoices'] if i['id']==e['invoice'])
            base=e['net'] if e['basis']=='net' else e['list'] if e['basis']=='list' else min(e['net'], e['net']*inv['received']//max(1,inv['amount']))
            allocated=0
            for index,p in enumerate(e['people']):
                revenue=e['net']-allocated if index==len(e['people'])-1 else e['net']*p['share']//10000
                allocated+=revenue
                if doctor and p['doctor']!=doctor: continue
                rows.append(dict(id=e['id'],date=e['date'],patient=e['patient'],service=e['serviceName'],doctor=p['doctor'],status=e['status'],basis=e['basis'],base=base,rate=p['rate'],share=p['share'],revenue=revenue,fee=money(base,p['rate']),note=e.get('note','')))
        return rows
    def view(self,role,doctor,month):
        self.actor(role,doctor); check(valid_day(month+'-01'),'Tháng không hợp lệ')
        s=self.load(); private=role=='doctor'; period=s['periods'].get(month)
        rows=period['rows'] if period else self.rows(s,month)
        if private: rows=[r for r in rows if r['doctor']==doctor]
        active=[r for r in rows if r['status']!='void']; approved=[r for r in active if r['status']=='approved']
        payments=[p for p in s['payments'] if p['date'][:7]==month]
        entries=[e for e in s['entries'] if e['date'][:7]==month and e['status']!='void']
        summary=dict(revenue=sum(r['revenue'] for r in active) if private else sum(e['net'] for e in entries),fee=sum(r['fee'] for r in approved),pending=sum(r['fee'] for r in active if r['status']=='pending'))
        if not private: summary.update(collected=sum(p['amount'] for p in payments),debt=sum(i['amount']-i['received'] for i in s['invoices']))
        return dict(month=month,today=today(),role=role,doctor=doctor,summary=summary,rows=rows,period=dict(status=period['status'],at=period['at']) if period else dict(status='open'),
          doctors=[d for d in s['doctors'] if not private or d['id']==doctor],services=[] if private else s['services'],
          invoices=[] if private else s['invoices'],payments=[] if private else payments,
          notifications=[] if role!='owner' else s['notifications'][:100], audit=[] if private else s['audit'][-30:][::-1])
    def command(self,role,doctor,action,d):
        self.actor(role,doctor); check(role in ['owner','accountant'],'Không có quyền thay đổi dữ liệu tài chính')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE'); s=json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])
            result=self.mutate(s,role,doctor,action,d)
            s['audit'].append(dict(at=datetime.now(TZ).isoformat(),role=role,doctor=doctor,action=action,record=str(result.get('id',''))))
            db.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(s,ensure_ascii=False),))
            return result
    def mutate(self,s,role,doctor,action,d):
        if action=='rate':
            service=next((x for x in s['services'] if x['id']==d.get('service')),None); check(service,'Không tìm thấy thủ thuật')
            check(d.get('basis') in ['net','list','collected'],'Cơ sở tính không hợp lệ')
            service.update(rate=integer(d.get('rate'),0,10000),basis=d['basis'],version=service['version']+1)
            return service
        if action=='entry':
            day=d.get('date'); check(valid_day(day) and day<=today(),'Ngày thực hiện không hợp lệ')
            check(day[:7] not in s['periods'],'Kỳ đã chốt')
            service=next((x for x in s['services'] if x['id']==d.get('service')),None); check(service,'Không có thủ thuật')
            patient=d.get('patient',''); check(len(patient)==4 and patient[0]=='P' and patient[1:].isdigit() and 1<=int(patient[1:])<=999,'Chọn mã hồ sơ P001–P999')
            gross=integer(d.get('list'),1); discount=integer(d.get('discount'),0,gross); people=d.get('people',[])
            check(isinstance(people,list) and 0<len(people)<=4,'Cần người thực hiện')
            check(len({p.get('doctor') for p in people})==len(people),'Trùng người thực hiện')
            for p in people:
                check(p.get('doctor') in [x['id'] for x in s['doctors']],'Người thực hiện không hợp lệ')
                integer(p.get('share'),1,10000); integer(p.get('rate'),0,10000)
            check(sum(p['share'] for p in people)==10000,'Tổng tỷ trọng doanh số phải là 100%')
            check(sum(p['rate'] for p in people)<=10000,'Tổng tỷ lệ tiền thủ thuật không vượt 100%')
            id='TT-'+uid(); inv=d.get('invoice')
            owns=not inv
            if inv:
                linked=next((i for i in s['invoices'] if i['id']==inv and i['patient']==patient),None)
                check(linked,'Hóa đơn không thuộc bệnh nhân này')
                allocated=sum(e['net'] for e in s['entries'] if e['invoice']==inv and e['status']!='void')
                check(allocated+gross-discount<=linked['amount'],'Giá trị lượt vượt phần hóa đơn chưa phân bổ')
            else:
                inv='FIN-HD-'+uid()
                s['invoices'].append(dict(id=inv,patient=patient,name=patient,amount=gross-discount,received=0,source='finance',date=day))
            e=dict(id=id,date=day,patient=patient,invoice=inv,service=service['id'],serviceName=service['name'],list=gross,discount=discount,net=gross-discount,people=people,basis=service['basis'],policyVersion=service['version'],ownsInvoice=owns,status='pending',note=str(d.get('note','')).strip())
            check(e['note'],'Ghi chú xác nhận hoàn tất là bắt buộc'); s['entries'].append(e); return e
        if action in ['approve','void']:
            e=next((e for e in s['entries'] if e['id']==d.get('id')),None); check(e,'Không tìm thấy lượt')
            check(e['date'][:7] not in s['periods'],'Kỳ đã chốt, không được sửa')
            check(e['status']!='void','Lượt đã hủy')
            if action=='void':
                check(str(d.get('reason','')).strip(),'Cần lý do hủy')
                inv=next(i for i in s['invoices'] if i['id']==e['invoice']);check(inv['received']==0,'Lượt đã thu tiền; cần quy trình hoàn/điều chỉnh riêng')
                if e.get('ownsInvoice',True): inv['amount']=0
                e['note']=str(d['reason']);e['status']='void'
            else: e['status']='approved'
            return e
        if action in ['close','paid']:
            month=d.get('month','');check(valid_day(month+'-01') and month<today()[:7],'Chỉ chốt tháng đã kết thúc')
            if action=='close':
                check(month not in s['periods'],'Kỳ đã chốt')
                rows=self.rows(s,month);check(rows,'Kỳ không có dữ liệu')
                collected_entries=[e for e in s['entries'] if e['date'][:7]==month and e['basis']=='collected' and e['status']!='void']
                check(all(next(i for i in s['invoices'] if i['id']==e['invoice'])['received']>=next(i for i in s['invoices'] if i['id']==e['invoice'])['amount'] for e in collected_entries),'Còn lượt tính theo thực thu chưa thu đủ; chưa thể chốt để tránh mất tiền kỳ sau')
                check(not any(r['status']=='pending' for r in rows),'Còn lượt chờ duyệt')
                s['periods'][month]=dict(status='closed',at=datetime.now(TZ).isoformat(),rows=rows)
            else:
                check(month in s['periods'] and s['periods'][month]['status']=='closed','Cần chốt kỳ trước khi xác nhận chi')
                check(str(d.get('reference','')).strip(),'Cần mã chứng từ chi')
                s['periods'][month].update(status='paid',reference=d['reference'])
            return dict(id=month)
        if action=='payment':
            key=d.get('id','');check(isinstance(key,str) and 3<=len(key)<=160,'Cần mã chống thu trùng')
            old=next((p for p in s['payments'] if p['id']==key),None)
            if old:
                check(old['invoice']==d.get('invoice') and old['amount']==d.get('amount') and old['method']==d.get('method'),'Mã giao dịch đã dùng cho nội dung khác')
                return old
            inv=next((i for i in s['invoices'] if i['id']==d.get('invoice')),None);check(inv and inv['source']=='finance','Hóa đơn web cũ phải thu tại Thu ngân web')
            amount=integer(d.get('amount'),1);check(amount<=inv['amount']-inv['received'],'Số thu vượt công nợ')
            check(d.get('method') in ['Tiền mặt','Chuyển khoản'],'Phương thức không hợp lệ')
            inv['received']+=amount
            p=dict(id=key,invoice=inv['id'],patient=inv['patient'],amount=amount,method=d['method'],date=today(),source='finance')
            s['payments'].append(p);self.notify(s,p);return p
        if action=='sync':
            # Mirror successful legacy receipts; never re-collect cash here.
            for raw in d.get('invoices',[]):
                id='WEB:'+str(raw['patient'])+':'+str(raw['id']);amount=integer(raw['amount']);received=integer(raw['received'],0,amount)
                inv=next((i for i in s['invoices'] if i['id']==id),None)
                item=dict(id=id,patient=str(raw['patient']),name=str(raw.get('name',raw['patient'])),amount=amount,received=received,source='web',date=str(raw.get('date',today())))
                if inv: inv.update(item)
                else:s['invoices'].append(item)
            for raw in d.get('payments',[]):
                id='WEB:'+str(raw['id'])
                if any(p['id']==id for p in s['payments']):continue
                amount=integer(raw['amount'],1);inv='WEB:'+str(raw['patient'])+':'+str(raw['invoice'])
                check(any(i['id']==inv for i in s['invoices']),'Thiếu hóa đơn nguồn')
                day=datetime.fromisoformat(raw['at'].replace('Z','+00:00')).astimezone(TZ).date().isoformat()
                p=dict(id=id,invoice=inv,patient=str(raw['patient']),amount=amount,method=str(raw['method']),date=day,source='web')
                s['payments'].append(p);self.notify(s,p)
            return dict(id='sync')
        if action=='read':
            check(role=='owner','Chỉ chủ đọc thông báo của mình')
            n=next((n for n in s['notifications'] if n['id']==d.get('id')),None);check(n,'Không tìm thấy thông báo');n['read']=True;return n
        raise ValueError('Thao tác không tồn tại')
    def notify(self,s,p):
        s['notifications'].insert(0,dict(id=p['id'],title='Đã nhận thanh toán',body=p['patient']+' · '+format(p['amount'],',').replace(',', '.')+' đ · '+p['method'],amount=p['amount'],invoice=p['invoice'],at=datetime.now(TZ).isoformat(),read=False))

class Handler(BaseHTTPRequestHandler):
    def headers_out(self,status=200,kind='application/json; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',kind)
        origin=self.headers.get('Origin','')
        parsed=urlparse(origin)
        if parsed.hostname in ['localhost','127.0.0.1']:self.send_header('Access-Control-Allow-Origin',origin)
        self.send_header('Access-Control-Allow-Headers','Content-Type, X-Pema-Role, X-Pema-Doctor')
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Cache-Control','no-store');self.end_headers()
    def reply(self,value,status=200):self.headers_out(status);self.wfile.write(json.dumps(value,ensure_ascii=False).encode())
    def do_OPTIONS(self):self.headers_out(204)
    def do_GET(self):
        try:
            path=urlparse(self.path);q=parse_qs(path.query);role=self.headers.get('X-Pema-Role','doctor');doctor=self.headers.get('X-Pema-Doctor','D0')
            if path.path=='/health':return self.reply(dict(ok=True))
            check(path.path in ['/state','/export'],'Endpoint không tồn tại')
            v=self.server.finance.view(role,doctor,q.get('month',[today()[:7]])[0])
            if path.path=='/export':
                out=io.StringIO();w=csv.writer(out);w.writerow(['Ngay','Ho so','Thu thuat','Bac si','Doanh so','Co so','Ty le %','Tien thu thuat','Trang thai'])
                for r in v['rows']:
                    def safe(x):
                        t=str(x);return "'"+t if t.startswith(('=','+','-','@')) else t
                    w.writerow([safe(x) for x in [r['date'],r['patient'],r['service'],r['doctor'],r['revenue'],r['base'],r['rate']/100,r['fee'],r['status']]])
                self.headers_out(kind='text/csv; charset=utf-8');self.wfile.write(('\ufeff'+out.getvalue()).encode());return
            self.reply(v)
        except (ValueError,KeyError,TypeError) as e:self.reply(dict(error=str(e)),400)
    def do_POST(self):
        try:
            check(self.path.startswith('/command/'),'Endpoint không tồn tại');length=int(self.headers.get('Content-Length','0'));check(0<length<2000000,'Payload không hợp lệ')
            d=json.loads(self.rfile.read(length));check(isinstance(d,dict),'Payload không hợp lệ')
            result=self.server.finance.command(self.headers.get('X-Pema-Role','doctor'),self.headers.get('X-Pema-Doctor','D0'),self.path.split('/')[-1],d);self.reply(result)
        except (ValueError,KeyError,TypeError) as e:self.reply(dict(error=str(e)),400)
    def log_message(self,*args):pass

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=4174);parser.add_argument('--db',default=str(Path(__file__).parent.parent/'.local/finance.sqlite3'));args=parser.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.finance=Finance(args.db)
    print('Pema finance API: http://127.0.0.1:'+str(args.port),flush=True);server.serve_forever()
if __name__=='__main__':main()
