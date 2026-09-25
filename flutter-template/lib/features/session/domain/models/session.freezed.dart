// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'session.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$Session {

 bool get careMode; String get staffRole; String get staffDoctor; String get staffName; int get staffSelected; int get careSelected;
/// Create a copy of Session
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$SessionCopyWith<Session> get copyWith => _$SessionCopyWithImpl<Session>(this as Session, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as Session;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is Session&&(identical(other.careMode, _this.careMode) || other.careMode == _this.careMode)&&(identical(other.staffRole, _this.staffRole) || other.staffRole == _this.staffRole)&&(identical(other.staffDoctor, _this.staffDoctor) || other.staffDoctor == _this.staffDoctor)&&(identical(other.staffName, _this.staffName) || other.staffName == _this.staffName)&&(identical(other.staffSelected, _this.staffSelected) || other.staffSelected == _this.staffSelected)&&(identical(other.careSelected, _this.careSelected) || other.careSelected == _this.careSelected));
}


@override
int get hashCode {
  final _this = this as Session;
  return Object.hash(runtimeType,_this.careMode,_this.staffRole,_this.staffDoctor,_this.staffName,_this.staffSelected,_this.careSelected);
}

@override
String toString() {
  final _this = this as Session;
  return 'Session(careMode: ${_this.careMode}, staffRole: ${_this.staffRole}, staffDoctor: ${_this.staffDoctor}, staffName: ${_this.staffName}, staffSelected: ${_this.staffSelected}, careSelected: ${_this.careSelected})';
}


}

/// @nodoc
abstract mixin class $SessionCopyWith<$Res>  {
  factory $SessionCopyWith(Session value, $Res Function(Session) _then) = _$SessionCopyWithImpl;
@useResult
$Res call({
 bool careMode, String staffRole, String staffDoctor, String staffName, int staffSelected, int careSelected
});




}
/// @nodoc
class _$SessionCopyWithImpl<$Res>
    implements $SessionCopyWith<$Res> {
  _$SessionCopyWithImpl(this._self, this._then);

  final Session _self;
  final $Res Function(Session) _then;

/// Create a copy of Session
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? careMode = null,Object? staffRole = null,Object? staffDoctor = null,Object? staffName = null,Object? staffSelected = null,Object? careSelected = null,}) {
  return _then(Session(
careMode: null == careMode ? _self.careMode : careMode // ignore: cast_nullable_to_non_nullable
as bool,staffRole: null == staffRole ? _self.staffRole : staffRole // ignore: cast_nullable_to_non_nullable
as String,staffDoctor: null == staffDoctor ? _self.staffDoctor : staffDoctor // ignore: cast_nullable_to_non_nullable
as String,staffName: null == staffName ? _self.staffName : staffName // ignore: cast_nullable_to_non_nullable
as String,staffSelected: null == staffSelected ? _self.staffSelected : staffSelected // ignore: cast_nullable_to_non_nullable
as int,careSelected: null == careSelected ? _self.careSelected : careSelected // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [Session].
extension SessionPatterns on Session {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _Session value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _Session() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _Session value)  $default,){
final _that = this;
switch (_that) {
case _Session():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _Session value)?  $default,){
final _that = this;
switch (_that) {
case _Session() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( bool careMode,  String staffRole,  String staffDoctor,  String staffName,  int staffSelected,  int careSelected)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _Session() when $default != null:
return $default(_that.careMode,_that.staffRole,_that.staffDoctor,_that.staffName,_that.staffSelected,_that.careSelected);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( bool careMode,  String staffRole,  String staffDoctor,  String staffName,  int staffSelected,  int careSelected)  $default,) {final _that = this;
switch (_that) {
case _Session():
return $default(_that.careMode,_that.staffRole,_that.staffDoctor,_that.staffName,_that.staffSelected,_that.careSelected);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( bool careMode,  String staffRole,  String staffDoctor,  String staffName,  int staffSelected,  int careSelected)?  $default,) {final _that = this;
switch (_that) {
case _Session() when $default != null:
return $default(_that.careMode,_that.staffRole,_that.staffDoctor,_that.staffName,_that.staffSelected,_that.careSelected);case _:
  return null;

}
}

}

/// @nodoc


class _Session extends Session {
  const _Session({this.careMode = false, this.staffRole = 'owner', this.staffDoctor = 'BS. Tâm', this.staffName = 'BS. Tâm', this.staffSelected = 0, this.careSelected = 0}): super._();
  

@override@JsonKey() final  bool careMode;
@override@JsonKey() final  String staffRole;
@override@JsonKey() final  String staffDoctor;
@override@JsonKey() final  String staffName;
@override@JsonKey() final  int staffSelected;
@override@JsonKey() final  int careSelected;

/// Create a copy of Session
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$SessionCopyWith<_Session> get copyWith => __$SessionCopyWithImpl<_Session>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _Session&&(identical(other.careMode, careMode) || other.careMode == careMode)&&(identical(other.staffRole, staffRole) || other.staffRole == staffRole)&&(identical(other.staffDoctor, staffDoctor) || other.staffDoctor == staffDoctor)&&(identical(other.staffName, staffName) || other.staffName == staffName)&&(identical(other.staffSelected, staffSelected) || other.staffSelected == staffSelected)&&(identical(other.careSelected, careSelected) || other.careSelected == careSelected));
}


@override
int get hashCode {
    return Object.hash(runtimeType,careMode,staffRole,staffDoctor,staffName,staffSelected,careSelected);
}

@override
String toString() {
    return 'Session(careMode: $careMode, staffRole: $staffRole, staffDoctor: $staffDoctor, staffName: $staffName, staffSelected: $staffSelected, careSelected: $careSelected)';
}


}

/// @nodoc
abstract mixin class _$SessionCopyWith<$Res> implements $SessionCopyWith<$Res> {
  factory _$SessionCopyWith(_Session value, $Res Function(_Session) _then) = __$SessionCopyWithImpl;
@override @useResult
$Res call({
 bool careMode, String staffRole, String staffDoctor, String staffName, int staffSelected, int careSelected
});




}
/// @nodoc
class __$SessionCopyWithImpl<$Res>
    implements _$SessionCopyWith<$Res> {
  __$SessionCopyWithImpl(this._self, this._then);

  final _Session _self;
  final $Res Function(_Session) _then;

/// Create a copy of Session
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? careMode = null,Object? staffRole = null,Object? staffDoctor = null,Object? staffName = null,Object? staffSelected = null,Object? careSelected = null,}) {
  return _then(_Session(
careMode: null == careMode ? _self.careMode : careMode // ignore: cast_nullable_to_non_nullable
as bool,staffRole: null == staffRole ? _self.staffRole : staffRole // ignore: cast_nullable_to_non_nullable
as String,staffDoctor: null == staffDoctor ? _self.staffDoctor : staffDoctor // ignore: cast_nullable_to_non_nullable
as String,staffName: null == staffName ? _self.staffName : staffName // ignore: cast_nullable_to_non_nullable
as String,staffSelected: null == staffSelected ? _self.staffSelected : staffSelected // ignore: cast_nullable_to_non_nullable
as int,careSelected: null == careSelected ? _self.careSelected : careSelected // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}

// dart format on
