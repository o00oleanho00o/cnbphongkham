/* Domain logic only: deterministic projections, protocol tasks and atomic commands. */
(() => {
  const P=window.Pema, O=window.PemaOps, D=window.PemaCRMData;
  const open=t=>['open','rescheduled'].includes(t.status);
  const upcoming=p=>O.seed().appointments.filter(a=>a.patient===p.id&&O.active(a)&&!['completed'].includes(a.status)&&a.date>=D.DAY).sort((a,b)=>(a.date+a.time).localeCompare(b.date+b.time));
  const outcomes={unanswered:'Không nghe máy',callback:'Gọi lại sau',no_need:'Đã liên hệ, chưa có nhu cầu',busy:'Đang bận, hẹn gọi lại',booked:'Đồng ý đặt lịch',doctor:'Muốn bác sĩ tư vấn',reaction:'Có phản hồi sau điều trị',complaint:'Khiếu nại',optout:'Không muốn nhận CSKH',invalid:'Sai số / không liên hệ được'};
  const sources={doctor_recommendation:'Bác sĩ khuyến nghị',service_protocol:'Protocol dịch vụ',treatment_plan:'Kế hoạch điều trị',appointment:'Lịch đã đặt',followup_automation:'Chăm sóc sau điều trị'};
  const stageLabels={new:'Khách mới',returning:'Khách quay lại',treating:'Đang điều trị',dormant:'Lâu chưa quay lại',reactivated:'Đã quay lại sau CSKH'};
  const stamp=()=>D.DAY+'T'+new Date(Date.UTC(2000,0,1,9,0,++P.state.crmSequence)).toISOString().slice(11,19)+'+07:00';
  function profile(p) {
    const c=p.crm, next=upcoming(p)[0], expected=next?.date||c.recommendationAt||null;
    const age=p.lastVisit?D.days(p.lastVisit):0, remaining=Math.max(0,p.total-p.completed);
    const overdue=expected?Math.max(0,D.days(expected)):0;
    const lifecycleStage=c.reactivatedAt?'reactivated':!p.sessions.length?'new':age>=90?'dormant':remaining?'treating':'returning';
    return {...c,lastVisitAt:p.lastVisit,expectedNextVisitAt:expected,expectedVisitSource:next?'appointment':c.expectedVisitSource,expectedVisitReason:next?'Lịch hẹn đã xác nhận với phòng khám':c.expectedVisitReason,overdueDays:overdue,lifecycleStage,remaining,riskLevel:!next&&(overdue>7||remaining>0&&age>45)?'high':'normal',age};
  }
  function refresh() {
    D.seed();
    for (const p of P.state.patients) {
      const reception=O.seed().appointments.find(a=>a.patient===p.id&&a.date===D.DAY&&O.active(a));
      p.status=reception?({booked:'Đặt hẹn',confirmed:'Đã xác nhận',arrived:'Đang chờ',in_progress:'Đang điều trị',completed:'Hoàn tất'}[reception.status]||'Đặt hẹn'):'Chưa có lịch hôm nay';
      const latest=p.sessions.slice().sort((a,b)=>b.date.localeCompare(a.date))[0];
      if(latest&&p.crm.lastProtocolSession!==latest.id&&latest.protocolId==='laser-co2') {
        p.crm.recommendationAt=D.addDays(latest.date,30);p.crm.expectedVisitSource='service_protocol';p.crm.expectedVisitReason='Đánh giá D+30 sau Laser CO2';p.crm.lastProtocolSession=latest.id;
      }
      const x=profile(p);Object.assign(p.crm,{expectedNextVisitAt:x.expectedNextVisitAt,overdueDays:x.overdueDays,lifecycleStage:x.lifecycleStage,riskLevel:x.riskLevel,lastVisitAt:x.lastVisitAt});
      for(const plan of p.servicePlans||[]) {plan.economics ||= {consultant:null,doctor:plan.doctor||p.doctor,technician:null,serviceValue:plan.agreedPrice,commissionRuleId:null,consumables:[]};}
    }
  }
  function run() {
    refresh();const s=P.state, candidates=[];
    function task(rule,p,source,due,related={}) {
      if(!rule.active||rule.conditions.marketing&&p.crm.marketingOptOut)return;
      candidates.push({id:`CRM:${rule.id}:${p.id}:${source}`,patientId:p.id,ruleId:rule.id,type:rule.id,reason:rule.name,priority:rule.priority,createdAt:D.DAY+'T08:00:00+07:00',dueAt:due+'T09:00:00+07:00',status:'open',owner:rule.id==='d7'?p.doctor:p.crm.owner,suggestedAction:rule.suggestedAction,sourceEventId:source,...related});
    }
    for(const p of s.patients) {
      const x=profile(p), future=upcoming(p), latest=p.sessions.slice().sort((a,b)=>b.date.localeCompare(a.date))[0];
      for(const r of s.crmAutomationRules) {
        if(['d1','d3','d7'].includes(r.id)&&latest?.protocolId==='laser-co2'&&D.days(latest.date)>=0&&D.days(latest.date)<=45)task(r,p,latest.id,D.addDays(latest.date,r.delayDays));
        if(r.id==='due'&&x.expectedNextVisitAt===D.DAY&&!future.some(a=>a.date===D.DAY&&['arrived','in_progress'].includes(a.status)))task(r,p,x.expectedNextVisitAt,D.DAY);
        if(r.id==='overdue'&&x.overdueDays>0)task(r,p,x.expectedNextVisitAt,x.expectedNextVisitAt);
        if(r.id==='no_show'&&!future.length) {
          const a=O.seed().appointments.filter(a=>a.patient===p.id&&['missed','cancelled'].includes(a.status)&&Date.parse(D.DAY+'T09:00:00+07:00')-Date.parse(a.cancelledAt||a.missedAt||a.date+'T'+a.time+':00+07:00')>=86400000).sort((a,b)=>b.date.localeCompare(a.date))[0];
          if(a)task(r,p,a.id,D.addDays((a.cancelledAt||a.date).slice(0,10),1),{relatedAppointmentId:a.id});
        }
        if(r.id==='abandoned'&&x.remaining>0&&x.age>r.delayDays&&!future.length)task(r,p,latest?.id||p.lastVisit,D.addDays(p.lastVisit,r.delayDays),{relatedPlanId:p.servicePlans?.[0]?.id||'LP-'+p.id});
        if(r.id==='dormant90'&&x.age>=90&&x.age<180&&!future.length||r.id==='dormant180'&&x.age>=180&&!future.length)task(r,p,p.lastVisit,D.addDays(p.lastVisit,r.delayDays));
        if(r.id==='birthday'&&p.crm.birthday) {
          let birthday=D.DAY.slice(0,4)+p.crm.birthday.slice(4);if(birthday<D.DAY)birthday=(Number(D.DAY.slice(0,4))+1)+p.crm.birthday.slice(4);
          if(D.days(D.DAY,birthday)<=r.delayDays)task(r,p,birthday,birthday);
        }
      }
    }
    const ids=new Set(s.crmTasks.map(t=>t.id)), eligible=new Set(candidates.map(t=>t.id));
    for(const c of candidates)if(!ids.has(c.id)){s.crmTasks.push(c);ids.add(c.id);}
    for(const t of s.crmTasks)if(open(t)&&t.ruleId!=='manual'&&!eligible.has(t.id)){t.status='superseded';t.resolution='Nguồn đã đổi: có lịch mới, mốc mới hoặc opt-out';t.resolvedAt=D.DAY+'T09:00:00+07:00';}
    return s.crmTasks;
  }
  function ensure() {
    O.seed();const before=JSON.stringify(P.state);run();
    if(before!==JSON.stringify(P.state)&&!P.save()){const s=P.state;Object.keys(s).forEach(k=>delete s[k]);Object.assign(s,JSON.parse(before));throw Error('Không lưu được dữ liệu CRM.');}
  }
  function queue(filter={}) {
    const rank=t=>['d1','d3','d7'].includes(t.type)?0:1;
    return P.state.crmTasks.filter(t=>open(t)&&(filter.allDates||t.dueAt.slice(0,10)<=D.DAY||t.type==='birthday')&&(!filter.rule||filter.rule==='all'||t.type===filter.rule)&&(!filter.owner||filter.owner==='all'||t.owner===filter.owner)&&(!filter.patient||t.patientId===filter.patient)).sort((a,b)=>rank(a)-rank(b)||({high:0,normal:1,low:2}[a.priority]-{high:0,normal:1,low:2}[b.priority])||a.dueAt.localeCompare(b.dueAt));
  }
  function addActivity(t,input,appointment) {
    const p=P.patient(t.patientId), at=stamp();
    const a={id:'CA-'+P.state.crmSequence,patientId:p.id,taskId:t.id,type:input.outcome==='complaint'?'complaint':'cskh',channel:input.channel,outcome:input.outcome,note:input.note.trim(),actor:window.PemaStaff?(PemaStaff.current().owner||PemaStaff.current().name):input.owner,occurredAt:at,nextActionAt:input.nextActionAt||null,relatedAppointmentId:appointment?.id||null};
    P.state.crmActivities.unshift(a);p.crm.lastContactAt=at;p.crm.latestOutcome=input.outcome;
    p.crm.nextActionAt=a.nextActionAt;p.crm.nextActionType=input.nextActionType||null;p.crm.owner=input.owner;
    // Internal outreach logs are never published as patient-facing clinical advice.
    P.log('CSKH · '+outcomes[input.outcome],p.id);
    return a;
  }
  function validate(t,input,booking=false) {
    window.PemaStaff?.assert('crm');
    if(window.PemaStaff?.current().role==='doctor'&&(!t||t.type!=='d7'||!PemaStaff.owns(P.patient(t.patientId))))throw Error('Tài khoản bác sĩ chỉ xử lý review D+7 của hồ sơ phụ trách.');
    if(!t||!open(t))throw Error('Việc đã được xử lý hoặc không còn hợp lệ. Tải lại danh sách.');
    if(!outcomes[input.outcome]||!['Gọi điện','Zalo','SMS','Ghi chú nội bộ'].includes(input.channel)||!input.owner?.trim()||!input.note?.trim())throw Error('Chọn kênh, kết quả, người phụ trách và nhập ghi chú.');
    if(input.outcome==='booked'&&!booking)throw Error('Cần lưu lịch hẹn hợp lệ trước khi hoàn tất việc.');
    if(['unanswered','callback','busy'].includes(input.outcome)&&!input.nextActionAt)throw Error('Cần ngày giờ gọi lại.');
    if(input.nextActionAt&&(!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(input.nextActionAt)||!Number.isFinite(Date.parse(input.nextActionAt))||input.nextActionAt<=D.DAY+'T09:00'))throw Error('Bước tiếp theo phải sau 09:00 ngày demo, đúng ngày giờ.');
  }
  function finish(t,input,appointment) {
    validate(t,input,!!appointment);const p=P.patient(t.patientId), wasDormant=profile(p).age>=90;
    const a=addActivity(t,input,appointment);
    t.status=input.nextActionAt&&!appointment?'rescheduled':'resolved';t.owner=input.owner;t.priority=input.priority||t.priority;t.resolution=input.outcome;t.resolvedAt=t.status==='resolved'?a.occurredAt:null;
    if(t.status==='rescheduled')t.dueAt=input.nextActionAt+'+07:00';
    if(appointment){t.relatedAppointmentId=appointment.id;p.crm.bookedAfterCareAt=a.occurredAt;p.crm.reactivationPending=wasDormant;}
    if(input.outcome==='optout'){p.crm.marketingOptOut=true;}
    if(['doctor','reaction','complaint'].includes(input.outcome)) {
      P.state.followups.unshift({id:'CRM-F-'+a.id,patient:p.id,type:input.outcome==='complaint'?'Khiếu nại cần xử lý':'CSKH chuyển bác sĩ',priority:'review',symptom:input.note.trim(),date:a.occurredAt,status:'open',owner:p.doctor,crmActivityId:a.id,image:null});
    }
    run();return a;
  }
  function resolve(id,input) {return O.transact(()=>{run();const t=P.state.crmTasks.find(t=>t.id===id);return finish(t,input);});}
  function bookingGuard(id,input,patientId) {run();const t=P.state.crmTasks.find(t=>t.id===id);validate(t,input,true);if(t.patientId!==patientId)throw Error('Lịch phải thuộc đúng bệnh nhân của task CSKH.');}
  function booked(id,input,a) {return finish(P.state.crmTasks.find(t=>t.id===id),input,a);}
  function expected(patientId,input) {window.PemaStaff?.assert('crm');return O.transact(()=>{D.seed();const p=P.patient(patientId);if(!/^\d{4}-\d{2}-\d{2}$/.test(input.date)||!Number.isFinite(Date.parse(input.date))||new Date(input.date).toISOString().slice(0,10)!==input.date||!input.reason.trim()||!sources[input.source]||input.source==='appointment')throw Error('Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.');Object.assign(p.crm,{recommendationAt:input.date,expectedVisitReason:input.reason.trim(),expectedVisitSource:input.source});P.addEvent(p,'plan','Ngày dự kiến tái khám',input.date+' · '+input.reason,p.doctor,D.DAY);run();});}
  function clinical(patientId,input) {window.PemaStaff?.assert('clinical');if(window.PemaStaff&&!PemaStaff.owns(P.patient(patientId)))throw Error('Hồ sơ không thuộc bác sĩ phụ trách.');return O.transact(()=>{const p=P.patient(patientId);if(!input.diagnosis.trim()||!input.history.trim())throw Error('Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận.');p.clinical={history:input.history.trim(),diagnosis:input.diagnosis.trim(),reviewedBy:p.doctor,at:D.DAY};P.addEvent(p,'consult','Bác sĩ ghi nhận khám và chẩn đoán',p.clinical.diagnosis,p.doctor,D.DAY);});}
  function reception(id,status) {return O.transact(()=>{const a=O.seed().appointments.find(a=>a.id===id);if(!a||a.date!==D.DAY||!O.active(a))throw Error('Lịch không thể chuyển trạng thái.');const allowed={booked:['arrived','missed'],confirmed:['arrived','missed'],arrived:['in_progress'],in_progress:['completed']};if(!allowed[a.status]?.includes(status))throw Error('Trạng thái không hợp lệ.');a.status=status;const p=P.patient(a.patient);p.status={arrived:'Đang chờ',in_progress:'Đang điều trị',completed:'Hoàn tất',missed:'Vắng hẹn'}[status];if(status==='arrived'&&p.crm.reactivationPending){p.crm.reactivatedAt=stamp();p.crm.reactivationPending=false;}O.sync(p.id);P.addEvent(p,'reception','Tiếp đón: '+p.status,a.date+' '+a.time,'Lễ tân',D.DAY);run();});}
  function metrics() {
    const q=queue(),a=P.state.crmActivities,ps=P.state.patients.map(profile), attempted=a.filter(x=>x.channel!=='Ghi chú nội bộ'),contacted=attempted.filter(x=>!['unanswered','invalid'].includes(x.outcome));
    return {pending:q.length,patients:new Set(q.map(t=>t.patientId)).size,completed:P.state.crmTasks.filter(t=>t.status==='resolved').length,overdueTasks:q.filter(t=>t.dueAt.slice(0,10)<D.DAY).length,overduePatients:ps.filter(p=>p.overdueDays>0).length,atRisk:ps.filter(p=>p.riskLevel==='high').length,abandoned:new Set(q.filter(t=>t.type==='abandoned').map(t=>t.patientId)).size,booked:a.filter(x=>x.relatedAppointmentId).length,reactivated:ps.filter(p=>p.reactivatedAt).length,contactRate:attempted.length?Math.round(contacted.length/attempted.length*100):0,attempted:attempted.length,contacted:contacted.length,stages:Object.fromEntries(Object.keys(stageLabels).map(k=>[k,ps.filter(x=>x.lifecycleStage===k).length]))};
  }
  function timeline(p) {
    const rows=p.events.map(x=>({...x,at:x.date,source:'Hồ sơ'}));
    for(const a of O.seed().appointments.filter(x=>x.patient===p.id))rows.push({id:'TL-'+a.id,at:a.date+'T'+a.time,title:'Lịch hẹn · '+({booked:'Đặt hẹn',confirmed:'Đã xác nhận',arrived:'Đã đến',in_progress:'Đang khám',completed:'Hoàn tất',cancelled:'Đã hủy',missed:'Vắng hẹn'}[a.status]||a.status),detail:a.note||'',by:a.createdBy||'Lễ tân',source:a.id});
    for(const a of P.state.crmActivities.filter(x=>x.patientId===p.id))rows.push({id:a.id,at:a.occurredAt,title:a.channel+' · '+outcomes[a.outcome],detail:a.note+(a.nextActionAt?' · Bước tiếp '+a.nextActionAt:'')+(a.relatedAppointmentId?' · Lịch '+a.relatedAppointmentId:''),by:a.actor,source:a.taskId});
    for(const a of O.seed().payments.filter(x=>x.patient===p.id))rows.push({id:a.id,at:a.at,title:'Thu tiền · '+P.money(a.amount),detail:a.invoice+' · '+a.method,by:'Thu ngân',source:a.id});
    return rows.sort((a,b)=>b.at.localeCompare(a.at));
  }
  window.PemaCRM={ensure,run,profile,queue,metrics,resolve,expected,clinical,reception,bookingGuard,booked,refresh,open,outcomes,sources,stageLabels,timeline,DAY:D.DAY};
})();
