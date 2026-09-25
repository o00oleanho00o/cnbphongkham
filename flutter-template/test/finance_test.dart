import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:pema_native_template/features/finance/presentation/screens/finance_screen.dart';
import 'package:pema_native_template/features/finance/presentation/screens/procedure_form_screen.dart';
import 'package:pema_native_template/app.dart';
import 'package:pema_native_template/features/catalog/presentation/providers/catalog_provider.dart';
import 'package:pema_native_template/core/network/http_client_provider.dart';
import 'package:pema_native_template/features/finance/presentation/providers/finance_provider.dart';

import 'support.dart';

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
ProviderContainer financeContainer(http.Client client) =>
    ProviderContainer.test(
      overrides: [httpClientProvider.overrideWithValue(client)],
    );

http.Response json(Object body, [int status = 200]) => http.Response(
  jsonEncode(body),
  status,
  headers: {'content-type': 'application/json; charset=utf-8'},
);

void main() {
  test(
    'API role selection clears old private data and receives notification',
    () async {
      final c = financeContainer(
        MockClient(
          (r) async => json(
            fixture(
              role:
                  r.headers['X-Pema-Role'] ??
                  r.headers['x-pema-role'] ??
                  'owner',
            ),
          ),
        ),
      );
      final finance = c.read(financeProvider.notifier);
      await finance.refresh();
      expect(c.read(financeProvider).unread, 1);
      finance.select('doctor:D1');
      expect(c.read(financeProvider).data, isNull);
      await finance.refresh();
      expect(c.read(financeProvider).unread, 0);
      expect(c.read(financeProvider).data!['invoices'], isEmpty);
    },
  );
  test(
    'API failed payment retains error and does not fabricate success',
    () async {
      final c = financeContainer(
        MockClient((r) async => json({'error': 'Số thu vượt công nợ'}, 400)),
      );
      final finance = c.read(financeProvider.notifier);
      expect(await finance.command('payment', {'amount': 9999999}), false);
      expect(c.read(financeProvider).error, contains('vượt công nợ'));
      expect(c.read(financeProvider).data, isNull);
      expect(c.read(financeProvider).sending, false);
    },
  );
  testWidgets('owner sees new payment alert while a detail route is open', (
    tester,
  ) async {
    var payments = 1;
    Map<String, dynamic> state() {
      final value = fixture();
      value['notifications'] = [
        for (var i = 0; i < payments; i++)
          {
            'id': 'PT-$i',
            'title': 'Đã nhận thanh toán',
            'body': 'P001',
            'read': false,
            'at': '2026-09-22T10:00:00+07:00',
          },
      ];
      return value;
    }

    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final catalog = (await tester.runAsync(loadCatalog))!;
    final c = ProviderContainer(
      overrides: [
        catalogProvider.overrideWithValue(catalog),
        financeEnabledProvider.overrideWithValue(true),
        httpClientProvider.overrideWithValue(
          MockClient((r) async => json(state())),
        ),
      ],
    );
    await tester.pumpWidget(scoped(c, const PemaApp()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Thu ngân').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Thu ngân').first);
    await tester.pumpAndSettle();
    expect(find.text('Khoản cần thanh toán'), findsOneWidget);
    payments = 2;
    await tester.pump(const Duration(seconds: 4));
    await tester.pump();
    expect(find.text('Có thanh toán mới tại phòng khám'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    c.dispose();
  });
  for (final width in [360.0, 390.0, 430.0, 768.0]) {
    testWidgets('finance tabs and procedure form at $width', (tester) async {
      tester.view.physicalSize = Size(width, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final c = financeContainer(MockClient((r) async => json(fixture())));
      await c.read(financeProvider.notifier).refresh();
      await tester.pumpWidget(
        scoped(c, const MaterialApp(home: FinanceScreen())),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      for (final label in ['Thủ thuật', 'Thu tiền', 'Thông báo', 'Tổng quan']) {
        await tester.tap(find.widgetWithText(NavigationDestination, label));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: label);
      }
      await tester.pumpWidget(
        scoped(
          c,
          MaterialApp(
            home: ProcedureForm(
              initialPatient: 'P046',
              patientIds: List.generate(
                46,
                (i) => 'P${(i + 1).toString().padLeft(3, '0')}',
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('P046'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });
  }
}
