import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:pema_native_template/state/catalog.dart';

ProviderContainer clinicContainer(Catalog catalog) => ProviderContainer.test(
  overrides: [catalogProvider.overrideWithValue(catalog)],
);

Widget scoped(ProviderContainer container, Widget child) =>
    UncontrolledProviderScope(container: container, child: child);
