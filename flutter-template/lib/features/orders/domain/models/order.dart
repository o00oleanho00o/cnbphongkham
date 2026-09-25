import '../../../patients/domain/models/cart_line.dart';

class Order {
  const Order({
    required this.id,
    required this.patientId,
    required this.patientName,
    required this.approved,
    required this.items,
  });

  final String id, patientId, patientName;
  final bool approved;
  final List<CartLine> items;

  int get total => items.fold(0, (sum, line) => sum + line.total);
}
