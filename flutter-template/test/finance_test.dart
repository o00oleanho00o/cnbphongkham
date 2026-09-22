import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pema_native_template/finance.dart';

Map<String, dynamic> fixture({String role = 'owner'}) => {
  'today': '2026-09-22',
  'month': '2026-09',
  'role': role,
  'doctor': 'D0',
  'summary': {
    'revenue': 2400000,
    'fee': 480000,
    'pending': 0,
    if (role != 'doctor') 'collected': 1200000,
    if (role != 'doctor') 'debt': 1200000,
  },
  'period': {'status': 'open'},
  'doctors': [
    {'id': 'D0', 'name': 'BS. Tâm'},
    {'id': 'D1', 'name': 'BS. Mai'},
  ],
  'services': [
    {
      'id': 'S0',
      'name': 'Laser theo chỉ định',
      'price': 2500000,
      'rate': 2000,
      'basis': 'net',
      'version': 1,
    },
  ],
  'rows': [
    {
      'id': 'TT-1',
      'date': '2026-09-22',
      'patient': 'P001',
      'service': 'Laser theo chỉ định',
      'doctor': 'D0',
      'status': 'approved',
      'basis': 'net',
      'base': 2400000,
      'rate': 2000,
      'share': 10000,
      'revenue': 2400000,
      'fee': 480000,
    },
  ],
  'invoices': role == 'doctor'
      ? []
      : [
          {
            'id': 'FIN-1',
            'patient': 'P001',
            'source': 'finance',
            'amount': 2400000,
            'received': 1200000,
          },
        ],
  'notifications': role == 'owner'
      ? [
          {
            'id': 'PT-1',
            'title': 'Đã nhận thanh toán',
            'body': 'P001 · 1.200.000 đ · Tiền mặt',
            'read': false,
            'at': '2026-09-22T10:00:00+07:00',
          },
        ]
      : [],
};
void main() {
  test(
    'API role selection clears old private data and receives notification',
    () async {
      final client = MockClient(
        (r) async => http.Response(
          jsonEncode(
            fixture(
              role:
                  r.headers['X-Pema-Role'] ??
                  r.headers['x-pema-role'] ??
                  'owner',
            ),
          ),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        ),
      );
      final c = FinanceController(client: client);
      await c.refresh();
      expect(c.unread, 1);
      c.select('doctor:D1');
      expect(c.data, isNull);
      await c.refresh();
      expect(c.unread, 0);
      expect(c.data!['invoices'], isEmpty);
      c.dispose();
    },
  );
  test(
    'API failed payment retains error and does not fabricate success',
    () async {
      final c = FinanceController(
        client: MockClient(
          (r) async => http.Response(
            jsonEncode({'error': 'Số thu vượt công nợ'}),
            400,
            headers: {'content-type': 'application/json; charset=utf-8'},
          ),
        ),
      );
      expect(await c.command('payment', {'amount': 9999999}), false);
      expect(c.error, contains('vượt công nợ'));
      expect(c.data, isNull);
      c.dispose();
    },
  );
  for (final width in [360.0, 390.0, 430.0, 768.0]) {
    testWidgets('finance tabs and procedure form at $width', (tester) async {
      tester.view.physicalSize = Size(width, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final c = FinanceController(
        client: MockClient(
          (r) async => http.Response(
            jsonEncode(fixture()),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          ),
        ),
      );
      await c.refresh();
      await tester.pumpWidget(MaterialApp(home: FinanceScreen(controller: c)));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      for (final label in ['Thủ thuật', 'Thu tiền', 'Thông báo', 'Tổng quan']) {
        await tester.tap(find.widgetWithText(NavigationDestination, label));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: label);
      }
      await tester.pumpWidget(
        MaterialApp(
          home: ProcedureForm(
            controller: c,
            initialPatient: 'P046',
            patientIds: List.generate(
              46,
              (i) => 'P${(i + 1).toString().padLeft(3, '0')}',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('P046'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      c.dispose();
    });
  }
}
