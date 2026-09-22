import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pema_native_template/main.dart';
import 'package:pema_native_template/store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('ten CSKH accounts and complete patient state isolation', () async {
    final s = DemoStore();
    await s.load();
    expect(s.profiles.length, 46);
    final cases = s.profiles.where((p) => p['group'] != '').toList();
    expect(cases.map((p) => p['group']).toSet().length, 10);
    for (final p in cases) {
      expect((p['tasks'] as List).any((t) => t['type'] == p['group']), true);
    }
    s.selected = 36;
    s.note = 'Clinical';
    s.response = 'Approved reply';
    s.day = '2026-10-01';
    s.appointment = '14:00';
    s.acknowledged = true;
    s.updates.add('My update');
    s.current.careNote = 'PRIVATE';
    s.current.escalations.add('Internal');
    s.add(s.products.first);
    s.editingOrder = 'Draft';
    s.selected = 37;
    expect(s.note, '');
    expect(s.response, '');
    expect(s.day, '');
    expect(s.acknowledged, false);
    expect(s.updates, isEmpty);
    expect(s.cart, isEmpty);
    expect(s.editingOrder, isNull);
    expect(s.current.careNote, '');
    s.selected = 36;
    expect(s.note, 'Clinical');
    expect(s.day, '2026-10-01');
    expect(s.cart.length, 1);
    s.careMode = true;
    expect(s.selected, 0);
    s.selected = 38;
    s.careMode = false;
    expect(s.selected, 36);
    s.staffRole = 'care';
    expect(s.allows('Tư vấn'), false);
    expect(s.allows('Thu ngân'), false);
    expect(s.allows('Chăm sóc khách hàng'), true);
    s.staffRole = 'doctor';
    s.staffDoctor = 'BS. Mai';
    expect(s.owns(36), false);
    expect(s.owns(37), true);
    expect(s.billing, false);
  });
  for (final width in [360.0, 390.0, 430.0, 768.0]) {
    testWidgets('separate role workspaces and patient accounts at $width', (
      tester,
    ) async {
      tester.view.physicalSize = Size(width, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final s = DemoStore();
      await tester.runAsync(s.load);
      await tester.pumpWidget(PemaApp(store: s));
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
      expect(s.current.careStatus, 'Đã liên hệ');
      expect(s.updates, isEmpty);
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.text('Không có khách trong bộ lọc này'), findsOneWidget);
      await tester.tap(find.text('Đã liên hệ'));
      await tester.pumpAndSettle();
      expect(find.text('Trần Minh Châu'), findsOneWidget);

      expect(find.text('Thu ngân'), findsNothing);
      await choose('BS. Mai · Bác sĩ điều trị');
      expect(find.text('Lịch & hồ sơ của tôi'), findsOneWidget);
      expect(s.profile['doctor'], 'BS. Mai');
      await choose('Kế toán · Đối soát & thu ngân');
      expect(find.text('Đối soát & thu ngân'), findsOneWidget);
      expect(find.text('CSKH hôm nay'), findsNothing);
      await choose('Người bệnh · Pema Care');
      s.change(() => s.selected = 37);
      await tester.pumpAndSettle();
      expect(find.text('Cập nhật ảnh tiến triển'), findsOneWidget);
      await tester.tap(find.text('Hồ sơ'));
      await tester.pumpAndSettle();
      expect(find.text('Tài khoản mẫu · 10 nhóm CSKH'), findsOneWidget);
      expect(tester.takeException(), isNull);
      s.current.careNote = 'PRIVATE-CSKH';
      s.current.escalations.add('PRIVATE-CSKH');
      await tester.tap(find.text('Tin nhắn'));
      await tester.pumpAndSettle();
      expect(find.textContaining('PRIVATE-CSKH'), findsNothing);
    });
  }
}
