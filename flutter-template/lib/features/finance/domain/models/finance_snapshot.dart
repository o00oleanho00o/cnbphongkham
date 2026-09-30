import 'package:freezed_annotation/freezed_annotation.dart';

part 'finance_snapshot.freezed.dart';

@freezed
abstract class FinanceSummary with _$FinanceSummary {
  const factory FinanceSummary({
    required int revenue,
    required int fee,
    required int pending,

    /// Omitted from a doctor's private projection.
    int? collected,
    int? debt,
  }) = _FinanceSummary;
}

@freezed
abstract class FinanceDoctor with _$FinanceDoctor {
  const factory FinanceDoctor({required String id, required String name}) =
      _FinanceDoctor;
}

/// A billable procedure and its current fee policy.
@freezed
abstract class ProcedureService with _$ProcedureService {
  const ProcedureService._();

  const factory ProcedureService({
    required String id,
    required String name,
    required int price,

    /// Basis points: 2000 = 20%.
    required int rate,

    /// `net`, `list` or `collected`.
    required String basis,
    required int version,
  }) = _ProcedureService;

  double get ratePercent => rate / 100;
}

/// One performer's share of a completed procedure in the month.
@freezed
abstract class ProcedureRow with _$ProcedureRow {
  const ProcedureRow._();

  const factory ProcedureRow({
    required String id,
    required String date,
    required String patient,
    required String service,
    required String doctor,

    /// `pending`, `approved` or `void`.
    required String status,
    required int base,

    /// Basis points.
    required int rate,
    required int revenue,
    required int fee,
  }) = _ProcedureRow;

  double get ratePercent => rate / 100;
  bool get isVoid => status == 'void';
  bool get isPending => status == 'pending';
}

@freezed
abstract class FinanceInvoice with _$FinanceInvoice {
  const FinanceInvoice._();

  const factory FinanceInvoice({
    required String id,
    required String patient,

    /// `finance` or `web` (legacy cashier mirror).
    required String source,
    required int amount,
    required int received,
  }) = _FinanceInvoice;

  int get due => amount - received;
}

@freezed
abstract class PaymentNotification with _$PaymentNotification {
  const PaymentNotification._();

  const factory PaymentNotification({
    required String id,
    required String title,
    required String body,
    required bool read,

    /// ISO-8601 with offset.
    required String at,
  }) = _PaymentNotification;

  /// `2026-09-22T10:00:00+07:00` → `2026-09-22 10:00`.
  String get shortTime => at.substring(0, 16).replaceAll('T', ' ');
}

/// Role-scoped finance projection for one month.
@freezed
abstract class FinanceSnapshot with _$FinanceSnapshot {
  const FinanceSnapshot._();

  const factory FinanceSnapshot({
    required String month,
    required String today,

    /// `open`, `closed` or `paid`.
    required String periodStatus,
    required FinanceSummary summary,
    @Default([]) List<FinanceDoctor> doctors,
    @Default([]) List<ProcedureService> services,
    @Default([]) List<ProcedureRow> rows,
    @Default([]) List<FinanceInvoice> invoices,
    @Default([]) List<PaymentNotification> notifications,
  }) = _FinanceSnapshot;

  bool get periodOpen => periodStatus == 'open';
  bool get periodClosed => periodStatus == 'closed';

  int get unread => notifications.where((n) => !n.read).length;

  String doctorName(String id) => doctors.firstWhere((d) => d.id == id).name;

  /// Allocated revenue of one doctor, excluding voided rows.
  int revenueOf(String doctorId) => rows
      .where((r) => r.doctor == doctorId && !r.isVoid)
      .fold(0, (sum, r) => sum + r.revenue);

  /// Finance-owned invoices with money still to collect here.
  List<FinanceInvoice> get receivable => [
    for (final i in invoices)
      if (i.due > 0 && i.source == 'finance') i,
  ];
}
