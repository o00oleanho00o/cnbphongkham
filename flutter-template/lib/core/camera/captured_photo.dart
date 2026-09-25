import 'package:freezed_annotation/freezed_annotation.dart';

part 'captured_photo.freezed.dart';

/// A JPEG taken with the native camera: upright, at most 1600 px on the long
/// edge and without EXIF/GPS metadata. Lives in the app cache.
@freezed
abstract class CapturedPhoto with _$CapturedPhoto {
  const factory CapturedPhoto({
    required String path,
    required int width,
    required int height,
    required int bytes,
  }) = _CapturedPhoto;
}
