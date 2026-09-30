// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'finance_snapshot.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$FinanceSummary {

 int get revenue; int get fee; int get pending;/// Omitted from a doctor's private projection.
 int? get collected; int? get debt;
/// Create a copy of FinanceSummary
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$FinanceSummaryCopyWith<FinanceSummary> get copyWith => _$FinanceSummaryCopyWithImpl<FinanceSummary>(this as FinanceSummary, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as FinanceSummary;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is FinanceSummary&&(identical(other.revenue, _this.revenue) || other.revenue == _this.revenue)&&(identical(other.fee, _this.fee) || other.fee == _this.fee)&&(identical(other.pending, _this.pending) || other.pending == _this.pending)&&(identical(other.collected, _this.collected) || other.collected == _this.collected)&&(identical(other.debt, _this.debt) || other.debt == _this.debt));
}


@override
int get hashCode {
  final _this = this as FinanceSummary;
  return Object.hash(runtimeType,_this.revenue,_this.fee,_this.pending,_this.collected,_this.debt);
}

@override
String toString() {
  final _this = this as FinanceSummary;
  return 'FinanceSummary(revenue: ${_this.revenue}, fee: ${_this.fee}, pending: ${_this.pending}, collected: ${_this.collected}, debt: ${_this.debt})';
}


}

/// @nodoc
abstract mixin class $FinanceSummaryCopyWith<$Res>  {
  factory $FinanceSummaryCopyWith(FinanceSummary value, $Res Function(FinanceSummary) _then) = _$FinanceSummaryCopyWithImpl;
@useResult
$Res call({
 int revenue, int fee, int pending, int? collected, int? debt
});




}
/// @nodoc
class _$FinanceSummaryCopyWithImpl<$Res>
    implements $FinanceSummaryCopyWith<$Res> {
  _$FinanceSummaryCopyWithImpl(this._self, this._then);

  final FinanceSummary _self;
  final $Res Function(FinanceSummary) _then;

/// Create a copy of FinanceSummary
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? revenue = null,Object? fee = null,Object? pending = null,Object? collected = freezed,Object? debt = freezed,}) {
  return _then(FinanceSummary(
revenue: null == revenue ? _self.revenue : revenue // ignore: cast_nullable_to_non_nullable
as int,fee: null == fee ? _self.fee : fee // ignore: cast_nullable_to_non_nullable
as int,pending: null == pending ? _self.pending : pending // ignore: cast_nullable_to_non_nullable
as int,collected: freezed == collected ? _self.collected : collected // ignore: cast_nullable_to_non_nullable
as int?,debt: freezed == debt ? _self.debt : debt // ignore: cast_nullable_to_non_nullable
as int?,
  ));
}

}


/// Adds pattern-matching-related methods to [FinanceSummary].
extension FinanceSummaryPatterns on FinanceSummary {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _FinanceSummary value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _FinanceSummary() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _FinanceSummary value)  $default,){
final _that = this;
switch (_that) {
case _FinanceSummary():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _FinanceSummary value)?  $default,){
final _that = this;
switch (_that) {
case _FinanceSummary() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( int revenue,  int fee,  int pending,  int? collected,  int? debt)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _FinanceSummary() when $default != null:
return $default(_that.revenue,_that.fee,_that.pending,_that.collected,_that.debt);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( int revenue,  int fee,  int pending,  int? collected,  int? debt)  $default,) {final _that = this;
switch (_that) {
case _FinanceSummary():
return $default(_that.revenue,_that.fee,_that.pending,_that.collected,_that.debt);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( int revenue,  int fee,  int pending,  int? collected,  int? debt)?  $default,) {final _that = this;
switch (_that) {
case _FinanceSummary() when $default != null:
return $default(_that.revenue,_that.fee,_that.pending,_that.collected,_that.debt);case _:
  return null;

}
}

}

/// @nodoc


class _FinanceSummary implements FinanceSummary {
  const _FinanceSummary({required this.revenue, required this.fee, required this.pending, this.collected, this.debt});
  

@override final  int revenue;
@override final  int fee;
@override final  int pending;
/// Omitted from a doctor's private projection.
@override final  int? collected;
@override final  int? debt;

/// Create a copy of FinanceSummary
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$FinanceSummaryCopyWith<_FinanceSummary> get copyWith => __$FinanceSummaryCopyWithImpl<_FinanceSummary>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _FinanceSummary&&(identical(other.revenue, revenue) || other.revenue == revenue)&&(identical(other.fee, fee) || other.fee == fee)&&(identical(other.pending, pending) || other.pending == pending)&&(identical(other.collected, collected) || other.collected == collected)&&(identical(other.debt, debt) || other.debt == debt));
}


@override
int get hashCode {
    return Object.hash(runtimeType,revenue,fee,pending,collected,debt);
}

@override
String toString() {
    return 'FinanceSummary(revenue: $revenue, fee: $fee, pending: $pending, collected: $collected, debt: $debt)';
}


}

/// @nodoc
abstract mixin class _$FinanceSummaryCopyWith<$Res> implements $FinanceSummaryCopyWith<$Res> {
  factory _$FinanceSummaryCopyWith(_FinanceSummary value, $Res Function(_FinanceSummary) _then) = __$FinanceSummaryCopyWithImpl;
@override @useResult
$Res call({
 int revenue, int fee, int pending, int? collected, int? debt
});




}
/// @nodoc
class __$FinanceSummaryCopyWithImpl<$Res>
    implements _$FinanceSummaryCopyWith<$Res> {
  __$FinanceSummaryCopyWithImpl(this._self, this._then);

  final _FinanceSummary _self;
  final $Res Function(_FinanceSummary) _then;

/// Create a copy of FinanceSummary
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? revenue = null,Object? fee = null,Object? pending = null,Object? collected = freezed,Object? debt = freezed,}) {
  return _then(_FinanceSummary(
revenue: null == revenue ? _self.revenue : revenue // ignore: cast_nullable_to_non_nullable
as int,fee: null == fee ? _self.fee : fee // ignore: cast_nullable_to_non_nullable
as int,pending: null == pending ? _self.pending : pending // ignore: cast_nullable_to_non_nullable
as int,collected: freezed == collected ? _self.collected : collected // ignore: cast_nullable_to_non_nullable
as int?,debt: freezed == debt ? _self.debt : debt // ignore: cast_nullable_to_non_nullable
as int?,
  ));
}


}

/// @nodoc
mixin _$FinanceDoctor {

 String get id; String get name;
/// Create a copy of FinanceDoctor
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$FinanceDoctorCopyWith<FinanceDoctor> get copyWith => _$FinanceDoctorCopyWithImpl<FinanceDoctor>(this as FinanceDoctor, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as FinanceDoctor;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is FinanceDoctor&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.name, _this.name) || other.name == _this.name));
}


@override
int get hashCode {
  final _this = this as FinanceDoctor;
  return Object.hash(runtimeType,_this.id,_this.name);
}

@override
String toString() {
  final _this = this as FinanceDoctor;
  return 'FinanceDoctor(id: ${_this.id}, name: ${_this.name})';
}


}

/// @nodoc
abstract mixin class $FinanceDoctorCopyWith<$Res>  {
  factory $FinanceDoctorCopyWith(FinanceDoctor value, $Res Function(FinanceDoctor) _then) = _$FinanceDoctorCopyWithImpl;
@useResult
$Res call({
 String id, String name
});




}
/// @nodoc
class _$FinanceDoctorCopyWithImpl<$Res>
    implements $FinanceDoctorCopyWith<$Res> {
  _$FinanceDoctorCopyWithImpl(this._self, this._then);

  final FinanceDoctor _self;
  final $Res Function(FinanceDoctor) _then;

/// Create a copy of FinanceDoctor
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? name = null,}) {
  return _then(FinanceDoctor(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,
  ));
}

}


/// Adds pattern-matching-related methods to [FinanceDoctor].
extension FinanceDoctorPatterns on FinanceDoctor {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _FinanceDoctor value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _FinanceDoctor() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _FinanceDoctor value)  $default,){
final _that = this;
switch (_that) {
case _FinanceDoctor():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _FinanceDoctor value)?  $default,){
final _that = this;
switch (_that) {
case _FinanceDoctor() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String name)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _FinanceDoctor() when $default != null:
return $default(_that.id,_that.name);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String name)  $default,) {final _that = this;
switch (_that) {
case _FinanceDoctor():
return $default(_that.id,_that.name);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String name)?  $default,) {final _that = this;
switch (_that) {
case _FinanceDoctor() when $default != null:
return $default(_that.id,_that.name);case _:
  return null;

}
}

}

/// @nodoc


class _FinanceDoctor implements FinanceDoctor {
  const _FinanceDoctor({required this.id, required this.name});
  

@override final  String id;
@override final  String name;

/// Create a copy of FinanceDoctor
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$FinanceDoctorCopyWith<_FinanceDoctor> get copyWith => __$FinanceDoctorCopyWithImpl<_FinanceDoctor>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _FinanceDoctor&&(identical(other.id, id) || other.id == id)&&(identical(other.name, name) || other.name == name));
}


@override
int get hashCode {
    return Object.hash(runtimeType,id,name);
}

@override
String toString() {
    return 'FinanceDoctor(id: $id, name: $name)';
}


}

/// @nodoc
abstract mixin class _$FinanceDoctorCopyWith<$Res> implements $FinanceDoctorCopyWith<$Res> {
  factory _$FinanceDoctorCopyWith(_FinanceDoctor value, $Res Function(_FinanceDoctor) _then) = __$FinanceDoctorCopyWithImpl;
@override @useResult
$Res call({
 String id, String name
});




}
/// @nodoc
class __$FinanceDoctorCopyWithImpl<$Res>
    implements _$FinanceDoctorCopyWith<$Res> {
  __$FinanceDoctorCopyWithImpl(this._self, this._then);

  final _FinanceDoctor _self;
  final $Res Function(_FinanceDoctor) _then;

/// Create a copy of FinanceDoctor
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? name = null,}) {
  return _then(_FinanceDoctor(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,
  ));
}


}

/// @nodoc
mixin _$ProcedureService {

 String get id; String get name; int get price;/// Basis points: 2000 = 20%.
 int get rate;/// `net`, `list` or `collected`.
 String get basis; int get version;
/// Create a copy of ProcedureService
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$ProcedureServiceCopyWith<ProcedureService> get copyWith => _$ProcedureServiceCopyWithImpl<ProcedureService>(this as ProcedureService, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as ProcedureService;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is ProcedureService&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.name, _this.name) || other.name == _this.name)&&(identical(other.price, _this.price) || other.price == _this.price)&&(identical(other.rate, _this.rate) || other.rate == _this.rate)&&(identical(other.basis, _this.basis) || other.basis == _this.basis)&&(identical(other.version, _this.version) || other.version == _this.version));
}


@override
int get hashCode {
  final _this = this as ProcedureService;
  return Object.hash(runtimeType,_this.id,_this.name,_this.price,_this.rate,_this.basis,_this.version);
}

@override
String toString() {
  final _this = this as ProcedureService;
  return 'ProcedureService(id: ${_this.id}, name: ${_this.name}, price: ${_this.price}, rate: ${_this.rate}, basis: ${_this.basis}, version: ${_this.version})';
}


}

/// @nodoc
abstract mixin class $ProcedureServiceCopyWith<$Res>  {
  factory $ProcedureServiceCopyWith(ProcedureService value, $Res Function(ProcedureService) _then) = _$ProcedureServiceCopyWithImpl;
@useResult
$Res call({
 String id, String name, int price, int rate, String basis, int version
});




}
/// @nodoc
class _$ProcedureServiceCopyWithImpl<$Res>
    implements $ProcedureServiceCopyWith<$Res> {
  _$ProcedureServiceCopyWithImpl(this._self, this._then);

  final ProcedureService _self;
  final $Res Function(ProcedureService) _then;

/// Create a copy of ProcedureService
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? name = null,Object? price = null,Object? rate = null,Object? basis = null,Object? version = null,}) {
  return _then(ProcedureService(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,price: null == price ? _self.price : price // ignore: cast_nullable_to_non_nullable
as int,rate: null == rate ? _self.rate : rate // ignore: cast_nullable_to_non_nullable
as int,basis: null == basis ? _self.basis : basis // ignore: cast_nullable_to_non_nullable
as String,version: null == version ? _self.version : version // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [ProcedureService].
extension ProcedureServicePatterns on ProcedureService {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _ProcedureService value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _ProcedureService() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _ProcedureService value)  $default,){
final _that = this;
switch (_that) {
case _ProcedureService():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _ProcedureService value)?  $default,){
final _that = this;
switch (_that) {
case _ProcedureService() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String name,  int price,  int rate,  String basis,  int version)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _ProcedureService() when $default != null:
return $default(_that.id,_that.name,_that.price,_that.rate,_that.basis,_that.version);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String name,  int price,  int rate,  String basis,  int version)  $default,) {final _that = this;
switch (_that) {
case _ProcedureService():
return $default(_that.id,_that.name,_that.price,_that.rate,_that.basis,_that.version);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String name,  int price,  int rate,  String basis,  int version)?  $default,) {final _that = this;
switch (_that) {
case _ProcedureService() when $default != null:
return $default(_that.id,_that.name,_that.price,_that.rate,_that.basis,_that.version);case _:
  return null;

}
}

}

/// @nodoc


class _ProcedureService extends ProcedureService {
  const _ProcedureService({required this.id, required this.name, required this.price, required this.rate, required this.basis, required this.version}): super._();
  

@override final  String id;
@override final  String name;
@override final  int price;
/// Basis points: 2000 = 20%.
@override final  int rate;
/// `net`, `list` or `collected`.
@override final  String basis;
@override final  int version;

/// Create a copy of ProcedureService
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$ProcedureServiceCopyWith<_ProcedureService> get copyWith => __$ProcedureServiceCopyWithImpl<_ProcedureService>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _ProcedureService&&(identical(other.id, id) || other.id == id)&&(identical(other.name, name) || other.name == name)&&(identical(other.price, price) || other.price == price)&&(identical(other.rate, rate) || other.rate == rate)&&(identical(other.basis, basis) || other.basis == basis)&&(identical(other.version, version) || other.version == version));
}


@override
int get hashCode {
    return Object.hash(runtimeType,id,name,price,rate,basis,version);
}

@override
String toString() {
    return 'ProcedureService(id: $id, name: $name, price: $price, rate: $rate, basis: $basis, version: $version)';
}


}

/// @nodoc
abstract mixin class _$ProcedureServiceCopyWith<$Res> implements $ProcedureServiceCopyWith<$Res> {
  factory _$ProcedureServiceCopyWith(_ProcedureService value, $Res Function(_ProcedureService) _then) = __$ProcedureServiceCopyWithImpl;
@override @useResult
$Res call({
 String id, String name, int price, int rate, String basis, int version
});




}
/// @nodoc
class __$ProcedureServiceCopyWithImpl<$Res>
    implements _$ProcedureServiceCopyWith<$Res> {
  __$ProcedureServiceCopyWithImpl(this._self, this._then);

  final _ProcedureService _self;
  final $Res Function(_ProcedureService) _then;

/// Create a copy of ProcedureService
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? name = null,Object? price = null,Object? rate = null,Object? basis = null,Object? version = null,}) {
  return _then(_ProcedureService(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,price: null == price ? _self.price : price // ignore: cast_nullable_to_non_nullable
as int,rate: null == rate ? _self.rate : rate // ignore: cast_nullable_to_non_nullable
as int,basis: null == basis ? _self.basis : basis // ignore: cast_nullable_to_non_nullable
as String,version: null == version ? _self.version : version // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}

/// @nodoc
mixin _$ProcedureRow {

 String get id; String get date; String get patient; String get service; String get doctor;/// `pending`, `approved` or `void`.
 String get status; int get base;/// Basis points.
 int get rate; int get revenue; int get fee;
/// Create a copy of ProcedureRow
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$ProcedureRowCopyWith<ProcedureRow> get copyWith => _$ProcedureRowCopyWithImpl<ProcedureRow>(this as ProcedureRow, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as ProcedureRow;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is ProcedureRow&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.date, _this.date) || other.date == _this.date)&&(identical(other.patient, _this.patient) || other.patient == _this.patient)&&(identical(other.service, _this.service) || other.service == _this.service)&&(identical(other.doctor, _this.doctor) || other.doctor == _this.doctor)&&(identical(other.status, _this.status) || other.status == _this.status)&&(identical(other.base, _this.base) || other.base == _this.base)&&(identical(other.rate, _this.rate) || other.rate == _this.rate)&&(identical(other.revenue, _this.revenue) || other.revenue == _this.revenue)&&(identical(other.fee, _this.fee) || other.fee == _this.fee));
}


@override
int get hashCode {
  final _this = this as ProcedureRow;
  return Object.hash(runtimeType,_this.id,_this.date,_this.patient,_this.service,_this.doctor,_this.status,_this.base,_this.rate,_this.revenue,_this.fee);
}

@override
String toString() {
  final _this = this as ProcedureRow;
  return 'ProcedureRow(id: ${_this.id}, date: ${_this.date}, patient: ${_this.patient}, service: ${_this.service}, doctor: ${_this.doctor}, status: ${_this.status}, base: ${_this.base}, rate: ${_this.rate}, revenue: ${_this.revenue}, fee: ${_this.fee})';
}


}

/// @nodoc
abstract mixin class $ProcedureRowCopyWith<$Res>  {
  factory $ProcedureRowCopyWith(ProcedureRow value, $Res Function(ProcedureRow) _then) = _$ProcedureRowCopyWithImpl;
@useResult
$Res call({
 String id, String date, String patient, String service, String doctor, String status, int base, int rate, int revenue, int fee
});




}
/// @nodoc
class _$ProcedureRowCopyWithImpl<$Res>
    implements $ProcedureRowCopyWith<$Res> {
  _$ProcedureRowCopyWithImpl(this._self, this._then);

  final ProcedureRow _self;
  final $Res Function(ProcedureRow) _then;

/// Create a copy of ProcedureRow
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? date = null,Object? patient = null,Object? service = null,Object? doctor = null,Object? status = null,Object? base = null,Object? rate = null,Object? revenue = null,Object? fee = null,}) {
  return _then(ProcedureRow(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,date: null == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String,patient: null == patient ? _self.patient : patient // ignore: cast_nullable_to_non_nullable
as String,service: null == service ? _self.service : service // ignore: cast_nullable_to_non_nullable
as String,doctor: null == doctor ? _self.doctor : doctor // ignore: cast_nullable_to_non_nullable
as String,status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,base: null == base ? _self.base : base // ignore: cast_nullable_to_non_nullable
as int,rate: null == rate ? _self.rate : rate // ignore: cast_nullable_to_non_nullable
as int,revenue: null == revenue ? _self.revenue : revenue // ignore: cast_nullable_to_non_nullable
as int,fee: null == fee ? _self.fee : fee // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [ProcedureRow].
extension ProcedureRowPatterns on ProcedureRow {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _ProcedureRow value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _ProcedureRow() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _ProcedureRow value)  $default,){
final _that = this;
switch (_that) {
case _ProcedureRow():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _ProcedureRow value)?  $default,){
final _that = this;
switch (_that) {
case _ProcedureRow() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String date,  String patient,  String service,  String doctor,  String status,  int base,  int rate,  int revenue,  int fee)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _ProcedureRow() when $default != null:
return $default(_that.id,_that.date,_that.patient,_that.service,_that.doctor,_that.status,_that.base,_that.rate,_that.revenue,_that.fee);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String date,  String patient,  String service,  String doctor,  String status,  int base,  int rate,  int revenue,  int fee)  $default,) {final _that = this;
switch (_that) {
case _ProcedureRow():
return $default(_that.id,_that.date,_that.patient,_that.service,_that.doctor,_that.status,_that.base,_that.rate,_that.revenue,_that.fee);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String date,  String patient,  String service,  String doctor,  String status,  int base,  int rate,  int revenue,  int fee)?  $default,) {final _that = this;
switch (_that) {
case _ProcedureRow() when $default != null:
return $default(_that.id,_that.date,_that.patient,_that.service,_that.doctor,_that.status,_that.base,_that.rate,_that.revenue,_that.fee);case _:
  return null;

}
}

}

/// @nodoc


class _ProcedureRow extends ProcedureRow {
  const _ProcedureRow({required this.id, required this.date, required this.patient, required this.service, required this.doctor, required this.status, required this.base, required this.rate, required this.revenue, required this.fee}): super._();
  

@override final  String id;
@override final  String date;
@override final  String patient;
@override final  String service;
@override final  String doctor;
/// `pending`, `approved` or `void`.
@override final  String status;
@override final  int base;
/// Basis points.
@override final  int rate;
@override final  int revenue;
@override final  int fee;

/// Create a copy of ProcedureRow
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$ProcedureRowCopyWith<_ProcedureRow> get copyWith => __$ProcedureRowCopyWithImpl<_ProcedureRow>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _ProcedureRow&&(identical(other.id, id) || other.id == id)&&(identical(other.date, date) || other.date == date)&&(identical(other.patient, patient) || other.patient == patient)&&(identical(other.service, service) || other.service == service)&&(identical(other.doctor, doctor) || other.doctor == doctor)&&(identical(other.status, status) || other.status == status)&&(identical(other.base, base) || other.base == base)&&(identical(other.rate, rate) || other.rate == rate)&&(identical(other.revenue, revenue) || other.revenue == revenue)&&(identical(other.fee, fee) || other.fee == fee));
}


@override
int get hashCode {
    return Object.hash(runtimeType,id,date,patient,service,doctor,status,base,rate,revenue,fee);
}

@override
String toString() {
    return 'ProcedureRow(id: $id, date: $date, patient: $patient, service: $service, doctor: $doctor, status: $status, base: $base, rate: $rate, revenue: $revenue, fee: $fee)';
}


}

/// @nodoc
abstract mixin class _$ProcedureRowCopyWith<$Res> implements $ProcedureRowCopyWith<$Res> {
  factory _$ProcedureRowCopyWith(_ProcedureRow value, $Res Function(_ProcedureRow) _then) = __$ProcedureRowCopyWithImpl;
@override @useResult
$Res call({
 String id, String date, String patient, String service, String doctor, String status, int base, int rate, int revenue, int fee
});




}
/// @nodoc
class __$ProcedureRowCopyWithImpl<$Res>
    implements _$ProcedureRowCopyWith<$Res> {
  __$ProcedureRowCopyWithImpl(this._self, this._then);

  final _ProcedureRow _self;
  final $Res Function(_ProcedureRow) _then;

/// Create a copy of ProcedureRow
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? date = null,Object? patient = null,Object? service = null,Object? doctor = null,Object? status = null,Object? base = null,Object? rate = null,Object? revenue = null,Object? fee = null,}) {
  return _then(_ProcedureRow(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,date: null == date ? _self.date : date // ignore: cast_nullable_to_non_nullable
as String,patient: null == patient ? _self.patient : patient // ignore: cast_nullable_to_non_nullable
as String,service: null == service ? _self.service : service // ignore: cast_nullable_to_non_nullable
as String,doctor: null == doctor ? _self.doctor : doctor // ignore: cast_nullable_to_non_nullable
as String,status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,base: null == base ? _self.base : base // ignore: cast_nullable_to_non_nullable
as int,rate: null == rate ? _self.rate : rate // ignore: cast_nullable_to_non_nullable
as int,revenue: null == revenue ? _self.revenue : revenue // ignore: cast_nullable_to_non_nullable
as int,fee: null == fee ? _self.fee : fee // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}

/// @nodoc
mixin _$FinanceInvoice {

 String get id; String get patient;/// `finance` or `web` (legacy cashier mirror).
 String get source; int get amount; int get received;
/// Create a copy of FinanceInvoice
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$FinanceInvoiceCopyWith<FinanceInvoice> get copyWith => _$FinanceInvoiceCopyWithImpl<FinanceInvoice>(this as FinanceInvoice, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as FinanceInvoice;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is FinanceInvoice&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.patient, _this.patient) || other.patient == _this.patient)&&(identical(other.source, _this.source) || other.source == _this.source)&&(identical(other.amount, _this.amount) || other.amount == _this.amount)&&(identical(other.received, _this.received) || other.received == _this.received));
}


@override
int get hashCode {
  final _this = this as FinanceInvoice;
  return Object.hash(runtimeType,_this.id,_this.patient,_this.source,_this.amount,_this.received);
}

@override
String toString() {
  final _this = this as FinanceInvoice;
  return 'FinanceInvoice(id: ${_this.id}, patient: ${_this.patient}, source: ${_this.source}, amount: ${_this.amount}, received: ${_this.received})';
}


}

/// @nodoc
abstract mixin class $FinanceInvoiceCopyWith<$Res>  {
  factory $FinanceInvoiceCopyWith(FinanceInvoice value, $Res Function(FinanceInvoice) _then) = _$FinanceInvoiceCopyWithImpl;
@useResult
$Res call({
 String id, String patient, String source, int amount, int received
});




}
/// @nodoc
class _$FinanceInvoiceCopyWithImpl<$Res>
    implements $FinanceInvoiceCopyWith<$Res> {
  _$FinanceInvoiceCopyWithImpl(this._self, this._then);

  final FinanceInvoice _self;
  final $Res Function(FinanceInvoice) _then;

/// Create a copy of FinanceInvoice
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? patient = null,Object? source = null,Object? amount = null,Object? received = null,}) {
  return _then(FinanceInvoice(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,patient: null == patient ? _self.patient : patient // ignore: cast_nullable_to_non_nullable
as String,source: null == source ? _self.source : source // ignore: cast_nullable_to_non_nullable
as String,amount: null == amount ? _self.amount : amount // ignore: cast_nullable_to_non_nullable
as int,received: null == received ? _self.received : received // ignore: cast_nullable_to_non_nullable
as int,
  ));
}

}


/// Adds pattern-matching-related methods to [FinanceInvoice].
extension FinanceInvoicePatterns on FinanceInvoice {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _FinanceInvoice value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _FinanceInvoice() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _FinanceInvoice value)  $default,){
final _that = this;
switch (_that) {
case _FinanceInvoice():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _FinanceInvoice value)?  $default,){
final _that = this;
switch (_that) {
case _FinanceInvoice() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String patient,  String source,  int amount,  int received)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _FinanceInvoice() when $default != null:
return $default(_that.id,_that.patient,_that.source,_that.amount,_that.received);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String patient,  String source,  int amount,  int received)  $default,) {final _that = this;
switch (_that) {
case _FinanceInvoice():
return $default(_that.id,_that.patient,_that.source,_that.amount,_that.received);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String patient,  String source,  int amount,  int received)?  $default,) {final _that = this;
switch (_that) {
case _FinanceInvoice() when $default != null:
return $default(_that.id,_that.patient,_that.source,_that.amount,_that.received);case _:
  return null;

}
}

}

/// @nodoc


class _FinanceInvoice extends FinanceInvoice {
  const _FinanceInvoice({required this.id, required this.patient, required this.source, required this.amount, required this.received}): super._();
  

@override final  String id;
@override final  String patient;
/// `finance` or `web` (legacy cashier mirror).
@override final  String source;
@override final  int amount;
@override final  int received;

/// Create a copy of FinanceInvoice
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$FinanceInvoiceCopyWith<_FinanceInvoice> get copyWith => __$FinanceInvoiceCopyWithImpl<_FinanceInvoice>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _FinanceInvoice&&(identical(other.id, id) || other.id == id)&&(identical(other.patient, patient) || other.patient == patient)&&(identical(other.source, source) || other.source == source)&&(identical(other.amount, amount) || other.amount == amount)&&(identical(other.received, received) || other.received == received));
}


@override
int get hashCode {
    return Object.hash(runtimeType,id,patient,source,amount,received);
}

@override
String toString() {
    return 'FinanceInvoice(id: $id, patient: $patient, source: $source, amount: $amount, received: $received)';
}


}

/// @nodoc
abstract mixin class _$FinanceInvoiceCopyWith<$Res> implements $FinanceInvoiceCopyWith<$Res> {
  factory _$FinanceInvoiceCopyWith(_FinanceInvoice value, $Res Function(_FinanceInvoice) _then) = __$FinanceInvoiceCopyWithImpl;
@override @useResult
$Res call({
 String id, String patient, String source, int amount, int received
});




}
/// @nodoc
class __$FinanceInvoiceCopyWithImpl<$Res>
    implements _$FinanceInvoiceCopyWith<$Res> {
  __$FinanceInvoiceCopyWithImpl(this._self, this._then);

  final _FinanceInvoice _self;
  final $Res Function(_FinanceInvoice) _then;

/// Create a copy of FinanceInvoice
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? patient = null,Object? source = null,Object? amount = null,Object? received = null,}) {
  return _then(_FinanceInvoice(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,patient: null == patient ? _self.patient : patient // ignore: cast_nullable_to_non_nullable
as String,source: null == source ? _self.source : source // ignore: cast_nullable_to_non_nullable
as String,amount: null == amount ? _self.amount : amount // ignore: cast_nullable_to_non_nullable
as int,received: null == received ? _self.received : received // ignore: cast_nullable_to_non_nullable
as int,
  ));
}


}

/// @nodoc
mixin _$PaymentNotification {

 String get id; String get title; String get body; bool get read;/// ISO-8601 with offset.
 String get at;
/// Create a copy of PaymentNotification
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$PaymentNotificationCopyWith<PaymentNotification> get copyWith => _$PaymentNotificationCopyWithImpl<PaymentNotification>(this as PaymentNotification, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as PaymentNotification;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is PaymentNotification&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.title, _this.title) || other.title == _this.title)&&(identical(other.body, _this.body) || other.body == _this.body)&&(identical(other.read, _this.read) || other.read == _this.read)&&(identical(other.at, _this.at) || other.at == _this.at));
}


@override
int get hashCode {
  final _this = this as PaymentNotification;
  return Object.hash(runtimeType,_this.id,_this.title,_this.body,_this.read,_this.at);
}

@override
String toString() {
  final _this = this as PaymentNotification;
  return 'PaymentNotification(id: ${_this.id}, title: ${_this.title}, body: ${_this.body}, read: ${_this.read}, at: ${_this.at})';
}


}

/// @nodoc
abstract mixin class $PaymentNotificationCopyWith<$Res>  {
  factory $PaymentNotificationCopyWith(PaymentNotification value, $Res Function(PaymentNotification) _then) = _$PaymentNotificationCopyWithImpl;
@useResult
$Res call({
 String id, String title, String body, bool read, String at
});




}
/// @nodoc
class _$PaymentNotificationCopyWithImpl<$Res>
    implements $PaymentNotificationCopyWith<$Res> {
  _$PaymentNotificationCopyWithImpl(this._self, this._then);

  final PaymentNotification _self;
  final $Res Function(PaymentNotification) _then;

/// Create a copy of PaymentNotification
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? title = null,Object? body = null,Object? read = null,Object? at = null,}) {
  return _then(PaymentNotification(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,title: null == title ? _self.title : title // ignore: cast_nullable_to_non_nullable
as String,body: null == body ? _self.body : body // ignore: cast_nullable_to_non_nullable
as String,read: null == read ? _self.read : read // ignore: cast_nullable_to_non_nullable
as bool,at: null == at ? _self.at : at // ignore: cast_nullable_to_non_nullable
as String,
  ));
}

}


/// Adds pattern-matching-related methods to [PaymentNotification].
extension PaymentNotificationPatterns on PaymentNotification {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _PaymentNotification value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _PaymentNotification() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _PaymentNotification value)  $default,){
final _that = this;
switch (_that) {
case _PaymentNotification():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _PaymentNotification value)?  $default,){
final _that = this;
switch (_that) {
case _PaymentNotification() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String title,  String body,  bool read,  String at)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _PaymentNotification() when $default != null:
return $default(_that.id,_that.title,_that.body,_that.read,_that.at);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String title,  String body,  bool read,  String at)  $default,) {final _that = this;
switch (_that) {
case _PaymentNotification():
return $default(_that.id,_that.title,_that.body,_that.read,_that.at);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String title,  String body,  bool read,  String at)?  $default,) {final _that = this;
switch (_that) {
case _PaymentNotification() when $default != null:
return $default(_that.id,_that.title,_that.body,_that.read,_that.at);case _:
  return null;

}
}

}

/// @nodoc


class _PaymentNotification extends PaymentNotification {
  const _PaymentNotification({required this.id, required this.title, required this.body, required this.read, required this.at}): super._();
  

@override final  String id;
@override final  String title;
@override final  String body;
@override final  bool read;
/// ISO-8601 with offset.
@override final  String at;

/// Create a copy of PaymentNotification
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$PaymentNotificationCopyWith<_PaymentNotification> get copyWith => __$PaymentNotificationCopyWithImpl<_PaymentNotification>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _PaymentNotification&&(identical(other.id, id) || other.id == id)&&(identical(other.title, title) || other.title == title)&&(identical(other.body, body) || other.body == body)&&(identical(other.read, read) || other.read == read)&&(identical(other.at, at) || other.at == at));
}


@override
int get hashCode {
    return Object.hash(runtimeType,id,title,body,read,at);
}

@override
String toString() {
    return 'PaymentNotification(id: $id, title: $title, body: $body, read: $read, at: $at)';
}


}

/// @nodoc
abstract mixin class _$PaymentNotificationCopyWith<$Res> implements $PaymentNotificationCopyWith<$Res> {
  factory _$PaymentNotificationCopyWith(_PaymentNotification value, $Res Function(_PaymentNotification) _then) = __$PaymentNotificationCopyWithImpl;
@override @useResult
$Res call({
 String id, String title, String body, bool read, String at
});




}
/// @nodoc
class __$PaymentNotificationCopyWithImpl<$Res>
    implements _$PaymentNotificationCopyWith<$Res> {
  __$PaymentNotificationCopyWithImpl(this._self, this._then);

  final _PaymentNotification _self;
  final $Res Function(_PaymentNotification) _then;

/// Create a copy of PaymentNotification
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? title = null,Object? body = null,Object? read = null,Object? at = null,}) {
  return _then(_PaymentNotification(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,title: null == title ? _self.title : title // ignore: cast_nullable_to_non_nullable
as String,body: null == body ? _self.body : body // ignore: cast_nullable_to_non_nullable
as String,read: null == read ? _self.read : read // ignore: cast_nullable_to_non_nullable
as bool,at: null == at ? _self.at : at // ignore: cast_nullable_to_non_nullable
as String,
  ));
}


}

/// @nodoc
mixin _$FinanceSnapshot {

 String get month; String get today;/// `open`, `closed` or `paid`.
 String get periodStatus; FinanceSummary get summary; List<FinanceDoctor> get doctors; List<ProcedureService> get services; List<ProcedureRow> get rows; List<FinanceInvoice> get invoices; List<PaymentNotification> get notifications;
/// Create a copy of FinanceSnapshot
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$FinanceSnapshotCopyWith<FinanceSnapshot> get copyWith => _$FinanceSnapshotCopyWithImpl<FinanceSnapshot>(this as FinanceSnapshot, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as FinanceSnapshot;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is FinanceSnapshot&&(identical(other.month, _this.month) || other.month == _this.month)&&(identical(other.today, _this.today) || other.today == _this.today)&&(identical(other.periodStatus, _this.periodStatus) || other.periodStatus == _this.periodStatus)&&(identical(other.summary, _this.summary) || other.summary == _this.summary)&&const DeepCollectionEquality().equals(other.doctors, _this.doctors)&&const DeepCollectionEquality().equals(other.services, _this.services)&&const DeepCollectionEquality().equals(other.rows, _this.rows)&&const DeepCollectionEquality().equals(other.invoices, _this.invoices)&&const DeepCollectionEquality().equals(other.notifications, _this.notifications));
}


@override
int get hashCode {
  final _this = this as FinanceSnapshot;
  return Object.hash(runtimeType,_this.month,_this.today,_this.periodStatus,_this.summary,const DeepCollectionEquality().hash(_this.doctors),const DeepCollectionEquality().hash(_this.services),const DeepCollectionEquality().hash(_this.rows),const DeepCollectionEquality().hash(_this.invoices),const DeepCollectionEquality().hash(_this.notifications));
}

@override
String toString() {
  final _this = this as FinanceSnapshot;
  return 'FinanceSnapshot(month: ${_this.month}, today: ${_this.today}, periodStatus: ${_this.periodStatus}, summary: ${_this.summary}, doctors: ${_this.doctors}, services: ${_this.services}, rows: ${_this.rows}, invoices: ${_this.invoices}, notifications: ${_this.notifications})';
}


}

/// @nodoc
abstract mixin class $FinanceSnapshotCopyWith<$Res>  {
  factory $FinanceSnapshotCopyWith(FinanceSnapshot value, $Res Function(FinanceSnapshot) _then) = _$FinanceSnapshotCopyWithImpl;
@useResult
$Res call({
 String month, String today, String periodStatus, FinanceSummary summary, List<FinanceDoctor> doctors, List<ProcedureService> services, List<ProcedureRow> rows, List<FinanceInvoice> invoices, List<PaymentNotification> notifications
});


$FinanceSummaryCopyWith<$Res> get summary;

}
/// @nodoc
class _$FinanceSnapshotCopyWithImpl<$Res>
    implements $FinanceSnapshotCopyWith<$Res> {
  _$FinanceSnapshotCopyWithImpl(this._self, this._then);

  final FinanceSnapshot _self;
  final $Res Function(FinanceSnapshot) _then;

/// Create a copy of FinanceSnapshot
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? month = null,Object? today = null,Object? periodStatus = null,Object? summary = null,Object? doctors = null,Object? services = null,Object? rows = null,Object? invoices = null,Object? notifications = null,}) {
  return _then(FinanceSnapshot(
month: null == month ? _self.month : month // ignore: cast_nullable_to_non_nullable
as String,today: null == today ? _self.today : today // ignore: cast_nullable_to_non_nullable
as String,periodStatus: null == periodStatus ? _self.periodStatus : periodStatus // ignore: cast_nullable_to_non_nullable
as String,summary: null == summary ? _self.summary : summary // ignore: cast_nullable_to_non_nullable
as FinanceSummary,doctors: null == doctors ? _self.doctors : doctors // ignore: cast_nullable_to_non_nullable
as List<FinanceDoctor>,services: null == services ? _self.services : services // ignore: cast_nullable_to_non_nullable
as List<ProcedureService>,rows: null == rows ? _self.rows : rows // ignore: cast_nullable_to_non_nullable
as List<ProcedureRow>,invoices: null == invoices ? _self.invoices : invoices // ignore: cast_nullable_to_non_nullable
as List<FinanceInvoice>,notifications: null == notifications ? _self.notifications : notifications // ignore: cast_nullable_to_non_nullable
as List<PaymentNotification>,
  ));
}
/// Create a copy of FinanceSnapshot
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$FinanceSummaryCopyWith<$Res> get summary {
  
  return $FinanceSummaryCopyWith<$Res>(_self.summary, (value) {
    return _then(_self.copyWith(summary: value));
  });
}
}


/// Adds pattern-matching-related methods to [FinanceSnapshot].
extension FinanceSnapshotPatterns on FinanceSnapshot {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _FinanceSnapshot value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _FinanceSnapshot() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _FinanceSnapshot value)  $default,){
final _that = this;
switch (_that) {
case _FinanceSnapshot():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _FinanceSnapshot value)?  $default,){
final _that = this;
switch (_that) {
case _FinanceSnapshot() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String month,  String today,  String periodStatus,  FinanceSummary summary,  List<FinanceDoctor> doctors,  List<ProcedureService> services,  List<ProcedureRow> rows,  List<FinanceInvoice> invoices,  List<PaymentNotification> notifications)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _FinanceSnapshot() when $default != null:
return $default(_that.month,_that.today,_that.periodStatus,_that.summary,_that.doctors,_that.services,_that.rows,_that.invoices,_that.notifications);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String month,  String today,  String periodStatus,  FinanceSummary summary,  List<FinanceDoctor> doctors,  List<ProcedureService> services,  List<ProcedureRow> rows,  List<FinanceInvoice> invoices,  List<PaymentNotification> notifications)  $default,) {final _that = this;
switch (_that) {
case _FinanceSnapshot():
return $default(_that.month,_that.today,_that.periodStatus,_that.summary,_that.doctors,_that.services,_that.rows,_that.invoices,_that.notifications);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String month,  String today,  String periodStatus,  FinanceSummary summary,  List<FinanceDoctor> doctors,  List<ProcedureService> services,  List<ProcedureRow> rows,  List<FinanceInvoice> invoices,  List<PaymentNotification> notifications)?  $default,) {final _that = this;
switch (_that) {
case _FinanceSnapshot() when $default != null:
return $default(_that.month,_that.today,_that.periodStatus,_that.summary,_that.doctors,_that.services,_that.rows,_that.invoices,_that.notifications);case _:
  return null;

}
}

}

/// @nodoc


class _FinanceSnapshot extends FinanceSnapshot {
  const _FinanceSnapshot({required this.month, required this.today, required this.periodStatus, required this.summary,  List<FinanceDoctor> doctors = const [],  List<ProcedureService> services = const [],  List<ProcedureRow> rows = const [],  List<FinanceInvoice> invoices = const [],  List<PaymentNotification> notifications = const []}): _doctors = doctors,_services = services,_rows = rows,_invoices = invoices,_notifications = notifications,super._();
  

@override final  String month;
@override final  String today;
/// `open`, `closed` or `paid`.
@override final  String periodStatus;
@override final  FinanceSummary summary;
 final  List<FinanceDoctor> _doctors;
@override@JsonKey() List<FinanceDoctor> get doctors {
  if (_doctors is EqualUnmodifiableListView) return _doctors;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_doctors);
}

 final  List<ProcedureService> _services;
@override@JsonKey() List<ProcedureService> get services {
  if (_services is EqualUnmodifiableListView) return _services;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_services);
}

 final  List<ProcedureRow> _rows;
@override@JsonKey() List<ProcedureRow> get rows {
  if (_rows is EqualUnmodifiableListView) return _rows;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_rows);
}

 final  List<FinanceInvoice> _invoices;
@override@JsonKey() List<FinanceInvoice> get invoices {
  if (_invoices is EqualUnmodifiableListView) return _invoices;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_invoices);
}

 final  List<PaymentNotification> _notifications;
@override@JsonKey() List<PaymentNotification> get notifications {
  if (_notifications is EqualUnmodifiableListView) return _notifications;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_notifications);
}


/// Create a copy of FinanceSnapshot
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$FinanceSnapshotCopyWith<_FinanceSnapshot> get copyWith => __$FinanceSnapshotCopyWithImpl<_FinanceSnapshot>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _FinanceSnapshot&&(identical(other.month, month) || other.month == month)&&(identical(other.today, today) || other.today == today)&&(identical(other.periodStatus, periodStatus) || other.periodStatus == periodStatus)&&(identical(other.summary, summary) || other.summary == summary)&&const DeepCollectionEquality().equals(other.doctors, _doctors)&&const DeepCollectionEquality().equals(other.services, _services)&&const DeepCollectionEquality().equals(other.rows, _rows)&&const DeepCollectionEquality().equals(other.invoices, _invoices)&&const DeepCollectionEquality().equals(other.notifications, _notifications));
}


@override
int get hashCode {
    return Object.hash(runtimeType,month,today,periodStatus,summary,const DeepCollectionEquality().hash(_doctors),const DeepCollectionEquality().hash(_services),const DeepCollectionEquality().hash(_rows),const DeepCollectionEquality().hash(_invoices),const DeepCollectionEquality().hash(_notifications));
}

@override
String toString() {
    return 'FinanceSnapshot(month: $month, today: $today, periodStatus: $periodStatus, summary: $summary, doctors: $doctors, services: $services, rows: $rows, invoices: $invoices, notifications: $notifications)';
}


}

/// @nodoc
abstract mixin class _$FinanceSnapshotCopyWith<$Res> implements $FinanceSnapshotCopyWith<$Res> {
  factory _$FinanceSnapshotCopyWith(_FinanceSnapshot value, $Res Function(_FinanceSnapshot) _then) = __$FinanceSnapshotCopyWithImpl;
@override @useResult
$Res call({
 String month, String today, String periodStatus, FinanceSummary summary, List<FinanceDoctor> doctors, List<ProcedureService> services, List<ProcedureRow> rows, List<FinanceInvoice> invoices, List<PaymentNotification> notifications
});


@override $FinanceSummaryCopyWith<$Res> get summary;

}
/// @nodoc
class __$FinanceSnapshotCopyWithImpl<$Res>
    implements _$FinanceSnapshotCopyWith<$Res> {
  __$FinanceSnapshotCopyWithImpl(this._self, this._then);

  final _FinanceSnapshot _self;
  final $Res Function(_FinanceSnapshot) _then;

/// Create a copy of FinanceSnapshot
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? month = null,Object? today = null,Object? periodStatus = null,Object? summary = null,Object? doctors = null,Object? services = null,Object? rows = null,Object? invoices = null,Object? notifications = null,}) {
  return _then(_FinanceSnapshot(
month: null == month ? _self.month : month // ignore: cast_nullable_to_non_nullable
as String,today: null == today ? _self.today : today // ignore: cast_nullable_to_non_nullable
as String,periodStatus: null == periodStatus ? _self.periodStatus : periodStatus // ignore: cast_nullable_to_non_nullable
as String,summary: null == summary ? _self.summary : summary // ignore: cast_nullable_to_non_nullable
as FinanceSummary,doctors: null == doctors ? _self._doctors : doctors // ignore: cast_nullable_to_non_nullable
as List<FinanceDoctor>,services: null == services ? _self._services : services // ignore: cast_nullable_to_non_nullable
as List<ProcedureService>,rows: null == rows ? _self._rows : rows // ignore: cast_nullable_to_non_nullable
as List<ProcedureRow>,invoices: null == invoices ? _self._invoices : invoices // ignore: cast_nullable_to_non_nullable
as List<FinanceInvoice>,notifications: null == notifications ? _self._notifications : notifications // ignore: cast_nullable_to_non_nullable
as List<PaymentNotification>,
  ));
}

/// Create a copy of FinanceSnapshot
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$FinanceSummaryCopyWith<$Res> get summary {
  
  return $FinanceSummaryCopyWith<$Res>(_self.summary, (value) {
    return _then(_self.copyWith(summary: value));
  });
}
}

// dart format on
