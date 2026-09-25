import 'cart_line.dart';

const _keep = Object();

/// Session-only clinical, schedule, care and cart state for one patient.
class PatientState {
  const PatientState({
    required this.sessions,
    required this.appointment,
    required this.day,
    this.checkedIn = false,
    this.confirmed = false,
    this.acknowledged = false,
    this.note = '',
    this.response = '',
    this.careNote = '',
    this.careStatus = 'Chưa liên hệ',
    this.editingOrder,
    this.cart = const [],
    this.updates = const [],
    this.escalations = const [],
  });

  PatientState.fromProfile(Map<String, dynamic> profile)
    : this(
        sessions: profile['sessions'] as int,
        appointment: profile['appointment'] as String,
        day: profile['day'] as String,
      );

  final int sessions;
  final String appointment, day;
  final bool checkedIn, confirmed, acknowledged;
  final String note, response, careNote, careStatus;
  final String? editingOrder;
  final List<CartLine> cart;
  final List<String> updates;

  /// Internal CSKH hand-offs; never shown in Care.
  final List<String> escalations;

  int get cartTotal => cart.fold(0, (sum, line) => sum + line.total);
  bool get cartReady =>
      cart.isNotEmpty &&
      cart.every((l) => l.route != 'UNRESOLVED' && l.usage.trim().isNotEmpty);

  PatientState copyWith({
    int? sessions,
    String? appointment,
    String? day,
    bool? checkedIn,
    bool? confirmed,
    bool? acknowledged,
    String? note,
    String? response,
    String? careNote,
    String? careStatus,
    Object? editingOrder = _keep,
    List<CartLine>? cart,
    List<String>? updates,
    List<String>? escalations,
  }) => PatientState(
    sessions: sessions ?? this.sessions,
    appointment: appointment ?? this.appointment,
    day: day ?? this.day,
    checkedIn: checkedIn ?? this.checkedIn,
    confirmed: confirmed ?? this.confirmed,
    acknowledged: acknowledged ?? this.acknowledged,
    note: note ?? this.note,
    response: response ?? this.response,
    careNote: careNote ?? this.careNote,
    careStatus: careStatus ?? this.careStatus,
    editingOrder: identical(editingOrder, _keep)
        ? this.editingOrder
        : editingOrder as String?,
    cart: cart ?? this.cart,
    updates: updates ?? this.updates,
    escalations: escalations ?? this.escalations,
  );
}
