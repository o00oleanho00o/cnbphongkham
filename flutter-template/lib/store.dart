import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class DemoStore extends ChangeNotifier {
  List<Map<String, dynamic>> products = [];
  List<Map<String, dynamic>> profiles = [];
  List<String> get patients =>
      profiles.map((p) => p['name'] as String).toList();
  int staffSelected = 0, careSelected = 0;
  bool careMode = false;
  String staffRole = 'owner', staffDoctor = 'BS. Tâm', staffName = 'BS. Tâm';
  int get selected => careMode ? careSelected : staffSelected;
  set selected(int value) {
    if (careMode) {
      careSelected = value;
    } else {
      staffSelected = value;
    }
  }

  Map<String, dynamic> get profile => profiles[selected];
  bool owns(int i) =>
      staffRole != 'doctor' || profiles[i]['doctor'] == staffDoctor;
  bool get billing => !careMode && ['owner', 'accountant'].contains(staffRole);
  bool get clinical => !careMode && ['owner', 'doctor'].contains(staffRole);
  final states = <String, PatientState>{};
  PatientState get current =>
      states.putIfAbsent(patientId, () => PatientState(profile));
  int get sessions => current.sessions;
  set sessions(int value) => current.sessions = value;
  int get totalSessions => profile['total'] as int;
  bool get checkedIn => current.checkedIn;
  set checkedIn(bool value) => current.checkedIn = value;
  bool get confirmed => current.confirmed;
  set confirmed(bool value) => current.confirmed = value;
  bool get acknowledged => current.acknowledged;
  set acknowledged(bool value) => current.acknowledged = value;
  String get appointment => current.appointment;
  set appointment(String value) => current.appointment = value;
  String get day => current.day;
  set day(String value) => current.day = value;
  String get note => current.note;
  set note(String value) => current.note = value;
  String get response => current.response;
  set response(String value) => current.response = value;
  String? get editingOrder => current.editingOrder;
  set editingOrder(String? value) => current.editingOrder = value;
  List<Map<String, dynamic>> get cart => current.cart;
  List<String> get updates => current.updates;
  final receipts = <String, int>{};
  int get paid => receipts[patientId] ?? 0;
  set paid(int value) => receipts[patientId] = value;
  final orders = <Map<String, dynamic>>[];
  String get name => patients[selected];
  String get patientId => profile['id'] as String;
  bool allows(String route) {
    if (careMode)
      return [
        'Lịch của tôi',
        'Chăm sóc tại nhà',
        'Gửi cập nhật',
        'Kế hoạch điều trị',
        'Ảnh tiến triển',
        'Đơn thuốc & tư vấn',
        'Hóa đơn',
        'Quyền riêng tư',
        'Hướng dẫn',
      ].contains(route);
    if (staffRole == 'owner') return true;
    if (staffRole == 'care')
      return [
        'Chăm sóc khách hàng',
        'Đặt lịch',
        'Chi tiết lịch',
        'Hướng dẫn',
      ].contains(route);
    if (staffRole == 'accountant')
      return ['Thu ngân', 'Hóa đơn', 'Hướng dẫn'].contains(route);
    return ![
      'Thu ngân',
      'Bác sĩ & phòng',
      'Dịch vụ',
      'Chăm sóc khách hàng',
    ].contains(route);
  }

  Future<void> load() async {
    products =
        (jsonDecode(await rootBundle.loadString('assets/products.json'))
                as List)
            .cast<Map<String, dynamic>>();
    profiles =
        (jsonDecode(await rootBundle.loadString('assets/patients.json'))
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

class PatientState {
  PatientState(Map<String, dynamic> profile)
    : sessions = profile['sessions'] as int,
      appointment = profile['appointment'] as String,
      day = profile['day'] as String;
  int sessions;
  String appointment, day;
  bool checkedIn = false, confirmed = false, acknowledged = false;
  String note = '', response = '', careNote = '', careStatus = 'Chưa liên hệ';
  String? editingOrder;
  final cart = <Map<String, dynamic>>[];
  final updates = <String>[];
  final escalations = <String>[];
}
