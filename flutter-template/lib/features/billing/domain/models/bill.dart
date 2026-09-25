import 'package:freezed_annotation/freezed_annotation.dart';

part 'bill.freezed.dart';

/// What one patient owes across their orders and what has been collected.
@freezed
abstract class Bill with _$Bill {
  const Bill._();

  const factory Bill({required int total, required int paid}) = _Bill;

  int get due => total - paid;
  bool get settled => due <= 0;
}
