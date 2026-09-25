import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../patients/domain/models/cart_line.dart';

part 'order.freezed.dart';

@freezed
abstract class Order with _$Order {
  const Order._();

  const factory Order({
    required String id,
    required String patientId,
    required String patientName,
    required bool approved,
    required List<CartLine> items,
  }) = _Order;

  int get total => items.fold(0, (sum, line) => sum + line.total);
}
