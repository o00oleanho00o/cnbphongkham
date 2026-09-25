import 'package:freezed_annotation/freezed_annotation.dart';

part 'product.freezed.dart';

/// A catalog item as supplied in the Excel export.
@freezed
abstract class Product with _$Product {
  const Product._();

  const factory Product({
    required String id,
    required String code,
    required String name,
    required String unit,

    /// Excel "loại" column, e.g. "Thuốc".
    required String sourceType,
    required int price,

    /// `PRESCRIPTION`, `CONSULTATION` or `UNRESOLVED` (needs classification).
    required String outputType,
  }) = _Product;

  bool get needsClassification => outputType == 'UNRESOLVED';

  /// Case-insensitive match on code or name; [query] must be lower-case.
  bool matches(String query) => '$code $name'.toLowerCase().contains(query);
}
