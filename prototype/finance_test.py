import unittest, tempfile, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from finance_server import Finance, today, date, timedelta

class FinanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.f=Finance(Path(self.tmp.name)/'test.db');self.month=today()[:7]
    def tearDown(self):self.tmp.cleanup()
    def cmd(self,a,d,role='accountant',doctor='D0'):return self.f.command(role,doctor,a,d)
    def entry(self,**kw):
        d=dict(patient='P001',date=today(),service='S2',list=2500000,discount=100000,note='Đã hoàn tất',people=[dict(doctor='D0',share=7000,rate=1500),dict(doctor='D1',share=3000,rate=500)]);d.update(kw);return self.cmd('entry',d)
    def test_split_discount_and_snapshot(self):
        e=self.entry();rows=[r for r in self.f.view('owner','D0',self.month)['rows'] if r['id']==e['id']]
        self.assertEqual([r['fee'] for r in rows],[360000,120000]);self.assertEqual(sum(r['revenue'] for r in rows),2400000)
        self.cmd('rate',dict(service='S2',rate=3000,basis='list'))
        self.assertEqual([r['fee'] for r in self.f.rows(self.f.load(),self.month) if r['id']==e['id']],[360000,120000])
    def test_validation_rollback(self):
        before=self.f.load()
        for override in [dict(people=[]),dict(discount=3000000),dict(people=[dict(doctor='D0',share=7000,rate=2000)]),dict(people=[dict(doctor='D0',share=10000,rate=11000)]),dict(note='')]:
            with self.assertRaises(ValueError):self.entry(**override)
        self.assertEqual(before,self.f.load())
    def test_role_projection_and_write(self):
        v=self.f.view('doctor','D1',self.month)
        self.assertTrue(all(r['doctor']=='D1' for r in v['rows']));self.assertEqual(v['invoices'],[]);self.assertEqual(v['notifications'],[]);self.assertNotIn('collected',v['summary'])
        with self.assertRaises(ValueError):self.cmd('rate',dict(service='S2',rate=3000,basis='net'),'doctor','D1')
        with self.assertRaises(ValueError):self.f.view('owner','D1',self.month)
    def test_payment_idempotency_notification_and_persistence(self):
        e=self.entry();p=dict(id='test-receipt',invoice=e['invoice'],amount=1000000,method='Tiền mặt')
        self.cmd('payment',p);self.cmd('payment',p)
        s=Finance(self.f.path).load();self.assertEqual(len([n for n in s['notifications'] if n['id']=='test-receipt']),1)
        self.assertEqual(next(i['received'] for i in s['invoices'] if i['id']==e['invoice']),1000000)
        with self.assertRaises(ValueError):self.cmd('payment',{**p,'amount':1})
        with self.assertRaises(ValueError):self.cmd('payment',{**p,'id':'test-over','amount':2000000})
        self.cmd('read',{'id':'test-receipt'},'owner');self.assertTrue(self.f.load()['notifications'][0]['read'])
    def test_parallel_payment_serialized(self):
        e=self.entry();p=dict(id='concurrent-payment',invoice=e['invoice'],amount=1000000,method='Tiền mặt')
        with ThreadPoolExecutor(max_workers=5) as ex:list(ex.map(lambda _:self.cmd('payment',p),range(5)))
        self.assertEqual(len([n for n in self.f.load()['notifications'] if n['id']==p['id']]),1)
    def test_collected_and_close_snapshot(self):
        month=(date.fromisoformat(today()).replace(day=1)-timedelta(days=1)).isoformat()[:7]
        self.cmd('rate',dict(service='S2',rate=2000,basis='collected'));e=self.entry(date=month+'-10')
        self.cmd('payment',dict(id='collect-a',invoice=e['invoice'],amount=1200000,method='Tiền mặt'))
        with self.assertRaises(ValueError):self.cmd('close',dict(month=month))
        self.cmd('approve',dict(id=e['id']))
        with self.assertRaises(ValueError):self.cmd('close',dict(month=month))
        self.cmd('payment',dict(id='collect-b',invoice=e['invoice'],amount=1200000,method='Tiền mặt'))
        self.cmd('close',dict(month=month))
        frozen=[r for r in self.f.view('owner','D0',month)['rows'] if r['id']==e['id']]
        self.assertEqual(sum(r['fee'] for r in frozen),480000)
        self.cmd('rate',dict(service='S2',rate=3000,basis='list'))
        self.assertEqual(frozen,[r for r in self.f.view('owner','D0',month)['rows'] if r['id']==e['id']])
        for a in ['approve','void']:
            with self.assertRaises(ValueError):self.cmd(a,dict(id=e['id'],reason='test'))
        with self.assertRaises(ValueError):self.entry(date=month+'-12')
        self.cmd('paid',dict(month=month,reference='CHI-01'));self.assertEqual(self.f.view('owner','D0',month)['period']['status'],'paid')
    def test_void_and_no_close_current_month(self):
        e=self.entry();self.cmd('void',dict(id=e['id'],reason='Ghi nhầm'));self.assertEqual(next(i['amount'] for i in self.f.load()['invoices'] if i['id']==e['invoice']),0)
        with self.assertRaises(ValueError):self.cmd('close',dict(month=self.month))
    def test_revenue_rounding_reconciles(self):
        e=self.entry(list=101,discount=0,people=[dict(doctor='D0',share=3333,rate=1000),dict(doctor='D1',share=3333,rate=1000),dict(doctor='D2',share=3334,rate=1000)])
        rows=[r for r in self.f.rows(self.f.load(),self.month) if r['id']==e['id']]
        self.assertEqual(sum(r['revenue'] for r in rows),101)
    def test_http_csv_and_role_projection(self):
        from finance_server import Handler, ThreadingHTTPServer
        from threading import Thread
        from urllib.request import Request, urlopen
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.finance=self.f
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            root='http://127.0.0.1:'+str(server.server_port)
            headers={'X-Pema-Role':'doctor','X-Pema-Doctor':'D1'}
            with urlopen(Request(root+'/state?month='+self.month,headers=headers)) as r:
                data=json.load(r);self.assertTrue(all(x['doctor']=='D1' for x in data['rows']))
            with urlopen(Request(root+'/export?month='+self.month,headers=headers)) as r:
                text=r.read().decode('utf-8-sig');self.assertIn('D1',text);self.assertNotIn('D0',text)
        finally:server.shutdown();server.server_close();thread.join()
    def test_link_existing_invoice_without_duplicate_debt(self):
        self.cmd('sync',dict(invoices=[dict(id='INV-EXIST',patient='P001',amount=2400000,received=0)],payments=[]))
        before=len(self.f.load()['invoices']);e=self.entry(invoice='WEB:P001:INV-EXIST')
        self.assertEqual(len(self.f.load()['invoices']),before)
        with self.assertRaises(ValueError):self.entry(invoice='WEB:P001:INV-EXIST')
        with self.assertRaises(ValueError):self.entry(invoice='WEB:P001:INV-EXIST',patient='P002')
        self.cmd('void',dict(id=e['id'],reason='Sai phân bổ'))
        self.assertEqual(next(i['amount'] for i in self.f.load()['invoices'] if i['id']=='WEB:P001:INV-EXIST'),2400000)
    def test_legacy_sync_not_double_collection(self):
        data=dict(invoices=[dict(id='WEB-1',patient='P001',amount=1000000,received=300000)],payments=[dict(id='WEB-PAY',patient='P001',invoice='WEB-1',amount=300000,method='Tiền mặt',at=today()+'T10:00:00+07:00')])
        self.cmd('sync',data);self.cmd('sync',data)
        s=self.f.load();self.assertEqual(len([p for p in s['payments'] if p['id']=='WEB:WEB-PAY']),1);self.assertEqual(next(i['received'] for i in s['invoices'] if i['id']=='WEB:P001:WEB-1'),300000)
        with self.assertRaises(ValueError):self.cmd('payment',dict(id='wrong-channel',invoice='WEB:P001:WEB-1',amount=100,method='Tiền mặt'))

if __name__=='__main__':unittest.main(verbosity=2)
