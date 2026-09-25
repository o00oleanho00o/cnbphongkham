// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'procedure_entry.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$ProcedureShare {

 String get doctor;/// Basis points of revenue; all shares of an entry sum to 10000.
 int get share;/// Basis points of the fee rate.
 int get rate;
/// Create a copy of ProcedureShare
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$ProcedureShareCopyWith<ProcedureShare> get copyWith => _$ProcedureShareCopyWithImpl<ProcedureShare>(this as ProcedureShare, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as ProcedureShare;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is ProcedureShare&&(identical(other.doctor, _this.doctor) || other.doctor == _this.doctor)&&(identical(other.share, _this.share) || other.share == _this.share)&&(identical(other.rate, _this.rate) || other.rate == _this.rate));
}


@override
int get hashCode {
  final _this = this as ProcedureShare;
  return Object.hash(runtimeType,_this.doctor,_this.share,_this.rate);
}

@override
String toString() {
  final _this = this as ProcedureShare;
  return 'ProcedureShare(doctor: ${_this.doctor}, share: ${_this.share}, rate: ${_this.rate})';
}


}

/// @nodoc
abstract mixin class $ProcedureShareCopyWith<$Res>  {
  factory $ProcedureShareCopyWith(ProcedureShare value, $Res Function(ProcedureShare) _then) = _$ProcedureShareCopyWithImpl;
@useResult
$Res call({
 String doctor, int share, int rate
});




}
/// @nodoc
class _$ProcedureShareCopyWithImpl<$Res>
    implements $ProcedureShareCopyWith<$Res> {
  _$ProcedureShareCopyWithImpl(this._self, this._then);

  final ProcedureShare _self;
  final $Res Function(ProcedureShare) _then;

/// Create a copy of ProcedureShare
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? doctor = null,Object? share = null,Object? rate = null,}) {
  return _then(ProcedureShare(
doctor: null == doctor ? _self.doctor : doctor // ignore: cast_nullable_to_non_nullable
as String,share: null == share ? _self.share : share // ignore: cast_nullable_to_non_nullable
as int,rate: null == rate ? _self.rate : rate // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [ProcedureShare].
extension ProcedureSharePatterns on ProcedureShare {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _ProcedureShare value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _ProcedureShare() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _ProcedureShare value)  $default,){
final _that = this;
switch (_that) {
case _ProcedureShare():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _ProcedureShare value)?  $default,){
final _that = this;
switch (_that) {
case _ProcedureShare() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String doctor,  int share,  int rate)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _ProcedureShare() when $default != null:
return $default(_that.doctor,_that.share,_that.rate);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String doctor,  int share,  int rate)  $default,) {final _that = this;
switch (_that) {
case _ProcedureShare():
return $default(_that.doctor,_that.share,_that.rate);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String doctor,  int share,  int rate)?  $default,) {final _that = this;
switch (_that) {
case _ProcedureShare() when $default != null:
return $default(_that.doctor,_that.share,_that.rate);case _:
  return null;

}
}

}

/// @nodoc


class _ProcedureShare implements ProcedureShare {
  const _ProcedureShare({required this.doctor, required this.share, required this.rate});
  

@override final  String doctor;
/// Basis points of revenue; all shares of an entry sum to 10000.
@override final  int share;
/// Basis points of the fee rate.
@override final  int rate;

/// Create a copy of ProcedureShare
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$ProcedureShareCopyWith<_ProcedureShare> get copyWith => __$ProcedureShareCopyWithImpl<_ProcedureShare>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _ProcedureShare&&(identical(other.doctor, doctor) || other.doctor == doctor)&&(identical(other.share, share) || other.share == share)&&(identical(other.rate, rate) || other.rate == rate));
}


@override
int get hashCode {
    return Object.hash(runtimeType,doctor,share,rate);
}

@override
String toString() {
    return 'ProcedureShare(doctor: $doctor, share: $share, rate: $rate)';
}


}

/// @nodoc
abstract mixin class _$ProcedureShareCopyWith<$Res> implements $ProcedureShareCopyWith<$Res> {
  factory _$ProcedureShareCopyWith(_ProcedureShare value, $Res Function(_ProcedureShare) _then) = __$ProcedureShareCopyWithImpl;
@override @useResult
$Res call({
 String doctor, int share, int rate
});




}
/// @nodoc
class __$ProcedureShareCopyWithImpl<$Res>
    implements _$ProcedureShareCopyWith<$Res> {
  __$ProcedureShareCopyWithImpl(this._self, this._then);

  final _ProcedureShare _self;
  final $Res Function(_ProcedureShare) _then;

/// Create a copy of ProcedureShare
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? doctor = null,Object? share = null,Object? rate = null,}) {
  return _then(_ProcedureShare(
doctor: null == doctor ? _self.doctor : doctor // ignore: cast_nullable_to_non_nullable
as String,share: null == share ? _self.share : share // ignore: cast_nullable_to_non_nullable
as int,rate: null == rate ? _self.rate : rate // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}

/// @nodoc
mixin _$ProcedureEntry {

 String get patient;/// Existing invoice id, or empty to create a new invoice.
 String get invoice; String get service; String get date; int get listPrice; int get discount; String get note; List<ProcedureShare> get people;
/// Create a copy of ProcedureEntry
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$ProcedureEntryCopyWith<ProcedureEntry> get copyWith => _$ProcedureEntryCopyWithImpl<ProcedureEntry>(this as ProcedureEntry, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as ProcedureEntry;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is ProcedureEntry&&(identical(other.patient, _this.patient) || other.patient == _this.patient)&&(identical(other.invoice, _this.invoice) || other.invoice == _this.invoice)&&(identical(other.service, _this.service) || other.service == _this.service)&&(identical(other.date, _this.date) || other.date == _this.date)&&(identical(other.listPrice, _this.listPrice) || other.listPrice == _this.listPrice)&&(identical(other.discount, _this.discount) || other.discount == _this.discount)&&(identical(other.note, _this.note) || other.note == _this.note)&&const DeepCollectionEquality().equals(other.people, _this.people));
}


@override
int get hashCode {
  final _this = this as ProcedureEntry;
  return Object.hash(runtimeType,_this.patient,_this.invoice,_this.service,_this.date,_this.listPrice,_this.discount,_this.note,const DeepCollectionEquality().hash(_this.people));
}

@override
String toString() {
  final _this = this as ProcedureEntry;
  return 'ProcedureEntry(patient: ${_this.patient}, invoice: ${_this.invoice}, service: ${_this.service}, date: ${_this.date}, listPrice: ${_this.listPrice}, discount: ${_this.discount}, note: ${_this.note}, people: ${_this.people})';
}


}

/// @nodoc
abstract mixin class $ProcedureEntryCopyWith<$Res>  {
  factory $ProcedureEntryCopyWith(ProcedureEntry value, $Res Function(ProcedureEntry) _then) = _$ProcedureEntryCopyWithImpl;
@useResult
$Res call({
 String patient, String invoice, String service, String date, int listPrice, int discount, String note, List<ProcedureShare> people
});




}
/// @nodoc
class _$ProcedureEntryCopyWithImpl<$Res>
    implements $ProcedureEntryCopyWith<$Res> {
  _$ProcedureEntryCopyWithImpl(this._self, this._then);

  final ProcedureEntry _self;
  final $Res Function(ProcedureEntry) _then;

/// Create a copy of ProcedureEntry
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? patient = null,Object? invoice = null,Object? service = null,Object? date = null,Object? listPrice = null,Object? discount = null,Object? note = null,Object? people = null,}) {
  return _then(ProcedureEntry(
patient: null == patient ? _self.patient : patient // ignore: cast_nullable_to_non_nullable
as String,invoice: null == invoice ? _self.invoice : invoice // ignore: cast_nullable_to_non_nullable
as String,service: null == service ? _self.service : service // ignore: cast_nullable_to_non_nullable
as String,date: null == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String,listPrice: null == listPrice ? _self.listPrice : listPrice // ignore: cast_nullable_to_non_nullable
as int,discount: null == discount ? _self.discount : discount // ignore: cast_nullable_to_non_nullable
as int,note: null == note ? _self.note : note // ignore: cast_nullable_to_non_nullable
as String,people: null == people ? _self.people : people // ignore: cast_nullable_to_non_nullable
as List<ProcedureShare>,
  ));
}

}


/// Adds pattern-matching-related methods to [ProcedureEntry].
extension ProcedureEntryPatterns on ProcedureEntry {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _ProcedureEntry value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _ProcedureEntry() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _ProcedureEntry value)  $default,){
final _that = this;
switch (_that) {
case _ProcedureEntry():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _ProcedureEntry value)?  $default,){
final _that = this;
switch (_that) {
case _ProcedureEntry() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String patient,  String invoice,  String service,  String date,  int listPrice,  int discount,  String note,  List<ProcedureShare> people)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _ProcedureEntry() when $default != null:
return $default(_that.patient,_that.invoice,_that.service,_that.date,_that.listPrice,_that.discount,_that.note,_that.people);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String patient,  String invoice,  String service,  String date,  int listPrice,  int discount,  String note,  List<ProcedureShare> people)  $default,) {final _that = this;
switch (_that) {
case _ProcedureEntry():
return $default(_that.patient,_that.invoice,_that.service,_that.date,_that.listPrice,_that.discount,_that.note,_that.people);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String patient,  String invoice,  String service,  String date,  int listPrice,  int discount,  String note,  List<ProcedureShare> people)?  $default,) {final _that = this;
switch (_that) {
case _ProcedureEntry() when $default != null:
return $default(_that.patient,_that.invoice,_that.service,_that.date,_that.listPrice,_that.discount,_that.note,_that.people);case _:
  return null;

}
}

}

/// @nodoc


class _ProcedureEntry implements ProcedureEntry {
  const _ProcedureEntry({required this.patient, required this.invoice, required this.service, required this.date, required this.listPrice, required this.discount, required this.note, required  List<ProcedureShare> people}): _people = people;
  

@override final  String patient;
/// Existing invoice id, or empty to create a new invoice.
@override final  String invoice;
@override final  String service;
@override final  String date;
@override final  int listPrice;
@override final  int discount;
@override final  String note;
 final  List<ProcedureShare> _people;
@override List<ProcedureShare> get people {
  if (_people is EqualUnmodifiableListView) return _people;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_people);
}


/// Create a copy of ProcedureEntry
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$ProcedureEntryCopyWith<_ProcedureEntry> get copyWith => __$ProcedureEntryCopyWithImpl<_ProcedureEntry>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _ProcedureEntry&&(identical(other.patient, patient) || other.patient == patient)&&(identical(other.invoice, invoice) || other.invoice == invoice)&&(identical(other.service, service) || other.service == service)&&(identical(other.date, date) || other.date == date)&&(identical(other.listPrice, listPrice) || other.listPrice == listPrice)&&(identical(other.discount, discount) || other.discount == discount)&&(identical(other.note, note) || other.note == note)&&const DeepCollectionEquality().equals(other.people, _people));
}


@override
int get hashCode {
    return Object.hash(runtimeType,patient,invoice,service,date,listPrice,discount,note,const DeepCollectionEquality().hash(_people));
}

@override
String toString() {
    return 'ProcedureEntry(patient: $patient, invoice: $invoice, service: $service, date: $date, listPrice: $listPrice, discount: $discount, note: $note, people: $people)';
}


}

/// @nodoc
abstract mixin class _$ProcedureEntryCopyWith<$Res> implements $ProcedureEntryCopyWith<$Res> {
  factory _$ProcedureEntryCopyWith(_ProcedureEntry value, $Res Function(_ProcedureEntry) _then) = __$ProcedureEntryCopyWithImpl;
@override @useResult
$Res call({
 String patient, String invoice, String service, String date, int listPrice, int discount, String note, List<ProcedureShare> people
});




}
/// @nodoc
class __$ProcedureEntryCopyWithImpl<$Res>
    implements _$ProcedureEntryCopyWith<$Res> {
  __$ProcedureEntryCopyWithImpl(this._self, this._then);

  final _ProcedureEntry _self;
  final $Res Function(_ProcedureEntry) _then;

/// Create a copy of ProcedureEntry
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? patient = null,Object? invoice = null,Object? service = null,Object? date = null,Object? listPrice = null,Object? discount = null,Object? note = null,Object? people = null,}) {
  return _then(_ProcedureEntry(
patient: null == patient ? _self.patient : patient // ignore: cast_nullable_to_non_nullable
as String,invoice: null == invoice ? _self.invoice : invoice // ignore: cast_nullable_to_non_nullable
as String,service: null == service ? _self.service : service // ignore: cast_nullable_to_non_nullable
as String,date: null == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String,listPrice: null == listPrice ? _self.listPrice : listPrice // ignore: cast_nullable_to_non_nullable
as int,discount: null == discount ? _self.discount : discount // ignore: cast_nullable_to_non_nullable
as int,note: null == note ? _self.note : note // ignore: cast_nullable_to_non_nullable
as String,people: null == people ? _self._people : people // ignore: cast_nullable_to_non_nullable
as List<ProcedureShare>,
  ));
}


}

// dart format on
