// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'patient_profile.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$CareTask {

 String get id; String get type; String get title; String get status;
/// Create a copy of CareTask
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$CareTaskCopyWith<CareTask> get copyWith => _$CareTaskCopyWithImpl<CareTask>(this as CareTask, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as CareTask;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is CareTask&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.type, _this.type) || other.type == _this.type)&&(identical(other.title, _this.title) || other.title == _this.title)&&(identical(other.status, _this.status) || other.status == _this.status));
}


@override
int get hashCode {
  final _this = this as CareTask;
  return Object.hash(runtimeType,_this.id,_this.type,_this.title,_this.status);
}

@override
String toString() {
  final _this = this as CareTask;
  return 'CareTask(id: ${_this.id}, type: ${_this.type}, title: ${_this.title}, status: ${_this.status})';
}


}

/// @nodoc
abstract mixin class $CareTaskCopyWith<$Res>  {
  factory $CareTaskCopyWith(CareTask value, $Res Function(CareTask) _then) = _$CareTaskCopyWithImpl;
@useResult
$Res call({
 String id, String type, String title, String status
});




}
/// @nodoc
class _$CareTaskCopyWithImpl<$Res>
    implements $CareTaskCopyWith<$Res> {
  _$CareTaskCopyWithImpl(this._self, this._then);

  final CareTask _self;
  final $Res Function(CareTask) _then;

/// Create a copy of CareTask
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? type = null,Object? title = null,Object? status = null,}) {
  return _then(CareTask(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,type: null == type ? _self.type : type // ignore: cast_nullable_to_non_nullable
as String,title: null == title ? _self.title : title // ignore: cast_nullable_to_non_nullable
as String,status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,
  ));
}

}


/// Adds pattern-matching-related methods to [CareTask].
extension CareTaskPatterns on CareTask {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _CareTask value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _CareTask() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _CareTask value)  $default,){
final _that = this;
switch (_that) {
case _CareTask():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _CareTask value)?  $default,){
final _that = this;
switch (_that) {
case _CareTask() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String type,  String title,  String status)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _CareTask() when $default != null:
return $default(_that.id,_that.type,_that.title,_that.status);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String type,  String title,  String status)  $default,) {final _that = this;
switch (_that) {
case _CareTask():
return $default(_that.id,_that.type,_that.title,_that.status);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String type,  String title,  String status)?  $default,) {final _that = this;
switch (_that) {
case _CareTask() when $default != null:
return $default(_that.id,_that.type,_that.title,_that.status);case _:
  return null;

}
}

}

/// @nodoc


class _CareTask implements CareTask {
  const _CareTask({required this.id, required this.type, required this.title, required this.status});
  

@override final  String id;
@override final  String type;
@override final  String title;
@override final  String status;

/// Create a copy of CareTask
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$CareTaskCopyWith<_CareTask> get copyWith => __$CareTaskCopyWithImpl<_CareTask>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _CareTask&&(identical(other.id, id) || other.id == id)&&(identical(other.type, type) || other.type == type)&&(identical(other.title, title) || other.title == title)&&(identical(other.status, status) || other.status == status));
}


@override
int get hashCode {
    return Object.hash(runtimeType,id,type,title,status);
}

@override
String toString() {
    return 'CareTask(id: $id, type: $type, title: $title, status: $status)';
}


}

/// @nodoc
abstract mixin class _$CareTaskCopyWith<$Res> implements $CareTaskCopyWith<$Res> {
  factory _$CareTaskCopyWith(_CareTask value, $Res Function(_CareTask) _then) = __$CareTaskCopyWithImpl;
@override @useResult
$Res call({
 String id, String type, String title, String status
});




}
/// @nodoc
class __$CareTaskCopyWithImpl<$Res>
    implements _$CareTaskCopyWith<$Res> {
  __$CareTaskCopyWithImpl(this._self, this._then);

  final _CareTask _self;
  final $Res Function(_CareTask) _then;

/// Create a copy of CareTask
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? type = null,Object? title = null,Object? status = null,}) {
  return _then(_CareTask(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,type: null == type ? _self.type : type // ignore: cast_nullable_to_non_nullable
as String,title: null == title ? _self.title : title // ignore: cast_nullable_to_non_nullable
as String,status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as String,
  ));
}


}

/// @nodoc
mixin _$PatientProfile {

 String get id; String get name; String get doctor; int get sessions; int get totalSessions; String get appointment; String get day;/// CSKH group key (`d1`, `due`, ...); empty when not in the care queue.
 String get careGroup;/// Human label of [careGroup] shown in account pickers.
 String get caseLabel; List<CareTask> get tasks;
/// Create a copy of PatientProfile
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$PatientProfileCopyWith<PatientProfile> get copyWith => _$PatientProfileCopyWithImpl<PatientProfile>(this as PatientProfile, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as PatientProfile;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is PatientProfile&&(identical(other.id, _this.id) || other.id == _this.id)&&(identical(other.name, _this.name) || other.name == _this.name)&&(identical(other.doctor, _this.doctor) || other.doctor == _this.doctor)&&(identical(other.sessions, _this.sessions) || other.sessions == _this.sessions)&&(identical(other.totalSessions, _this.totalSessions) || other.totalSessions == _this.totalSessions)&&(identical(other.appointment, _this.appointment) || other.appointment == _this.appointment)&&(identical(other.day, _this.day) || other.day == _this.day)&&(identical(other.careGroup, _this.careGroup) || other.careGroup == _this.careGroup)&&(identical(other.caseLabel, _this.caseLabel) || other.caseLabel == _this.caseLabel)&&const DeepCollectionEquality().equals(other.tasks, _this.tasks));
}


@override
int get hashCode {
  final _this = this as PatientProfile;
  return Object.hash(runtimeType,_this.id,_this.name,_this.doctor,_this.sessions,_this.totalSessions,_this.appointment,_this.day,_this.careGroup,_this.caseLabel,const DeepCollectionEquality().hash(_this.tasks));
}

@override
String toString() {
  final _this = this as PatientProfile;
  return 'PatientProfile(id: ${_this.id}, name: ${_this.name}, doctor: ${_this.doctor}, sessions: ${_this.sessions}, totalSessions: ${_this.totalSessions}, appointment: ${_this.appointment}, day: ${_this.day}, careGroup: ${_this.careGroup}, caseLabel: ${_this.caseLabel}, tasks: ${_this.tasks})';
}


}

/// @nodoc
abstract mixin class $PatientProfileCopyWith<$Res>  {
  factory $PatientProfileCopyWith(PatientProfile value, $Res Function(PatientProfile) _then) = _$PatientProfileCopyWithImpl;
@useResult
$Res call({
 String id, String name, String doctor, int sessions, int totalSessions, String appointment, String day, String careGroup, String caseLabel, List<CareTask> tasks
});




}
/// @nodoc
class _$PatientProfileCopyWithImpl<$Res>
    implements $PatientProfileCopyWith<$Res> {
  _$PatientProfileCopyWithImpl(this._self, this._then);

  final PatientProfile _self;
  final $Res Function(PatientProfile) _then;

/// Create a copy of PatientProfile
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? id = null,Object? name = null,Object? doctor = null,Object? sessions = null,Object? totalSessions = null,Object? appointment = null,Object? day = null,Object? careGroup = null,Object? caseLabel = null,Object? tasks = null,}) {
  return _then(PatientProfile(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,doctor: null == doctor ? _self.doctor : doctor // ignore: cast_nullable_to_non_nullable
as String,sessions: null == sessions ? _self.sessions : sessions // ignore: cast_nullable_to_non_nullable
as int,totalSessions: null == totalSessions ? _self.totalSessions : totalSessions // ignore: cast_nullable_to_non_nullable
as int,appointment: null == appointment ? _self.appointment : appointment // ignore: cast_nullable_to_non_nullable
as String,day: null == day ? _self.day : day // ignore: cast_nullable_to_non_nullable
as String,careGroup: null == careGroup ? _self.careGroup : careGroup // ignore: cast_nullable_to_non_nullable
as String,caseLabel: null == caseLabel ? _self.caseLabel : caseLabel // ignore: cast_nullable_to_non_nullable
as String,tasks: null == tasks ? _self.tasks : tasks // ignore: cast_nullable_to_non_nullable
as List<CareTask>,
  ));
}

}


/// Adds pattern-matching-related methods to [PatientProfile].
extension PatientProfilePatterns on PatientProfile {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _PatientProfile value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _PatientProfile() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _PatientProfile value)  $default,){
final _that = this;
switch (_that) {
case _PatientProfile():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _PatientProfile value)?  $default,){
final _that = this;
switch (_that) {
case _PatientProfile() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String id,  String name,  String doctor,  int sessions,  int totalSessions,  String appointment,  String day,  String careGroup,  String caseLabel,  List<CareTask> tasks)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _PatientProfile() when $default != null:
return $default(_that.id,_that.name,_that.doctor,_that.sessions,_that.totalSessions,_that.appointment,_that.day,_that.careGroup,_that.caseLabel,_that.tasks);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String id,  String name,  String doctor,  int sessions,  int totalSessions,  String appointment,  String day,  String careGroup,  String caseLabel,  List<CareTask> tasks)  $default,) {final _that = this;
switch (_that) {
case _PatientProfile():
return $default(_that.id,_that.name,_that.doctor,_that.sessions,_that.totalSessions,_that.appointment,_that.day,_that.careGroup,_that.caseLabel,_that.tasks);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String id,  String name,  String doctor,  int sessions,  int totalSessions,  String appointment,  String day,  String careGroup,  String caseLabel,  List<CareTask> tasks)?  $default,) {final _that = this;
switch (_that) {
case _PatientProfile() when $default != null:
return $default(_that.id,_that.name,_that.doctor,_that.sessions,_that.totalSessions,_that.appointment,_that.day,_that.careGroup,_that.caseLabel,_that.tasks);case _:
  return null;

}
}

}

/// @nodoc


class _PatientProfile extends PatientProfile {
  const _PatientProfile({required this.id, required this.name, required this.doctor, required this.sessions, required this.totalSessions, required this.appointment, required this.day, required this.careGroup, required this.caseLabel,  List<CareTask> tasks = const []}): _tasks = tasks,super._();
  

@override final  String id;
@override final  String name;
@override final  String doctor;
@override final  int sessions;
@override final  int totalSessions;
@override final  String appointment;
@override final  String day;
/// CSKH group key (`d1`, `due`, ...); empty when not in the care queue.
@override final  String careGroup;
/// Human label of [careGroup] shown in account pickers.
@override final  String caseLabel;
 final  List<CareTask> _tasks;
@override@JsonKey() List<CareTask> get tasks {
  if (_tasks is EqualUnmodifiableListView) return _tasks;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableListView(_tasks);
}


/// Create a copy of PatientProfile
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$PatientProfileCopyWith<_PatientProfile> get copyWith => __$PatientProfileCopyWithImpl<_PatientProfile>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _PatientProfile&&(identical(other.id, id) || other.id == id)&&(identical(other.name, name) || other.name == name)&&(identical(other.doctor, doctor) || other.doctor == doctor)&&(identical(other.sessions, sessions) || other.sessions == sessions)&&(identical(other.totalSessions, totalSessions) || other.totalSessions == totalSessions)&&(identical(other.appointment, appointment) || other.appointment == appointment)&&(identical(other.day, day) || other.day == day)&&(identical(other.careGroup, careGroup) || other.careGroup == careGroup)&&(identical(other.caseLabel, caseLabel) || other.caseLabel == caseLabel)&&const DeepCollectionEquality().equals(other.tasks, _tasks));
}


@override
int get hashCode {
    return Object.hash(runtimeType,id,name,doctor,sessions,totalSessions,appointment,day,careGroup,caseLabel,const DeepCollectionEquality().hash(_tasks));
}

@override
String toString() {
    return 'PatientProfile(id: $id, name: $name, doctor: $doctor, sessions: $sessions, totalSessions: $totalSessions, appointment: $appointment, day: $day, careGroup: $careGroup, caseLabel: $caseLabel, tasks: $tasks)';
}


}

/// @nodoc
abstract mixin class _$PatientProfileCopyWith<$Res> implements $PatientProfileCopyWith<$Res> {
  factory _$PatientProfileCopyWith(_PatientProfile value, $Res Function(_PatientProfile) _then) = __$PatientProfileCopyWithImpl;
@override @useResult
$Res call({
 String id, String name, String doctor, int sessions, int totalSessions, String appointment, String day, String careGroup, String caseLabel, List<CareTask> tasks
});




}
/// @nodoc
class __$PatientProfileCopyWithImpl<$Res>
    implements _$PatientProfileCopyWith<$Res> {
  __$PatientProfileCopyWithImpl(this._self, this._then);

  final _PatientProfile _self;
  final $Res Function(_PatientProfile) _then;

/// Create a copy of PatientProfile
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? id = null,Object? name = null,Object? doctor = null,Object? sessions = null,Object? totalSessions = null,Object? appointment = null,Object? day = null,Object? careGroup = null,Object? caseLabel = null,Object? tasks = null,}) {
  return _then(_PatientProfile(
id: null == id ? _self.id : id // ignore: cast_nullable_to_non_nullable
as String,name: null == name ? _self.name : name // ignore: cast_nullable_to_non_nullable
as String,doctor: null == doctor ? _self.doctor : doctor // ignore: cast_nullable_to_non_nullable
as String,sessions: null == sessions ? _self.sessions : sessions // ignore: cast_nullable_to_non_nullable
as int,totalSessions: null == totalSessions ? _self.totalSessions : totalSessions // ignore: cast_nullable_to_non_nullable
as int,appointment: null == appointment ? _self.appointment : appointment // ignore: cast_nullable_to_non_nullable
as String,day: null == day ? _self.day : day // ignore: cast_nullable_to_non_nullable
as String,careGroup: null == careGroup ? _self.careGroup : careGroup // ignore: cast_nullable_to_non_nullable
as String,caseLabel: null == caseLabel ? _self.caseLabel : caseLabel // ignore: cast_nullable_to_non_nullable
as String,tasks: null == tasks ? _self._tasks : tasks // ignore: cast_nullable_to_non_nullable
as List<CareTask>,
  ));
}


}

// dart format on
