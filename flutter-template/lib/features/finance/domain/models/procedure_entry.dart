import 'package:freezed_annotation/freezed_annotation.dart';

part 'procedure_entry.freezed.dart';

/// One performer of a procedure entry.
@freezed
abstract class ProcedureShare with _$ProcedureShare {
  const factory ProcedureShare({
    required String doctor,

    /// Basis points of revenue; all shares of an entry sum to 10000.
    required int share,

    /// Basis points of the fee rate.
    required int rate,
  }) = _ProcedureShare;
}

/// A completed procedure to record; the server validates every field.
@freezed
abstract class ProcedureEntry with _$ProcedureEntry {
  const factory ProcedureEntry({
    required String patient,

    /// Existing invoice id, or empty to create a new invoice.
    required String invoice,
    required String service,
    required String date,
    required int listPrice,
    required int discount,
    required String note,
    required List<ProcedureShare> people,
  }) = _ProcedureEntry;
}
