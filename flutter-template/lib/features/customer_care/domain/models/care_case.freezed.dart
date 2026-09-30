// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'care_case.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$CareCase {

 PatientProfile get profile; String get status;
/// Create a copy of CareCase
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$CareCaseCopyWith<CareCase> get copyWith => _$CareCaseCopyWithImpl<CareCase>(this as CareCase, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as CareCase;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is CareCase&&(identical(other.profile, _this.profile) || other.profile == _this.profile)&&(identical(other.status, _this.status) || other.status == _this.status));
}


@override
int get hashCode {
  final _this = this as CareCase;
  return Object.hash(runtimeType,_this.profile,_this.status);
}

@override
String toString() {
  final _this = this as CareCase;
  return 'CareCase(profile: ${_this.profile}, status: ${_this.status})';
}


}

/// @nodoc
abstract mixin class $CareCaseCopyWith<$Res>  {
  factory $CareCaseCopyWith(CareCase value, $Res Function(CareCase) _then) = _$CareCaseCopyWithImpl;
@useResult
$Res call({
 PatientProfile profile, String status
});


$PatientProfileCopyWith<$Res> get profile;

}
/// @nodoc
class _$CareCaseCopyWithImpl<$Res>
    implements $CareCaseCopyWith<$Res> {
  _$CareCaseCopyWithImpl(this._self, this._then);

  final CareCase _self;
  final $Res Function(CareCase) _then;

/// Create a copy of CareCase
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? profile = null,Object? status = null,}) {
  return _then(CareCase(
profile: null == profile ? _self.profile : profile // ignore: cast_nullable_to_non_nullable
as PatientProfile,status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,
  ));
}
/// Create a copy of CareCase
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$PatientProfileCopyWith<$Res> get profile {
  
  return $PatientProfileCopyWith<$Res>(_self.profile, (value) {
    return _then(_self.copyWith(profile: value));
  });
}
}


/// Adds pattern-matching-related methods to [CareCase].
extension CareCasePatterns on CareCase {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _CareCase value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _CareCase() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _CareCase value)  $default,){
final _that = this;
switch (_that) {
case _CareCase():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _CareCase value)?  $default,){
final _that = this;
switch (_that) {
case _CareCase() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( PatientProfile profile,  String status)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _CareCase() when $default != null:
return $default(_that.profile,_that.status);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( PatientProfile profile,  String status)  $default,) {final _that = this;
switch (_that) {
case _CareCase():
return $default(_that.profile,_that.status);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( PatientProfile profile,  String status)?  $default,) {final _that = this;
switch (_that) {
case _CareCase() when $default != null:
return $default(_that.profile,_that.status);case _:
  return null;

}
}

}

/// @nodoc


class _CareCase extends CareCase {
  const _CareCase({required this.profile, this.status = careNotContacted}): super._();
  

@override final  PatientProfile profile;
@override@JsonKey() final  String status;

/// Create a copy of CareCase
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$CareCaseCopyWith<_CareCase> get copyWith => __$CareCaseCopyWithImpl<_CareCase>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _CareCase&&(identical(other.profile, profile) || other.profile == profile)&&(identical(other.status, status) || other.status == status));
}


@override
int get hashCode {
    return Object.hash(runtimeType,profile,status);
}

@override
String toString() {
    return 'CareCase(profile: $profile, status: $status)';
}


}

/// @nodoc
abstract mixin class _$CareCaseCopyWith<$Res> implements $CareCaseCopyWith<$Res> {
  factory _$CareCaseCopyWith(_CareCase value, $Res Function(_CareCase) _then) = __$CareCaseCopyWithImpl;
@override @useResult
$Res call({
 PatientProfile profile, String status
});


@override $PatientProfileCopyWith<$Res> get profile;

}
/// @nodoc
class __$CareCaseCopyWithImpl<$Res>
    implements _$CareCaseCopyWith<$Res> {
  __$CareCaseCopyWithImpl(this._self, this._then);

  final _CareCase _self;
  final $Res Function(_CareCase) _then;

/// Create a copy of CareCase
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? profile = null,Object? status = null,}) {
  return _then(_CareCase(
profile: null == profile ? _self.profile : profile // ignore: cast_nullable_to_non_nullable
as PatientProfile,status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,
  ));
}

/// Create a copy of CareCase
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$PatientProfileCopyWith<$Res> get profile {
  
  return $PatientProfileCopyWith<$Res>(_self.profile, (value) {
    return _then(_self.copyWith(profile: value));
  });
}
}

// dart format on
