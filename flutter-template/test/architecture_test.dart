import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:pema_native_template/features/aftercare/presentation/providers/review_queue_provider.dart';
import 'package:pema_native_template/features/billing/presentation/providers/receipts_provider.dart';
import 'package:pema_native_template/features/catalog/data/mappers/catalog_mapper.dart';
import 'package:pema_native_template/features/catalog/presentation/providers/catalog_provider.dart';
import 'package:pema_native_template/features/customer_care/domain/models/care_case.dart';
import 'package:pema_native_template/features/customer_care/presentation/providers/care_queue_provider.dart';
import 'package:pema_native_template/features/orders/presentation/providers/orders_provider.dart';
import 'package:pema_native_template/features/patients/presentation/providers/patients_provider.dart';
import 'package:pema_native_template/features/session/presentation/providers/session_provider.dart';
import 'package:pema_native_template/features/finance/data/datasources/finance_remote_data_source.dart';
import 'package:pema_native_template/features/finance/data/mappers/finance_mapper.dart';
import 'package:pema_native_template/features/finance/data/repositories/finance_repository_impl.dart';
import 'package:pema_native_template/features/finance/domain/models/procedure_entry.dart';

import 'finance_test.dart' show fixture;
import 'support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  group('CatalogMapper', () {
    test('maps a profile and renames web keys', () {
      final p = CatalogMapper.profile({
        'id': 'P037',
        'name': 'Trần Minh Châu',
        'doctor': 'BS. Mai',
        'sessions': 2,
        'total': 6,
        'appointment': '09:30',
        'day': '2026-09-23',
        'group': 'd3',
        'case': 'Ảnh tiến triển · D+3',
        'tasks': [
          {'id': 'T1', 'type': 'd3', 'title': 'Gửi ảnh', 'status': 'open'},
        ],
      });
      expect(p.totalSessions, 6);
      expect(p.careGroup, 'd3');
      expect(p.caseLabel, 'Ảnh tiến triển · D+3');
      expect(p.inCareQueue, true);
      expect(p.hasTask('d3'), true);
      expect(p.initials, 'MC');
    });

    test('a profile without CSKH fields is outside the queue', () {
      final p = CatalogMapper.profile({
        'id': 'P001',
        'name': 'Nguyễn Văn A',
        'doctor': 'BS. Tâm',
        'sessions': 0,
        'total': 4,
        'appointment': '',
        'day': '',
      });
      expect(p.inCareQueue, false);
      expect(p.tasks, isEmpty);
    });

    test('maps a product and rounds the price', () {
      final p = CatalogMapper.product({
        'id': '1',
        'code': 'SP01',
        'name': 'Kem dưỡng',
        'unit': 'Tuýp',
        'sourceType': 'Mỹ phẩm',
        'price': 120000.0,
        'outputType': 'UNRESOLVED',
      });
      expect(p.price, 120000);
      expect(p.needsClassification, true);
      expect(p.matches('sp01'), true);
    });
  });

  group('FinanceMapper', () {
    test('maps the owner snapshot to typed fields', () {
      final s = FinanceMapper.snapshot(fixture());
      expect(s.periodOpen, true);
      expect(s.summary.collected, 1200000);
      expect(s.doctorName('D1'), 'BS. Mai');
      expect(s.revenueOf('D0'), 2400000);
      expect(s.rows.single.ratePercent, 20.0);
      expect(s.receivable.single.due, 1200000);
      expect(s.unread, 1);
      expect(s.notifications.single.shortTime, '2026-09-22 10:00');
    });

    test('a doctor projection has no cash totals or invoices', () {
      final s = FinanceMapper.snapshot(fixture(role: 'doctor'));
      expect(s.summary.collected, isNull);
      expect(s.summary.debt, isNull);
      expect(s.invoices, isEmpty);
    });

    test('equal JSON yields equal snapshots', () {
      expect(
        FinanceMapper.snapshot(fixture()),
        FinanceMapper.snapshot(fixture()),
      );
    });
  });

  group('view-model providers', () {
    test('care queue tracks contact status but ignores cart edits', () async {
      final c = clinicContainer(await loadCatalog());
      final catalog = c.read(catalogProvider);
      final first = c.read(careCasesProvider).first;
      expect(first.status, careNotContacted);
      var notified = 0;
      c.listen(careCasesProvider, (_, _) => notified++);
      c
          .read(patientsProvider.notifier)
          .addToCart(first.profile.id, catalog.products.first);
      c.read(careCasesProvider);
      expect(notified, 0);
      c
          .read(patientsProvider.notifier)
          .update(
            first.profile.id,
            (p) => p.copyWith(careStatus: 'Đã liên hệ'),
          );
      expect(c.read(careCasesProvider).first.status, 'Đã liên hệ');
      expect(notified, 1);
    });

    test(
      'review queue lists only the doctor\'s profiles needing review',
      () async {
        final c = clinicContainer(await loadCatalog());
        c.read(sessionProvider.notifier).enterStaff('doctor', 'BS. Mai');
        final queue = c.read(reviewQueueProvider);
        expect(queue.every((p) => p.doctor == 'BS. Mai'), true);
        final quiet = c
            .read(catalogProvider)
            .profiles
            .firstWhere((p) => p.doctor == 'BS. Mai' && !queue.contains(p));
        c
            .read(patientsProvider.notifier)
            .update(quiet.id, (p) => p.copyWith(updates: ['Da đỡ đỏ']));
        expect(c.read(reviewQueueProvider), contains(quiet));
      },
    );

    test('current bill sums the patient orders', () async {
      final c = clinicContainer(await loadCatalog());
      final id = c.read(selectedPatientIdProvider);
      final product = c.read(catalogProvider).products[1];
      c.read(patientsProvider.notifier)
        ..addToCart(id, product)
        ..addToCart(id, product);
      c.read(ordersProvider.notifier).save(id, approve: false);
      expect(c.read(currentBillProvider).total, product.price * 2);
      expect(c.read(currentBillProvider).due, product.price * 2);
    });
  });

  group('FinanceRepositoryImpl', () {
    late List<http.Request> sent;
    late FinanceRepositoryImpl repository;
    const actor = (role: 'accountant', doctor: 'D0');

    setUp(() {
      sent = [];
      repository = FinanceRepositoryImpl(
        FinanceRemoteDataSource(
          MockClient((r) async {
            sent.add(r);
            return http.Response('{}', 200);
          }),
          baseUrl: 'http://api',
        ),
      );
    });

    test('typed commands post the API action and body', () async {
      await repository.approveEntry('TT-1', actor);
      await repository.recordPayment(
        key: 'APP-1',
        invoice: 'FIN-1',
        amount: 5000,
        method: 'Tiền mặt',
        actor: actor,
      );
      expect(sent.map((r) => r.url.path), [
        '/command/approve',
        '/command/payment',
      ]);
      expect(jsonDecode(sent[0].body), {'id': 'TT-1'});
      expect(jsonDecode(sent[1].body), {
        'id': 'APP-1',
        'invoice': 'FIN-1',
        'amount': 5000,
        'method': 'Tiền mặt',
      });
      expect(sent[0].headers['X-Pema-Role'], 'accountant');
    });

    test('a procedure entry is sent with the server keys', () async {
      await repository.recordEntry(
        const ProcedureEntry(
          patient: 'P001',
          invoice: '',
          service: 'S0',
          date: '2026-09-22',
          listPrice: 2500000,
          discount: 100000,
          note: 'Hoàn tất',
          people: [
            ProcedureShare(doctor: 'D0', share: 7000, rate: 2000),
            ProcedureShare(doctor: 'D1', share: 3000, rate: 1000),
          ],
        ),
        actor,
      );
      final body = jsonDecode(sent.single.body) as Map<String, dynamic>;
      expect(sent.single.url.path, '/command/entry');
      expect(body['list'], 2500000);
      expect(body['people'], [
        {'doctor': 'D0', 'share': 7000, 'rate': 2000},
        {'doctor': 'D1', 'share': 3000, 'rate': 1000},
      ]);
    });

    test('a server error surfaces as an exception', () async {
      final failing = FinanceRepositoryImpl(
        FinanceRemoteDataSource(
          MockClient(
            (r) async => http.Response(
              jsonEncode({'error': 'Kỳ đã chốt'}),
              409,
              headers: {'content-type': 'application/json; charset=utf-8'},
            ),
          ),
          baseUrl: 'http://api',
        ),
      );
      expect(failing.closePeriod('2026-09', actor), throwsA(isA<Exception>()));
    });
  });
}
