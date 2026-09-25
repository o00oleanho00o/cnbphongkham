// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'patient_state.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$PatientState {

 int get sessions; String get appointment; String get day; bool get checkedIn; bool get confirmed; bool get acknowledged; String get note; String get response; String get careNote; String get careStatus; String? get editingOrder; List<CartLine> get cart; List<String> get updates;/// Internal CSKH hand-offs; never shown in Care.
 List<String> get escalations;
/// Create a copy of PatientState
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$PatientStateCopyWith<PatientState> get copyWith => _$PatientStateCopyWithImpl<PatientState>(this as PatientState, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as PatientState;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is PatientState&&(identical(other.sessions, _this.sessions) || other.sessions == _this.sessions)&&(identical(other.appointment, _this.appointment) || other.appointment == _this.appointment)&&(identical(other.day, _this.day) || other.day == _this.day)&&(identical(other.checkedIn, _this.checkedIn) || other.checkedIn == _this.checkedIn)&&(identical(other.confirmed, _this.confirmed) || other.confirmed == _this.confirmed)&&(identical(other.acknowledged, _this.acknowledged) || other.acknowledged == _this.acknowledged)&&(identical(other.note, _this.note) || other.note == _this.note)&&(identical(other.response, _this.response) || other.response == _this.response)&&(identical(other.careNote, _this.careNote) || other.careNote == _this.careNote)&&(identical(other.careStatus, _this.careStatus) || other.careStatus == _this.careStatus)&&(identical(other.editingOrder, _this.editingOrder) || other.editingOrder == _this.editingOrder)&&const DeepCollectionEquality().equals(other.cart, _this.cart)&&const DeepCollectionEquality().equals(other.updates, _this.updates)&&const DeepCollectionEquality().equals(other.escalations, _this.escalations));
}


@override
int get hashCode {
  final _this = this as PatientState;
  return Object.hash(runtimeType,_this.sessions,_this.appointment,_this.day,_this.checkedIn,_this.confirmed,_this.acknowledged,_this.note,_this.response,_this.careNote,_this.careStatus,_this.editingOrder,const DeepCollectionEquality().hash(_this.cart),const DeepCollectionEquality().hash(_this.updates),const DeepCollectionEquality().hash(_this.escalations));
}

@override
String toString() {
  final _this = this as PatientState;
  return 'PatientState(sessions: ${_this.sessions}, appointment: ${_this.appointment}, day: ${_this.day}, checkedIn: ${_this.checkedIn}, confirmed: ${_this.confirmed}, acknowledged: ${_this.acknowledged}, note: ${_this.note}, response: ${_this.response}, careNote: ${_this.careNote}, careStatus: ${_this.careStatus}, editingOrder: ${_this.editingOrder}, cart: ${_this.cart}, updates: ${_this.updates}, escalations: ${_this.escalations})';
}


}

/// @nodoc
abstract mixin class $PatientStateCopyWith<$Res>  {
  factory $PatientStateCopyWith(PatientState value, $Res Function(PatientState) _then) = _$PatientStateCopyWithImpl;
@useResult
$Res call({
 int sessions, String appointment, String day, bool checkedIn, bool confirmed, bool acknowledged, String note, String response, String careNote, String careStatus, String? editingOrder, List<CartLine> cart, List<String> updates, List<String> escalations
});




}
/// @nodoc
class _$PatientStateCopyWithImpl<$Res>
    implements $PatientStateCopyWith<$Res> {
  _$PatientStateCopyWithImpl(this._self, this._then);

  final PatientState _self;
  final $Res Function(PatientState) _then;

/// Create a copy of PatientState
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? sessions = null,Object? appointment = null,Object? day = null,Object? checkedIn = null,Object? confirmed = null,Object? acknowledged = null,Object? note = null,Object? response = null,Object? careNote = null,Object? careStatus = null,Object? editingOrder = freezed,Object? cart = null,Object? updates = null,Object? escalations = null,}) {
  return _then(PatientState(
sessions: null == sessions ? _self.sessions : sessions // ignore: cast_nullable_to_non_nullable
as int,appointment: null == appointment ? _self.appointment : appointment // ignore: cast_nullable_to_non_nullable
as String,day: null == day ? _self.day : day // ignore: cast_nullable_to_non_nullable
as String,checkedIn: null == checkedIn ? _self.checkedIn : checkedIn // ignore: cast_nullable_to_non_nullable
as bool,confirmed: null == confirmed ? _self.confirmed : confirmed // ignore: cast_nullable_to_non_nullable
as bool,acknowledged: null == acknowledged ? _self.acknowledged : acknowledged // ignore: cast_nullable_to_non_nullable
as bool,note: null == note ? _self.note : note // ignore: cast_nullable_to_non_nullable
as String,response: null == response ? _self.response : response // ignore: cast_nullable_to_non_nullable
as String,careNote: null == careNote ? _self.careNote : careNote // ignore: cast_nullable_to_non_nullable
as String,careStatus: null == careStatus ? _self.careStatus : careStatus // ignore: cast_nullable_to_non_nullable
as String,editingOrder: freezed == editingOrder ? _self.editingOrder : editingOrder // ignore: cast_nullable_to_non_nullable
as String?,cart: null == cart ? _self.cart : cart // ignore: cast_nullable_to_non_nullable
as List<CartLine>,updates: null == updates ? _self.updates : updates // ignore: cast_nullable_to_non_nullable
as List<String>,escalations: null == escalations ? _self.escalations : escalations // ignore: cast_nullable_to_non_nullable
as List<String>,
  ));
}

}


/// Adds pattern-matching-related methods to [PatientState].
extension PatientStatePatterns on PatientState {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _PatientState value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _PatientState() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _PatientState value)  $default,){
final _that = this;
switch (_that) {
case _PatientState():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _PatientState value)?  $default,){
final _that = this;
switch (_that) {
case _PatientState() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( int sessions,  String appointment,  String day,  bool checkedIn,  bool confirmed,  bool acknowledged,  String note,  String response,  String careNote,  String careStatus,  String? editingOrder,  List<CartLine> cart,  List<String> updates,  List<String> escalations)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _PatientState() when $default != null:
return $default(_that.sessions,_that.appointment,_that.day,_that.checkedIn,_that.confirmed,_that.acknowledged,_that.note,_that.response,_that.careNote,_that.careStatus,_that.editingOrder,_that.cart,_that.updates,_that.escalations);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( int sessions,  String appointment,  String day,  bool checkedIn,  bool confirmed,  bool acknowledged,  String note,  String response,  String careNote,  String careStatus,  String? editingOrder,  List<CartLine> cart,  List<String> updates,  List<String> escalations)  $default,) {final _that = this;
switch (_that) {
case _PatientState():
return $default(_that.sessions,_that.appointment,_that.day,_that.checkedIn,_that.confirmed,_that.acknowledged,_that.note,_that.response,_that.careNote,_that.careStatus,_that.editingOrder,_that.cart,_that.updates,_that.escalations);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( int sessions,  String appointment,  String day,  bool checkedIn,  bool confirmed,  bool acknowledged,  String note,  String response,  String careNote,  String careStatus,  String? editingOrder,  List<CartLine> cart,  List<String> updates,  List<String> escalations)?  $default,) {final _that = this;
switch (_that) {
case _PatientState() when $default != null:
return $default(_that.sessions,_that.appointment,_that.day,_that.checkedIn,_that.confirmed,_that.acknowledged,_that.note,_that.response,_that.careNote,_that.careStatus,_that.editingOrder,_that.cart,_that.updates,_that.escalations);case _:
  return null;

}
}

}

/// @nodoc


class _PatientState extends PatientState {
  const _PatientState({required this.sessions, required this.appointment, required this.day, this.checkedIn = false, this.confirmed = false, this.acknowledged = false, this.note = '', this.response = '', this.careNote = '', this.careStatus = 'Chưa liên hệ', this.editingOrder,  List<CartLine> cart = const [],  List<String> updates = const [],  List<String> escalations = const []}): _cart = cart,_updates = updates,_escalations = escalations,super._();
  

@override final  int sessions;
@override final  String appointment;
@override final  String day;
@override@JsonKey() final  bool checkedIn;
@override@JsonKey() final  bool confirmed;
@override@JsonKey() final  bool acknowledged;
@override@JsonKey() final  String note;
@override@JsonKey() final  String response;
@override@JsonKey() final  String careNote;
@override@JsonKey() final  String careStatus;
@override final  String? editingOrder;
 final  List<CartLine> _cart;
@override@JsonKey() List<CartLine> get cart {
  if (_cart is EqualUnmodifiableListView) return _cart;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_cart);
}

 final  List<String> _updates;
@override@JsonKey() List<String> get updates {
  if (_updates is EqualUnmodifiableListView) return _updates;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_updates);
}

/// Internal CSKH hand-offs; never shown in Care.
 final  List<String> _escalations;
/// Internal CSKH hand-offs; never shown in Care.
@override@JsonKey() List<String> get escalations {
  if (_escalations is EqualUnmodifiableListView) return _escalations;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_escalations);
}


/// Create a copy of PatientState
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$PatientStateCopyWith<_PatientState> get copyWith => __$PatientStateCopyWithImpl<_PatientState>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _PatientState&&(identical(other.sessions, sessions) || other.sessions == sessions)&&(identical(other.appointment, appointment) || other.appointment == appointment)&&(identical(other.day, day) || other.day == day)&&(identical(other.checkedIn, checkedIn) || other.checkedIn == checkedIn)&&(identical(other.confirmed, confirmed) || other.confirmed == confirmed)&&(identical(other.acknowledged, acknowledged) || other.acknowledged == acknowledged)&&(identical(other.note, note) || other.note == note)&&(identical(other.response, response) || other.response == response)&&(identical(other.careNote, careNote) || other.careNote == careNote)&&(identical(other.careStatus, careStatus) || other.careStatus == careStatus)&&(identical(other.editingOrder, editingOrder) || other.editingOrder == editingOrder)&&const DeepCollectionEquality().equals(other.cart, _cart)&&const DeepCollectionEquality().equals(other.updates, _updates)&&const DeepCollectionEquality().equals(other.escalations, _escalations));
}


@override
int get hashCode {
    return Object.hash(runtimeType,sessions,appointment,day,checkedIn,confirmed,acknowledged,note,response,careNote,careStatus,editingOrder,const DeepCollectionEquality().hash(_cart),const DeepCollectionEquality().hash(_updates),const DeepCollectionEquality().hash(_escalations));
}

@override
String toString() {
    return 'PatientState(sessions: $sessions, appointment: $appointment, day: $day, checkedIn: $checkedIn, confirmed: $confirmed, acknowledged: $acknowledged, note: $note, response: $response, careNote: $careNote, careStatus: $careStatus, editingOrder: $editingOrder, cart: $cart, updates: $updates, escalations: $escalations)';
}


}

/// @nodoc
abstract mixin class _$PatientStateCopyWith<$Res> implements $PatientStateCopyWith<$Res> {
  factory _$PatientStateCopyWith(_PatientState value, $Res Function(_PatientState) _then) = __$PatientStateCopyWithImpl;
@override @useResult
$Res call({
 int sessions, String appointment, String day, bool checkedIn, bool confirmed, bool acknowledged, String note, String response, String careNote, String careStatus, String? editingOrder, List<CartLine> cart, List<String> updates, List<String> escalations
});




}
/// @nodoc
class __$PatientStateCopyWithImpl<$Res>
    implements _$PatientStateCopyWith<$Res> {
  __$PatientStateCopyWithImpl(this._self, this._then);

  final _PatientState _self;
  final $Res Function(_PatientState) _then;

/// Create a copy of PatientState
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? sessions = null,Object? appointment = null,Object? day = null,Object? checkedIn = null,Object? confirmed = null,Object? acknowledged = null,Object? note = null,Object? response = null,Object? careNote = null,Object? careStatus = null,Object? editingOrder = freezed,Object? cart = null,Object? updates = null,Object? escalations = null,}) {
  return _then(_PatientState(
sessions: null == sessions ? _self.sessions : sessions // ignore: cast_nullable_to_non_nullable
as int,appointment: null == appointment ? _self.appointment : appointment // ignore: cast_nullable_to_non_nullable
as String,day: null == day ? _self.day : day // ignore: cast_nullable_to_non_nullable
as String,checkedIn: null == checkedIn ? _self.checkedIn : checkedIn // ignore: cast_nullable_to_non_nullable
as bool,confirmed: null == confirmed ? _self.confirmed : confirmed // ignore: cast_nullable_to_non_nullable
as bool,acknowledged: null == acknowledged ? _self.acknowledged : acknowledged // ignore: cast_nullable_to_non_nullable
as bool,note: null == note ? _self.note : note // ignore: cast_nullable_to_non_nullable
as String,response: null == response ? _self.response : response // ignore: cast_nullable_to_non_nullable
as String,careNote: null == careNote ? _self.careNote : careNote // ignore: cast_nullable_to_non_nullable
as String,careStatus: null == careStatus ? _self.careStatus : careStatus // ignore: cast_nullable_to_non_nullable
as String,editingOrder: freezed == editingOrder ? _self.editingOrder : editingOrder // ignore: cast_nullable_to_non_nullable
as String?,cart: null == cart ? _self._cart : cart // ignore: cast_nullable_to_non_nullable
as List<CartLine>,updates: null == updates ? _self._updates : updates // ignore: cast_nullable_to_non_nullable
as List<String>,escalations: null == escalations ? _self._escalations : escalations // ignore: cast_nullable_to_non_nullable
as List<String>,
  ));
}


}

// dart format on
