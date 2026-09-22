import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pema_native_template/main.dart';
import 'package:pema_native_template/store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('catalog, draft approval and patient isolation', () async {
    final s=DemoStore(); await s.load();
    expect(s.products.length,115);
    expect(s.products.where((p)=>p['outputType']=='UNRESOLVED').length,7);
    s.add(s.products.first); expect(s.ready,false);
    s.cart.first['usage']='Hướng dẫn được bác sĩ kiểm tra';
    expect(s.ready,true);s.saveOrder(false);expect(s.myOrders.single['approved'],false);
    s.edit(s.myOrders.single);s.saveOrder(true);expect(s.myOrders.length,1);expect(s.myOrders.single['approved'],true);
    s.paid=100;s.selected=1;expect(s.myOrders,isEmpty);expect(s.paid,0);
  });
  for(final width in [360.0,390.0,430.0,768.0]) {
    testWidgets('home and detail layouts at $width', (tester) async {
      tester.view.physicalSize=Size(width,844);tester.view.devicePixelRatio=1;
      addTearDown(tester.view.resetPhysicalSize);addTearDown(tester.view.resetDevicePixelRatio);
      final s=DemoStore();await tester.runAsync(s.load);
      s.add(s.products.first);s.cart.first['usage']='Hướng dẫn mẫu bác sĩ đã xem';
      s.saveOrder(true);s.add(s.products[1]);
      await tester.pumpWidget(PemaApp(store:s));await tester.pumpAndSettle();
      expect(find.text('Chào buổi sáng, BS. Tâm'),findsOneWidget);expect(tester.takeException(),isNull);
      for(final route in ['Patient 360','Đặt lịch','Lên đơn nhanh','Kiểm tra đơn','Thu ngân','Gửi cập nhật','Ảnh tiến triển','Ask Pema','Bác sĩ & phòng','Kế hoạch điều trị','Phiếu A5','Đơn thuốc & tư vấn']) {
        await tester.pumpWidget(MaterialApp(theme:ThemeData(fontFamily:'BeVietnam'),home:Detail(store:s,route:route)));
        await tester.pumpAndSettle();expect(tester.takeException(),isNull,reason:route);
      }
    });
  }
  testWidgets('native order form adds catalog item and opens review', (tester) async {
    final s=DemoStore();await tester.runAsync(s.load);
    await tester.pumpWidget(MaterialApp(home:Detail(store:s,route:'Lên đơn nhanh')));
    await tester.pumpAndSettle();
    await tester.tap(find.text(s.products.first['name']));await tester.pumpAndSettle();
    expect(s.cart.length,1);
    await tester.tap(find.textContaining('Xem đơn ·'));await tester.pumpAndSettle();
    expect(find.text('Kiểm tra trước khi duyệt'),findsOneWidget);
    expect(s.ready,false);expect(tester.takeException(),isNull);
  });
}
