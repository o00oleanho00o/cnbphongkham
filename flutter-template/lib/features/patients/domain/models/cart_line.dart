import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../catalog/domain/models/product.dart';

part 'cart_line.freezed.dart';

@freezed
abstract class CartLine with _$CartLine {
  const CartLine._();

  const factory CartLine({
    required Product product,

    /// Output route chosen by the doctor; starts as the catalog's `outputType`.
    required String route,
    @Default(1) int quantity,
    @Default('') String usage,
  }) = _CartLine;

  factory CartLine.of(Product product) =>
      CartLine(product: product, route: product.outputType);

  String get code => product.code;
  String get name => product.name;
  String get unit => product.unit;
  int get total => product.price * quantity;
}
