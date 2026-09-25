import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/aftercare/presentation/screens/follow_up_reply_screen.dart';
import '../../features/aftercare/presentation/screens/home_care_screen.dart';
import '../../features/aftercare/presentation/screens/privacy_screen.dart';
import '../../features/aftercare/presentation/screens/send_update_screen.dart';
import '../../features/billing/presentation/screens/cashier_screen.dart';
import '../../features/catalog/presentation/providers/catalog_provider.dart';
import '../../features/customer_care/presentation/screens/customer_care_contact_screen.dart';
import '../../features/finance/presentation/screens/finance_screen.dart';
import '../../features/orders/presentation/screens/a5_print_preview_screen.dart';
import '../../features/orders/presentation/screens/order_review_screen.dart';
import '../../features/orders/presentation/screens/prescriptions_screen.dart';
import '../../features/orders/presentation/screens/quick_order_screen.dart';
import '../../features/patients/presentation/screens/ask_pema_screen.dart';
import '../../features/patients/presentation/screens/consultation_screen.dart';
import '../../features/patients/presentation/screens/patient_360_screen.dart';
import '../../features/patients/presentation/screens/progress_photos_screen.dart';
import '../../features/patients/presentation/screens/treatment_plan_screen.dart';
import '../../features/patients/presentation/screens/treatment_session_screen.dart';
import '../../features/schedule/presentation/screens/appointment_detail_screen.dart';
import '../../features/schedule/presentation/screens/booking_screen.dart';
import '../../features/schedule/presentation/screens/resources_screen.dart';
import '../../features/schedule/presentation/screens/services_screen.dart';
import '../../features/session/presentation/providers/session_provider.dart';
import '../../features/workspace/presentation/screens/guide_screen.dart';
import '../widgets/detail_scaffold.dart';
import '../widgets/pema_blocks.dart';
import 'app_routes.dart';

/// Composition root for navigation: maps route names to feature screens.
abstract final class AppRouter {
  /// Routes are built without `settings` on purpose: a named route would be
  /// reported to the browser URL on web, and reloading that URL would open a
  /// task screen with no Workspace underneath.
  static Route<void> onGenerateRoute(RouteSettings settings) {
    final name = settings.name ?? AppRoutes.guide;
    if (name == AppRoutes.finance) {
      final tab = settings.arguments as int? ?? 0;
      return MaterialPageRoute<void>(
        builder: (_) => Consumer(
          builder: (_, ref, _) => FinanceScreen(
            initialTab: tab,
            lockRole: true,
            patientIds: ref.read(catalogProvider).patientIds,
          ),
        ),
      );
    }
    return MaterialPageRoute<void>(builder: (_) => page(name));
  }

  /// Task screen for [route], guarded by the current workspace role.
  static Widget page(String route) =>
      _RouteGuard(route: route, child: _screen(route));

  static Widget _screen(String route) => switch (route) {
    AppRoutes.customerCare => const CustomerCareContactScreen(),
    AppRoutes.patient360 => const Patient360Screen(),
    AppRoutes.consultation => const ConsultationScreen(),
    AppRoutes.treatmentPlan => const TreatmentPlanScreen(),
    AppRoutes.treatmentSession => const TreatmentSessionScreen(),
    AppRoutes.progressPhotos => const ProgressPhotosScreen(),
    AppRoutes.askPema => const AskPemaScreen(),
    AppRoutes.quickOrder => const QuickOrderScreen(),
    AppRoutes.orderReview => const OrderReviewScreen(),
    AppRoutes.prescriptions => const PrescriptionsScreen(),
    AppRoutes.a5Print => const A5PrintPreviewScreen(),
    AppRoutes.invoices || AppRoutes.cashier => CashierScreen(route: route),
    AppRoutes.booking => const BookingScreen(),
    AppRoutes.appointmentDetail ||
    AppRoutes.myAppointments => AppointmentDetailScreen(route: route),
    AppRoutes.services => const ServicesScreen(),
    AppRoutes.resources => const ResourcesScreen(),
    AppRoutes.homeCare => const HomeCareScreen(),
    AppRoutes.sendUpdate => const SendUpdateScreen(),
    AppRoutes.followUpReply => const FollowUpReplyScreen(),
    AppRoutes.privacy => const PrivacyScreen(),
    _ => GuideScreen(route: route),
  };
}

class _RouteGuard extends ConsumerWidget {
  const _RouteGuard({required this.route, required this.child});

  final String route;
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(sessionProvider).allows(route)) return child;
    return DetailScaffold(
      title: route,
      children: [
        notice(
          'Tác vụ không thuộc không gian hiện tại. Quay lại để chọn đúng công việc.',
        ),
      ],
    );
  }
}
