class CartLine {
  const CartLine({
    required this.product,
    required this.route,
    this.quantity = 1,
    this.usage = '',
  });

  CartLine.of(Map<String, dynamic> product)
    : this(product: product, route: product['outputType'] as String);

  final Map<String, dynamic> product;
  final int quantity;
  final String usage, route;

  String get code => product['code'] as String;
  String get name => product['name'] as String;
  String get unit => product['unit'] as String;
  int get total => ((product['price'] as num) * quantity).round();

  CartLine copyWith({int? quantity, String? usage, String? route}) => CartLine(
    product: product,
    quantity: quantity ?? this.quantity,
    usage: usage ?? this.usage,
    route: route ?? this.route,
  );
}
