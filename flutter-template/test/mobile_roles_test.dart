import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pema_native_template/app.dart';
import 'package:pema_native_template/features/catalog/presentation/providers/catalog_provider.dart';
import 'package:pema_native_template/features/patients/domain/models/patient_state.dart';
import 'package:pema_native_template/features/patients/presentation/providers/patients_provider.dart';
import 'package:pema_native_template/features/session/domain/models/session.dart';
import 'package:pema_native_template/features/session/presentation/providers/session_provider.dart';

import 'support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('ten CSKH accounts and complete patient state isolation', () async {
    final c = clinicContainer(await loadCatalog());
    final profiles = c.read(catalogProvider).profiles;
    expect(profiles.length, 46);
    final cases = profiles.where((p) => p.inCareQueue).toList();
    expect(cases.map((p) => p.careGroup).toSet().length, 10);
    for (final p in cases) {
      expect(p.hasTask(p.careGroup), true);
    }
    final session = c.read(sessionProvider.notifier);
    final patients = c.read(patientsProvider.notifier);
    PatientState current() => c.read(currentPatientProvider);
    session.select(36);
    final id = c.read(selectedPatientIdProvider);
    patients.update(
      id,
      (p) => p.copyWith(
        note: 'Clinical',
        response: 'Approved reply',
        day: '2026-10-01',
        appointment: '14:00',
        acknowledged: true,
        updates: ['My update'],
        careNote: 'PRIVATE',
        escalations: ['Internal'],
        editingOrder: 'Draft',
      ),
    );
    patients.addToCart(id, c.read(catalogProvider).products.first);
    session.select(37);
    expect(current().note, '');
    expect(current().response, '');
    expect(current().day, '');
    expect(current().acknowledged, false);
    expect(current().updates, isEmpty);
    expect(current().cart, isEmpty);
    expect(current().editingOrder, isNull);
    expect(current().careNote, '');
    expect(current().escalations, isEmpty);
    session.select(36);
    expect(current().note, 'Clinical');
    expect(current().day, '2026-10-01');
    expect(current().cart.length, 1);
    session.enterCare();
    expect(c.read(sessionProvider).selected, 0);
    session.select(38);
    session.enterStaff('owner', 'BS. Tâm');
    expect(c.read(sessionProvider).selected, 36);
    const care = Session(staffRole: 'care');
    expect(care.allows('Tư vấn'), false);
    expect(care.allows('Thu ngân'), false);
    expect(care.allows('Chăm sóc khách hàng'), true);
    const mai = Session(staffRole: 'doctor', staffDoctor: 'BS. Mai');
    expect(mai.owns(profiles[36]), false);
    expect(mai.owns(profiles[37]), true);
    expect(mai.billing, false);
  });
  for (final width in [360.0, 390.0, 430.0, 768.0]) {
    testWidgets('separate role workspaces and patient accounts at $width', (
      tester,
    ) async {
      tester.view.physicalSize = Size(width, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final c = clinicContainer((await tester.runAsync(loadCatalog))!);
      PatientState current() => c.read(currentPatientProvider);
      await tester.pumpWidget(scoped(c, const PemaApp()));
      await tester.pumpAndSettle();
      Future<void> choose(String label) async {
        await tester.tap(find.byIcon(Icons.swap_horiz));
        await tester.pumpAndSettle();
        await tester.ensureVisible(find.text(label));
        await tester.tap(find.text(label));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      }

      await choose('Mai Anh · CSKH');
      expect(find.text('CSKH hôm nay'), findsOneWidget);
      expect(
        tester.getTopLeft(find.text('Nguyễn Ánh Dương')).dy,
        lessThan(440),
      );
      await tester.tap(find.byTooltip('Lọc nhóm chăm sóc'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.descendant(
          of: find.byType(BottomSheet),
          matching: find.text('Ảnh tiến triển · D+3'),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('1 khách'), findsOneWidget);
      await tester.tap(find.text('Trần Minh Châu'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField),
        'Đã liên hệ; ghi chú nội bộ',
      );
      await tester.tap(find.text('Lưu kết quả liên hệ'));
      await tester.pumpAndSettle();
      expect(current().careStatus, 'Đã liên hệ');
      expect(current().updates, isEmpty);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.text('Không có khách trong bộ lọc này'), findsOneWidget);
      await tester.tap(find.text('Đã liên hệ'));
      await tester.pumpAndSettle();
      expect(find.text('Trần Minh Châu'), findsOneWidget);

      expect(find.text('Thu ngân'), findsNothing);
      await choose('BS. Mai · Bác sĩ điều trị');
      expect(find.text('Lịch & hồ sơ của tôi'), findsOneWidget);
      expect(c.read(selectedProfileProvider).doctor, 'BS. Mai');
      await choose('Kế toán · Đối soát & thu ngân');
      expect(find.text('Đối soát & thu ngân'), findsOneWidget);
      expect(find.text('CSKH hôm nay'), findsNothing);
      await choose('Người bệnh · Pema Care');
      c.read(sessionProvider.notifier).select(37);
      await tester.pumpAndSettle();
      expect(find.text('Cập nhật ảnh tiến triển'), findsOneWidget);
      await tester.tap(find.text('Hồ sơ'));
      await tester.pumpAndSettle();
      expect(find.text('Tài khoản mẫu · 10 nhóm CSKH'), findsOneWidget);
      expect(tester.takeException(), isNull);
      c
          .read(patientsProvider.notifier)
          .update(
            c.read(selectedPatientIdProvider),
            (p) => p.copyWith(
              careNote: 'PRIVATE-CSKH',
              escalations: ['PRIVATE-CSKH'],
            ),
          );
      await tester.tap(find.text('Tin nhắn'));
      await tester.pumpAndSettle();
      expect(find.textContaining('PRIVATE-CSKH'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    });
  }
}
