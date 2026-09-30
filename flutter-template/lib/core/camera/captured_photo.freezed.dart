// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'captured_photo.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$CapturedPhoto {

 String get path; int get width; int get height; int get bytes;
/// Create a copy of CapturedPhoto
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$CapturedPhotoCopyWith<CapturedPhoto> get copyWith => _$CapturedPhotoCopyWithImpl<CapturedPhoto>(this as CapturedPhoto, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as CapturedPhoto;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is CapturedPhoto&&(identical(other.path, _this.path) || other.path == _this.path)&&(identical(other.width, _this.width) || other.width == _this.width)&&(identical(other.height, _this.height) || other.height == _this.height)&&(identical(other.bytes, _this.bytes) || other.bytes == _this.bytes));
}


@override
int get hashCode {
  final _this = this as CapturedPhoto;
  return Object.hash(runtimeType,_this.path,_this.width,_this.height,_this.bytes);
}

@override
String toString() {
  final _this = this as CapturedPhoto;
  return 'CapturedPhoto(path: ${_this.path}, width: ${_this.width}, height: ${_this.height}, bytes: ${_this.bytes})';
}


}

/// @nodoc
abstract mixin class $CapturedPhotoCopyWith<$Res>  {
  factory $CapturedPhotoCopyWith(CapturedPhoto value, $Res Function(CapturedPhoto) _then) = _$CapturedPhotoCopyWithImpl;
@useResult
$Res call({
 String path, int width, int height, int bytes
});




}
/// @nodoc
class _$CapturedPhotoCopyWithImpl<$Res>
    implements $CapturedPhotoCopyWith<$Res> {
  _$CapturedPhotoCopyWithImpl(this._self, this._then);

  final CapturedPhoto _self;
  final $Res Function(CapturedPhoto) _then;

/// Create a copy of CapturedPhoto
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? path = null,Object? width = null,Object? height = null,Object? bytes = null,}) {
  return _then(CapturedPhoto(
path: null == path ? _self.path : path // ignore: cast_nullable_to_non_nullable
as String,width: null == width ? _self.width : width // ignore: cast_nullable_to_non_nullable
as int,height: null == height ? _self.height : height // ignore: cast_nullable_to_non_nullable
as int,bytes: null == bytes ? _self.bytes : bytes // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [CapturedPhoto].
extension CapturedPhotoPatterns on CapturedPhoto {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _CapturedPhoto value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _CapturedPhoto() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _CapturedPhoto value)  $default,){
final _that = this;
switch (_that) {
case _CapturedPhoto():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _CapturedPhoto value)?  $default,){
final _that = this;
switch (_that) {
case _CapturedPhoto() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String path,  int width,  int height,  int bytes)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _CapturedPhoto() when $default != null:
return $default(_that.path,_that.width,_that.height,_that.bytes);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String path,  int width,  int height,  int bytes)  $default,) {final _that = this;
switch (_that) {
case _CapturedPhoto():
return $default(_that.path,_that.width,_that.height,_that.bytes);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String path,  int width,  int height,  int bytes)?  $default,) {final _that = this;
switch (_that) {
case _CapturedPhoto() when $default != null:
return $default(_that.path,_that.width,_that.height,_that.bytes);case _:
  return null;

}
}

}

/// @nodoc


class _CapturedPhoto implements CapturedPhoto {
  const _CapturedPhoto({required this.path, required this.width, required this.height, required this.bytes});
  

@override final  String path;
@override final  int width;
@override final  int height;
@override final  int bytes;

/// Create a copy of CapturedPhoto
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$CapturedPhotoCopyWith<_CapturedPhoto> get copyWith => __$CapturedPhotoCopyWithImpl<_CapturedPhoto>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _CapturedPhoto&&(identical(other.path, path) || other.path == path)&&(identical(other.width, width) || other.width == width)&&(identical(other.height, height) || other.height == height)&&(identical(other.bytes, bytes) || other.bytes == bytes));
}


@override
int get hashCode {
    return Object.hash(runtimeType,path,width,height,bytes);
}

@override
String toString() {
    return 'CapturedPhoto(path: $path, width: $width, height: $height, bytes: $bytes)';
}


}

/// @nodoc
abstract mixin class _$CapturedPhotoCopyWith<$Res> implements $CapturedPhotoCopyWith<$Res> {
  factory _$CapturedPhotoCopyWith(_CapturedPhoto value, $Res Function(_CapturedPhoto) _then) = __$CapturedPhotoCopyWithImpl;
@override @useResult
$Res call({
 String path, int width, int height, int bytes
});




}
/// @nodoc
class __$CapturedPhotoCopyWithImpl<$Res>
    implements _$CapturedPhotoCopyWith<$Res> {
  __$CapturedPhotoCopyWithImpl(this._self, this._then);

  final _CapturedPhoto _self;
  final $Res Function(_CapturedPhoto) _then;

/// Create a copy of CapturedPhoto
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? path = null,Object? width = null,Object? height = null,Object? bytes = null,}) {
  return _then(_CapturedPhoto(
path: null == path ? _self.path : path // ignore: cast_nullable_to_non_nullable
as String,width: null == width ? _self.width : width // ignore: cast_nullable_to_non_nullable
as int,height: null == height ? _self.height : height // ignore: cast_nullable_to_non_nullable
as int,bytes: null == bytes ? _self.bytes : bytes // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}

// dart format on
