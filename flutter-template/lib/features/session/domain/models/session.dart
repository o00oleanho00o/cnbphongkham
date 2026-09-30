import 'package:freezed_annotation/freezed_annotation.dart';

import '../../../../core/router/app_routes.dart';
import '../../../catalog/domain/models/patient_profile.dart';

part 'session.freezed.dart';

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
@freezed
abstract class Session with _$Session {
  const Session._();

  const factory Session({
    @Default(false) bool careMode,
    @Default('owner') String staffRole,
    @Default('BS. Tâm') String staffDoctor,
    @Default('BS. Tâm') String staffName,
    @Default(0) int staffSelected,
    @Default(0) int careSelected,
  }) = _Session;

  int get selected => careMode ? careSelected : staffSelected;
  bool get billing =>
      !careMode && (staffRole == 'owner' || staffRole == 'accountant');
  bool get clinical =>
      !careMode && (staffRole == 'owner' || staffRole == 'doctor');

  bool owns(PatientProfile profile) =>
      staffRole != 'doctor' || profile.doctor == staffDoctor;

  bool allows(String route) {
    if (careMode) return _careRoutes.contains(route);
    return switch (staffRole) {
      'owner' => true,
      'care' => _customerCareRoutes.contains(route),
      'accountant' => _accountantRoutes.contains(route),
      _ => !_doctorBlockedRoutes.contains(route),
    };
  }
}
