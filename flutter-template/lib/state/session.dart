import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'catalog.dart';

part 'session.g.dart';

const _careRoutes = {
  'Lịch của tôi',
  'Chăm sóc tại nhà',
  'Gửi cập nhật',
  'Kế hoạch điều trị',
  'Ảnh tiến triển',
  'Đơn thuốc & tư vấn',
  'Hóa đơn',
  'Quyền riêng tư',
  'Hướng dẫn',
};
const _customerCareRoutes = {
  'Chăm sóc khách hàng',
  'Đặt lịch',
  'Chi tiết lịch',
  'Hướng dẫn',
};
const _accountantRoutes = {'Thu ngân', 'Hóa đơn', 'Hướng dẫn'};
const _doctorBlockedRoutes = {
  'Thu ngân',
  'Bác sĩ & phòng',
  'Dịch vụ',
  'Chăm sóc khách hàng',
};

/// Demo workspace switch; not authentication or RBAC.
class Session {
  const Session({
    this.careMode = false,
    this.staffRole = 'owner',
    this.staffDoctor = 'BS. Tâm',
    this.staffName = 'BS. Tâm',
    this.staffSelected = 0,
    this.careSelected = 0,
  });

  final bool careMode;
  final String staffRole, staffDoctor, staffName;
  final int staffSelected, careSelected;

  int get selected => careMode ? careSelected : staffSelected;
  bool get billing =>
      !careMode && (staffRole == 'owner' || staffRole == 'accountant');
  bool get clinical =>
      !careMode && (staffRole == 'owner' || staffRole == 'doctor');

  bool owns(Map<String, dynamic> profile) =>
      staffRole != 'doctor' || profile['doctor'] == staffDoctor;

  bool allows(String route) {
    if (careMode) return _careRoutes.contains(route);
    return switch (staffRole) {
      'owner' => true,
      'care' => _customerCareRoutes.contains(route),
      'accountant' => _accountantRoutes.contains(route),
      _ => !_doctorBlockedRoutes.contains(route),
    };
  }

  Session copyWith({
    bool? careMode,
    String? staffRole,
    String? staffDoctor,
    String? staffName,
    int? staffSelected,
    int? careSelected,
  }) => Session(
    careMode: careMode ?? this.careMode,
    staffRole: staffRole ?? this.staffRole,
    staffDoctor: staffDoctor ?? this.staffDoctor,
    staffName: staffName ?? this.staffName,
    staffSelected: staffSelected ?? this.staffSelected,
    careSelected: careSelected ?? this.careSelected,
  );
}

@Riverpod(keepAlive: true)
class SessionNotifier extends _$SessionNotifier {
  @override
  Session build() => const Session();

  void select(int index) => state = state.careMode
      ? state.copyWith(careSelected: index)
      : state.copyWith(staffSelected: index);

  void enterCare() => state = state.copyWith(careMode: true);

  void enterStaff(String role, String name) {
    var next = state.copyWith(
      careMode: false,
      staffRole: role,
      staffName: name,
      staffDoctor: name,
    );
    final profiles = ref.read(catalogProvider).profiles;
    if (!next.owns(profiles[next.staffSelected])) {
      next = next.copyWith(
        staffSelected: profiles.indexWhere(
          (p) => p['doctor'] == next.staffDoctor,
        ),
      );
    }
    state = next;
  }
}

@riverpod
Map<String, dynamic> selectedProfile(Ref ref) {
  final index = ref.watch(sessionProvider.select((s) => s.selected));
  return ref.watch(catalogProvider).profiles[index];
}

@riverpod
String selectedPatientId(Ref ref) =>
    ref.watch(selectedProfileProvider)['id'] as String;
