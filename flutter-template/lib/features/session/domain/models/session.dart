import '../../../../core/router/app_routes.dart';

const _careRoutes = {
  AppRoutes.myAppointments,
  AppRoutes.homeCare,
  AppRoutes.sendUpdate,
  AppRoutes.treatmentPlan,
  AppRoutes.progressPhotos,
  AppRoutes.prescriptions,
  AppRoutes.invoices,
  AppRoutes.privacy,
  AppRoutes.guide,
};
const _customerCareRoutes = {
  AppRoutes.customerCare,
  AppRoutes.booking,
  AppRoutes.appointmentDetail,
  AppRoutes.guide,
};
const _accountantRoutes = {
  AppRoutes.cashier,
  AppRoutes.invoices,
  AppRoutes.guide,
};
const _doctorBlockedRoutes = {
  AppRoutes.cashier,
  AppRoutes.resources,
  AppRoutes.services,
  AppRoutes.customerCare,
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
