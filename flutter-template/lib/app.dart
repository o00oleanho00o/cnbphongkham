import 'package:flutter/material.dart';

import 'core/router/app_navigation.dart';
import 'core/router/app_router.dart';
import 'core/theme/app_theme.dart';
import 'features/finance/presentation/widgets/payment_alerts.dart';
import 'features/workspace/presentation/screens/workspace_screen.dart';

class PemaApp extends StatelessWidget {
  const PemaApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    navigatorKey: appNavigatorKey,
    builder: (context, child) => PaymentAlerts(child: child!),
    debugShowCheckedModeBanner: false,
    title: 'Pema • Native review',
    theme: AppTheme.light,
    onGenerateRoute: AppRouter.onGenerateRoute,
    // Always start at Workspace, whatever URL the web build was reloaded on.
    onGenerateInitialRoutes: (_) => [
      MaterialPageRoute<void>(builder: (_) => const WorkspaceScreen()),
    ],
  );
}
