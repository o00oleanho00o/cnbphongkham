// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'finance_state.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$FinanceState {

 String get month; String get role; String get doctor; String get error;/// Null until the first load and right after a role switch.
 FinanceSnapshot? get data; bool get sending;
/// Create a copy of FinanceState
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$FinanceStateCopyWith<FinanceState> get copyWith => _$FinanceStateCopyWithImpl<FinanceState>(this as FinanceState, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as FinanceState;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is FinanceState&&(identical(other.month, _this.month) || other.month == _this.month)&&(identical(other.role, _this.role) || other.role == _this.role)&&(identical(other.doctor, _this.doctor) || other.doctor == _this.doctor)&&(identical(other.error, _this.error) || other.error == _this.error)&&(identical(other.data, _this.data) || other.data == _this.data)&&(identical(other.sending, _this.sending) || other.sending == _this.sending));
}


@override
int get hashCode {
  final _this = this as FinanceState;
  return Object.hash(runtimeType,_this.month,_this.role,_this.doctor,_this.error,_this.data,_this.sending);
}

@override
String toString() {
  final _this = this as FinanceState;
  return 'FinanceState(month: ${_this.month}, role: ${_this.role}, doctor: ${_this.doctor}, error: ${_this.error}, data: ${_this.data}, sending: ${_this.sending})';
}


}

/// @nodoc
abstract mixin class $FinanceStateCopyWith<$Res>  {
  factory $FinanceStateCopyWith(FinanceState value, $Res Function(FinanceState) _then) = _$FinanceStateCopyWithImpl;
@useResult
$Res call({
 String month, String role, String doctor, String error, FinanceSnapshot? data, bool sending
});


$FinanceSnapshotCopyWith<$Res>? get data;

}
/// @nodoc
class _$FinanceStateCopyWithImpl<$Res>
    implements $FinanceStateCopyWith<$Res> {
  _$FinanceStateCopyWithImpl(this._self, this._then);

  final FinanceState _self;
  final $Res Function(FinanceState) _then;

/// Create a copy of FinanceState
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? month = null,Object? role = null,Object? doctor = null,Object? error = null,Object? data = freezed,Object? sending = null,}) {
  return _then(FinanceState(
month: null == month ? _self.month : month // ignore: cast_nullable_to_non_nullable
as String,role: null == role ? _self.role : role // ignore: cast_nullable_to_non_nullable
as String,doctor: null == doctor ? _self.doctor : doctor // ignore: cast_nullable_to_non_nullable
as String,error: null == error ? _self.error : error // ignore: cast_nullable_to_non_nullable
as String,data: freezed == data ? _self.data : data // ignore: cast_nullable_to_non_nullable
as FinanceSnapshot?,sending: null == sending ? _self.sending : sending // ignore: cast_nullable_to_non_nullable
as bool,
  ));
}
/// Create a copy of FinanceState
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$FinanceSnapshotCopyWith<$Res>? get data {
    if (_self.data == null) {
    return null;
  }

  return $FinanceSnapshotCopyWith<$Res>(_self.data!, (value) {
    return _then(_self.copyWith(data: value));
  });
}
}


/// Adds pattern-matching-related methods to [FinanceState].
extension FinanceStatePatterns on FinanceState {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _FinanceState value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _FinanceState() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _FinanceState value)  $default,){
final _that = this;
switch (_that) {
case _FinanceState():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _FinanceState value)?  $default,){
final _that = this;
switch (_that) {
case _FinanceState() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String month,  String role,  String doctor,  String error,  FinanceSnapshot? data,  bool sending)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _FinanceState() when $default != null:
return $default(_that.month,_that.role,_that.doctor,_that.error,_that.data,_that.sending);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String month,  String role,  String doctor,  String error,  FinanceSnapshot? data,  bool sending)  $default,) {final _that = this;
switch (_that) {
case _FinanceState():
return $default(_that.month,_that.role,_that.doctor,_that.error,_that.data,_that.sending);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String month,  String role,  String doctor,  String error,  FinanceSnapshot? data,  bool sending)?  $default,) {final _that = this;
switch (_that) {
case _FinanceState() when $default != null:
return $default(_that.month,_that.role,_that.doctor,_that.error,_that.data,_that.sending);case _:
  return null;

}
}

}

/// @nodoc


class _FinanceState extends FinanceState {
  const _FinanceState({required this.month, this.role = 'owner', this.doctor = 'D0', this.error = '', this.data, this.sending = false}): super._();
  

@override final  String month;
@override@JsonKey() final  String role;
@override@JsonKey() final  String doctor;
@override@JsonKey() final  String error;
/// Null until the first load and right after a role switch.
@override final  FinanceSnapshot? data;
@override@JsonKey() final  bool sending;

/// Create a copy of FinanceState
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$FinanceStateCopyWith<_FinanceState> get copyWith => __$FinanceStateCopyWithImpl<_FinanceState>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _FinanceState&&(identical(other.month, month) || other.month == month)&&(identical(other.role, role) || other.role == role)&&(identical(other.doctor, doctor) || other.doctor == doctor)&&(identical(other.error, error) || other.error == error)&&(identical(other.data, data) || other.data == data)&&(identical(other.sending, sending) || other.sending == sending));
}


@override
int get hashCode {
    return Object.hash(runtimeType,month,role,doctor,error,data,sending);
}

@override
String toString() {
    return 'FinanceState(month: $month, role: $role, doctor: $doctor, error: $error, data: $data, sending: $sending)';
}


}

/// @nodoc
abstract mixin class _$FinanceStateCopyWith<$Res> implements $FinanceStateCopyWith<$Res> {
  factory _$FinanceStateCopyWith(_FinanceState value, $Res Function(_FinanceState) _then) = __$FinanceStateCopyWithImpl;
@override @useResult
$Res call({
 String month, String role, String doctor, String error, FinanceSnapshot? data, bool sending
});


@override $FinanceSnapshotCopyWith<$Res>? get data;

}
/// @nodoc
class __$FinanceStateCopyWithImpl<$Res>
    implements _$FinanceStateCopyWith<$Res> {
  __$FinanceStateCopyWithImpl(this._self, this._then);

  final _FinanceState _self;
  final $Res Function(_FinanceState) _then;

/// Create a copy of FinanceState
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? month = null,Object? role = null,Object? doctor = null,Object? error = null,Object? data = freezed,Object? sending = null,}) {
  return _then(_FinanceState(
month: null == month ? _self.month : month // ignore: cast_nullable_to_non_nullable
as String,role: null == role ? _self.role : role // ignore: cast_nullable_to_non_nullable
as String,doctor: null == doctor ? _self.doctor : doctor // ignore: cast_nullable_to_non_nullable
as String,error: null == error ? _self.error : error // ignore: cast_nullable_to_non_nullable
as String,data: freezed == data ? _self.data : data // ignore: cast_nullable_to_non_nullable
as FinanceSnapshot?,sending: null == sending ? _self.sending : sending // ignore: cast_nullable_to_non_nullable
as bool,
  ));
}

/// Create a copy of FinanceState
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$FinanceSnapshotCopyWith<$Res>? get data {
    if (_self.data == null) {
    return null;
  }

  return $FinanceSnapshotCopyWith<$Res>(_self.data!, (value) {
    return _then(_self.copyWith(data: value));
  });
}
}

// dart format on
