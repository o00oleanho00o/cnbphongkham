import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class DemoStore extends ChangeNotifier {
  List<Map<String, dynamic>> products = [];
  final patients = List.generate(
    36,
    (i) =>
        '${['Nguyễn Minh Linh', 'Trần Ngọc Anh', 'Lê Hoàng Nam', 'Phạm Thảo Vy', 'Vũ Quỳnh Trang', 'Đặng Gia Hân'][i % 6]}${i < 6 ? '' : ' ${i + 1}'}',
  );
  int selected = 0;
  int sessions = 2;
  bool checkedIn = false, confirmed = false, acknowledged = false;
  String appointment = '10:30', day = '22/09/2026';
  String note = '', response = '';
  final receipts = <String, int>{};
  int get paid => receipts[patientId] ?? 0;
  set paid(int value) => receipts[patientId] = value;
  String? editingOrder;
  final cart = <Map<String, dynamic>>[];
  final orders = <Map<String, dynamic>>[];
  final updates = <String>[
    'Da hơi khô sau buổi điều trị. Em muốn hỏi cách chăm sóc.',
  ];
  String get name => patients[selected];
  String get patientId => 'P${(selected + 1).toString().padLeft(3, '0')}';
  Future<void> load() async {
    products =
        (jsonDecode(await rootBundle.loadString('assets/products.json'))
                as List)
            .cast<Map<String, dynamic>>();
    notifyListeners();
  }

  void change(VoidCallback fn) {
    fn();
    notifyListeners();
  }

  void add(Map<String, dynamic> product) {
    final index = cart.indexWhere((x) => x['code'] == product['code']);
    change(() {
      if (index < 0) {
        cart.add({
          ...product,
          'quantity': 1,
          'usage': '',
          'route': product['outputType'],
        });
      } else {
        cart[index]['quantity']++;
      }
    });
  }

  int get total => cart.fold(
    0,
    (sum, row) =>
        sum + ((row['price'] as num) * (row['quantity'] as int)).round(),
  );
  bool get ready =>
      cart.isNotEmpty &&
      cart.every(
        (x) =>
            x['route'] != 'UNRESOLVED' &&
            (x['usage'] as String).trim().isNotEmpty,
      );
  void saveOrder(bool approve) {
    if (cart.isEmpty || (approve && !ready)) {
      throw StateError('Cần phân loại và nhập hướng dẫn trước khi duyệt');
    }
    change(() {
      final old = orders.indexWhere((x) => x['id'] == editingOrder);
      final record = {
        'id': editingOrder ?? 'DN-${orders.length + 1}',
        'patient': patientId,
        'name': name,
        'approved': approve,
        'total': total,
        'items': cart.map((x) => Map<String, dynamic>.from(x)).toList(),
      };
      if (old >= 0) {
        orders[old] = record;
      } else {
        orders.add(record);
      }
      cart.clear();
      editingOrder = null;
    });
  }

  void edit(Map<String, dynamic> order) {
    change(() {
      editingOrder = order['id'];
      cart.clear();
      cart.addAll(
        (order['items'] as List).map((x) => Map<String, dynamic>.from(x)),
      );
    });
  }

  List<Map<String, dynamic>> get myOrders =>
      orders.where((x) => x['patient'] == patientId).toList();
}

String money(num value) =>
    '${value.round().toString().replaceAllMapped(RegExp(r'(\d)(?=(\d{3})+(?!\d))'), (m) => '${m[1]}.')} ₫';
