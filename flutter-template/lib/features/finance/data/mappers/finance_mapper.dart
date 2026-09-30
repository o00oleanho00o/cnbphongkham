import '../../domain/models/finance_snapshot.dart';
import '../../domain/models/procedure_entry.dart';

/// Converts the finance API JSON (`prototype/finance_server.py`) to domain
/// models and back. Fields the app does not use (payments, audit) are dropped.
abstract final class FinanceMapper {
  static FinanceSnapshot snapshot(Map<String, dynamic> json) {
    final summary = json['summary'] as Map<String, dynamic>;
    return FinanceSnapshot(
      month: json['month'] as String,
      today: json['today'] as String,
      periodStatus: (json['period'] as Map)['status'] as String,
      summary: FinanceSummary(
        revenue: summary['revenue'] as int,
        fee: summary['fee'] as int,
        pending: summary['pending'] as int,
        collected: summary['collected'] as int?,
        debt: summary['debt'] as int?,
      ),
      doctors: [
        for (final d in _list(json['doctors']))
          FinanceDoctor(id: d['id'] as String, name: d['name'] as String),
      ],
      services: [
        for (final s in _list(json['services']))
          ProcedureService(
            id: s['id'] as String,
            name: s['name'] as String,
            price: s['price'] as int,
            rate: s['rate'] as int,
            basis: s['basis'] as String,
            version: s['version'] as int,
          ),
      ],
      rows: [
        for (final r in _list(json['rows']))
          ProcedureRow(
            id: r['id'] as String,
            date: r['date'] as String,
            patient: r['patient'] as String,
            service: r['service'] as String,
            doctor: r['doctor'] as String,
            status: r['status'] as String,
            base: r['base'] as int,
            rate: r['rate'] as int,
            revenue: r['revenue'] as int,
            fee: r['fee'] as int,
          ),
      ],
      invoices: [
        for (final i in _list(json['invoices']))
          FinanceInvoice(
            id: i['id'] as String,
            patient: i['patient'] as String,
            source: i['source'] as String,
            amount: i['amount'] as int,
            received: i['received'] as int,
          ),
      ],
      notifications: [
        for (final n in _list(json['notifications']))
          PaymentNotification(
            id: n['id'] as String,
            title: n['title'] as String,
            body: n['body'] as String,
            read: n['read'] as bool,
            at: n['at'] as String,
          ),
      ],
    );
  }

  static Map<String, dynamic> entry(ProcedureEntry e) => {
    'patient': e.patient,
    'invoice': e.invoice,
    'service': e.service,
    'date': e.date,
    'list': e.listPrice,
    'discount': e.discount,
    'note': e.note,
    'people': [
      for (final p in e.people)
        {'doctor': p.doctor, 'share': p.share, 'rate': p.rate},
    ],
  };

  static Iterable<Map<String, dynamic>> _list(Object? value) =>
      (value as List? ?? const []).cast<Map<String, dynamic>>();
}
