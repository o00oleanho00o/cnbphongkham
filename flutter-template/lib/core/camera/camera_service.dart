import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import 'captured_photo.dart';

part 'camera_service.g.dart';

/// A user-facing reason the camera could not be used.
class CameraFailure implements Exception {
  const CameraFailure(this.message);
  final String message;

  @override
  String toString() => message;
}

abstract interface class CameraService {
  /// Opens the camera; returns `null` when the user cancels.
  /// Throws [CameraFailure] when the device or platform cannot take photos.
  Future<CapturedPhoto?> capture();

  /// Removes a photo this service created; ignores any other path.
  Future<void> discard(CapturedPhoto photo);
}

/// Talks to `PemaCamera.kt` (Android) and `PemaCameraPlugin` (iOS) over the
/// `pema/camera` channel.
class NativeCameraService implements CameraService {
  const NativeCameraService();

  static const channel = MethodChannel('pema/camera');

  @override
  Future<CapturedPhoto?> capture() async {
    if (kIsWeb) {
      throw const CameraFailure(
        'Trình duyệt chưa hỗ trợ chụp ảnh. Hãy dùng app Pema trên điện thoại.',
      );
    }
    try {
      final value = await channel.invokeMapMethod<String, Object?>('capture');
      if (value == null) return null;
      return CapturedPhoto(
        path: value['path']! as String,
        width: value['width']! as int,
        height: value['height']! as int,
        bytes: value['bytes']! as int,
      );
    } on MissingPluginException {
      throw const CameraFailure('Thiết bị này chưa hỗ trợ chụp ảnh.');
    } on PlatformException catch (e) {
      throw CameraFailure(e.message ?? 'Không mở được camera.');
    }
  }

  @override
  Future<void> discard(CapturedPhoto photo) async {
    if (kIsWeb) return;
    try {
      await channel.invokeMethod<bool>('delete', {'path': photo.path});
    } on MissingPluginException {
      // Nothing was captured on this platform.
    }
  }
}

@Riverpod(keepAlive: true)
CameraService cameraService(Ref ref) => const NativeCameraService();
