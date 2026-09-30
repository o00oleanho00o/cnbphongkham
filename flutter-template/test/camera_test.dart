import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pema_native_template/core/camera/camera_service.dart';
import 'package:pema_native_template/core/camera/captured_photo.dart';
import 'package:pema_native_template/core/router/app_router.dart';
import 'package:pema_native_template/core/router/app_routes.dart';
import 'package:pema_native_template/features/catalog/presentation/providers/catalog_provider.dart';
import 'package:pema_native_template/features/patients/presentation/providers/patients_provider.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'support.dart';

class FakeCamera implements CameraService {
  FakeCamera(this.results);
  final List<Object?> results;
  final discarded = <String>[];

  @override
  Future<CapturedPhoto?> capture() async {
    final next = results.removeAt(0);
    if (next is CameraFailure) throw next;
    return next as CapturedPhoto?;
  }

  @override
  Future<void> discard(CapturedPhoto photo) async => discarded.add(photo.path);
}

CapturedPhoto photo(String name) => CapturedPhoto(
  path: '/cache/photos/$name.jpg',
  width: 1200,
  height: 1600,
  bytes: 240000,
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  tearDown(
    () => messenger.setMockMethodCallHandler(NativeCameraService.channel, null),
  );

  group('NativeCameraService', () {
    test('maps the native result to a photo', () async {
      messenger.setMockMethodCallHandler(NativeCameraService.channel, (
        call,
      ) async {
        expect(call.method, 'capture');
        return {'path': '/c/p.jpg', 'width': 1200, 'height': 1600, 'bytes': 9};
      });
      expect(
        await const NativeCameraService().capture(),
        const CapturedPhoto(
          path: '/c/p.jpg',
          width: 1200,
          height: 1600,
          bytes: 9,
        ),
      );
    });

    test('cancel returns null', () async {
      messenger.setMockMethodCallHandler(
        NativeCameraService.channel,
        (call) async => null,
      );
      expect(await const NativeCameraService().capture(), isNull);
    });

    test('native errors become a readable CameraFailure', () async {
      messenger.setMockMethodCallHandler(
        NativeCameraService.channel,
        (call) async => throw PlatformException(
          code: 'no_camera',
          message: 'Thiết bị không có ứng dụng camera',
        ),
      );
      expect(
        const NativeCameraService().capture(),
        throwsA(
          isA<CameraFailure>().having(
            (e) => e.message,
            'message',
            'Thiết bị không có ứng dụng camera',
          ),
        ),
      );
    });

    test('a platform without the channel reports unsupported', () {
      expect(
        const NativeCameraService().capture(),
        throwsA(isA<CameraFailure>()),
      );
    });
  });

  Future<(ProviderContainer, FakeCamera)> pumpSendUpdate(
    WidgetTester tester,
    List<Object?> results,
  ) async {
    tester.view.physicalSize = const Size(390, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final camera = FakeCamera(results);
    final catalog = (await tester.runAsync(loadCatalog))!;
    final c = ProviderContainer.test(
      overrides: [
        catalogProvider.overrideWithValue(catalog),
        cameraServiceProvider.overrideWithValue(camera),
      ],
    );
    await tester.pumpWidget(
      scoped(
        c,
        MaterialApp(
          onGenerateRoute: AppRouter.onGenerateRoute,
          home: AppRouter.page(AppRoutes.sendUpdate),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return (c, camera);
  }

  testWidgets('captured photo needs consent and is attached to the update', (
    tester,
  ) async {
    final (c, camera) = await pumpSendUpdate(tester, [photo('a'), photo('b')]);
    await tester.enterText(find.byType(TextField), 'Da đỡ đỏ');
    await tester.tap(find.text('Chụp ảnh tiến triển'));
    await tester.pumpAndSettle();
    expect(find.text('Ảnh vừa chụp'), findsOneWidget);
    FilledButton send() => tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Gửi cập nhật'),
    );
    expect(send().onPressed, isNull);

    await tester.tap(find.text('Chụp lại'));
    await tester.pumpAndSettle();
    expect(camera.discarded, ['/cache/photos/a.jpg']);

    await tester.tap(find.byType(CheckboxListTile));
    await tester.pump();
    expect(send().onPressed, isNotNull);
    await tester.tap(find.widgetWithText(FilledButton, 'Gửi cập nhật'));
    await tester.pumpAndSettle();
    expect(c.read(currentPatientProvider).photos, ['/cache/photos/b.jpg']);
    expect(c.read(currentPatientProvider).updates, ['Da đỡ đỏ']);
    expect(camera.discarded, ['/cache/photos/a.jpg']);
    expect(tester.takeException(), isNull);
  });

  testWidgets('camera failure is shown and nothing is attached', (
    tester,
  ) async {
    final (c, _) = await pumpSendUpdate(tester, [
      const CameraFailure('Thiết bị này chưa hỗ trợ chụp ảnh.'),
    ]);
    await tester.tap(find.text('Chụp ảnh tiến triển'));
    await tester.pump();
    expect(find.text('Thiết bị này chưa hỗ trợ chụp ảnh.'), findsOneWidget);
    expect(find.text('Ảnh vừa chụp'), findsNothing);
    expect(c.read(currentPatientProvider).photos, isEmpty);
  });

  testWidgets('leaving without sending discards the photo', (tester) async {
    final (_, camera) = await pumpSendUpdate(tester, [photo('a')]);
    await tester.tap(find.text('Chụp ảnh tiến triển'));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox());
    expect(camera.discarded, ['/cache/photos/a.jpg']);
  });
}
