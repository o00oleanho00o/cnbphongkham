import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pema_native_template/app.dart';
import 'package:pema_native_template/core/router/app_router.dart';
import 'package:pema_native_template/features/catalog/presentation/providers/catalog_provider.dart';
import 'package:pema_native_template/features/orders/presentation/providers/orders_provider.dart';
import 'package:pema_native_template/features/billing/presentation/providers/receipts_provider.dart';
import 'package:pema_native_template/features/patients/presentation/providers/patients_provider.dart';
import 'package:pema_native_template/features/session/presentation/providers/session_provider.dart';

import 'support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('catalog, draft approval and patient isolation', () async {
    final c = clinicContainer(await loadCatalog());
    final catalog = c.read(catalogProvider);
    expect(catalog.products.length, 115);
    expect(
      catalog.products.where((p) => p['outputType'] == 'UNRESOLVED').length,
      7,
    );
    final id = c.read(selectedPatientIdProvider);
    final patients = c.read(patientsProvider.notifier);
    final orders = c.read(ordersProvider.notifier);
    patients.addToCart(id, catalog.products.first);
    expect(c.read(currentPatientProvider).cartReady, false);
    expect(() => orders.save(id, approve: true), throwsStateError);
    patients.updateLine(
      id,
      0,
      (l) => l.copyWith(usage: 'Hướng dẫn được bác sĩ kiểm tra'),
    );
    expect(c.read(currentPatientProvider).cartReady, true);
    orders.save(id, approve: false);
    expect(c.read(currentOrdersProvider).single.approved, false);
    expect(c.read(currentPatientProvider).cart, isEmpty);
    orders.edit(id, c.read(currentOrdersProvider).single);
    orders.save(id, approve: true);
    expect(c.read(currentOrdersProvider).length, 1);
    expect(c.read(currentOrdersProvider).single.approved, true);
    c.read(receiptsProvider.notifier).settle(id, 100);
    c.read(sessionProvider.notifier).select(1);
    expect(c.read(currentOrdersProvider), isEmpty);
    expect(c.read(currentPaidProvider), 0);
  });
  for (final width in [360.0, 390.0, 430.0, 768.0]) {
    testWidgets('home and detail layouts at $width', (tester) async {
      tester.view.physicalSize = Size(width, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final catalog = (await tester.runAsync(loadCatalog))!;
      final c = clinicContainer(catalog);
      final id = c.read(selectedPatientIdProvider);
      final patients = c.read(patientsProvider.notifier);
      patients.addToCart(id, catalog.products.first);
      patients.updateLine(
        id,
        0,
        (l) => l.copyWith(usage: 'Hướng dẫn mẫu bác sĩ đã xem'),
      );
      c.read(ordersProvider.notifier).save(id, approve: true);
      patients.addToCart(id, catalog.products[1]);
      await tester.pumpWidget(scoped(c, const PemaApp()));
      await tester.pumpAndSettle();
      expect(find.text('Chào buổi sáng, BS. Tâm'), findsOneWidget);
      expect(tester.takeException(), isNull);
      for (final route in [
        'Patient 360',
        'Đặt lịch',
        'Lên đơn nhanh',
        'Kiểm tra đơn',
        'Thu ngân',
        'Gửi cập nhật',
        'Ảnh tiến triển',
        'Ask Pema',
        'Bác sĩ & phòng',
        'Kế hoạch điều trị',
        'Phiếu A5',
        'Đơn thuốc & tư vấn',
      ]) {
        await tester.pumpWidget(
          scoped(
            c,
            MaterialApp(
              theme: ThemeData(fontFamily: 'BeVietnam'),
              onGenerateRoute: AppRouter.onGenerateRoute,
              home: AppRouter.page(route),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: route);
      }
      await tester.pumpWidget(const SizedBox());
    });
  }
  testWidgets('native order form adds catalog item and opens review', (
    tester,
  ) async {
    final catalog = (await tester.runAsync(loadCatalog))!;
    final c = clinicContainer(catalog);
    await tester.pumpWidget(
      scoped(
        c,
        MaterialApp(
          onGenerateRoute: AppRouter.onGenerateRoute,
          home: AppRouter.page('Lên đơn nhanh'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(catalog.products.first['name']));
    await tester.pumpAndSettle();
    expect(c.read(currentPatientProvider).cart.length, 1);
    await tester.tap(find.textContaining('Xem đơn ·'));
    await tester.pumpAndSettle();
    expect(find.text('Kiểm tra trước khi duyệt'), findsOneWidget);
    expect(c.read(currentPatientProvider).cartReady, false);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
