import 'package:flutter/material.dart';

import 'app_routes.dart';

/// Lets widgets above the Navigator (e.g. payment alerts) push routes.
final appNavigatorKey = GlobalKey<NavigatorState>();

extension AppNavigation on BuildContext {
  Future<void> openRoute(String route) => Navigator.of(this).pushNamed(route);

  Future<void> openFinance([int tab = 0]) =>
      Navigator.of(this).pushNamed(AppRoutes.finance, arguments: tab);
}
