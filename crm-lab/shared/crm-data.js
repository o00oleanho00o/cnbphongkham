/* CRM01 fixture/migration. Existing clinical records are never reseeded on upgrade. */
(() => {
  const P = window.Pema;
  const DAY = '2026-09-20';
  const addDays = (day, n) => new Date(Date.parse(day.slice(0, 10) + 'T12:00:00Z') + n * 86400000).toISOString().slice(0, 10);
  const days = (from, to = DAY) => Math.floor((Date.parse(to.slice(0, 10) + 'T12:00:00Z') - Date.parse(from.slice(0, 10) + 'T12:00:00Z')) / 86400000);
  const rules = [
    ['d1','Sau thủ thuật D+1','session_completed',1,'Hỏi tình trạng sau thủ thuật','high'],
    ['d3','D+3 cần ảnh','session_completed',3,'Mời gửi cập nhật/ảnh có đồng ý qua Patient Mobile','high'],
    ['d7','D+7 bác sĩ review','session_completed',7,'Chuyển bác sĩ xem ảnh và phản hồi','high'],
    ['due','Đến hạn tái khám','expected_visit',0,'Xác nhận kế hoạch tái khám','normal'],
    ['overdue','Quá hạn tái khám','expected_visit',1,'Hỏi trở ngại và hỗ trợ đặt lại lịch','high'],
    ['no_show','Vắng/hủy chưa đặt lại','appointment_missed',1,'Liên hệ hỗ trợ chọn lịch mới','high'],
    ['abandoned','Nguy cơ bỏ liệu trình','remaining_sessions',45,'Trao đổi về các buổi còn lại','high'],
    ['dormant90','90 ngày chưa quay lại','last_visit',90,'Hỏi thăm nhu cầu chăm sóc','normal'],
    ['dormant180','180 ngày chưa quay lại','last_visit',180,'Chăm sóc lại khách cũ','high'],
    ['birthday','Sinh nhật trong tuần','birthday',7,'Chúc mừng sinh nhật, không gửi tự động','low']
  ].map(([id,name,trigger,delayDays,suggestedAction,priority]) => ({id,name,trigger,delayDays,suggestedAction,priority,active:true,actionType:'staff_task',conditions:{protocol:id.startsWith('d')&&['d1','d3','d7'].includes(id)?'laser-co2':null,marketing:['dormant90','dormant180','birthday'].includes(id)}}));
  const cases = [
    ['P025','01 · Sau Laser CO2 D+1',1],['P026','02 · D+3 gửi ảnh',3],
    ['P027','03 · Quá hạn 14 ngày',30],['P028','04 · Vắng hẹn 2 ngày',35],
    ['P029','05 · Còn 3/6 buổi, vắng 60 ngày',60],['P030','06 · Khách cũ 180 ngày',180],
    ['P031','07 · Gọi lại → đặt lịch',95],['P032','08 · Sinh nhật tuần này',7]
  ];
  function seed() {
    const s = P.state;
    if (s.crmVersion === 1 && s.patients.every(p => p.crm) && s.mobileCasesVersion===1) return false;
    s.crmTasks ||= []; s.crmActivities ||= []; s.crmAutomationRules ||= structuredClone(rules);
    s.crmSegments ||= ['new','returning','treating','dormant','reactivated'];
    s.crmSequence ||= 0;
    s.patients.forEach((p, i) => {
      p.crm ||= {source:['Giới thiệu','Zalo OA','Tại phòng khám'][i%3],owner:i%2?'CSKH Mai Anh':'CSKH Thu',firstContactAt:'2026-06-26',recommendationAt:p.next||null,expectedVisitReason:'Bác sĩ hẹn đánh giá',expectedVisitSource:'doctor_recommendation',marketingOptOut:false};
    });
    if (s.crmFixturePending) {
      for (const [id, label, age] of cases) {
        const p = P.patient(id), last = addDays(DAY, -age);
        p.crm.demoCase = label; p.lastVisit = last;
        p.sessions.forEach((x,i)=>{x.date=addDays(last,-14*(p.sessions.length-1-i));});
        p.events = p.events.filter(x=>!['session','photo','followup'].includes(x.kind));
        p.events.push({id:'CASE-'+id,kind:'session',date:last,title:'Buổi điều trị gần nhất',detail:label+' · dữ liệu tổng hợp',by:p.doctor});
        p.crm.recommendationAt = addDays(last,30);
        if (['P025','P026','P032'].includes(id)) {
          p.sessions.at(-1).protocolId='laser-co2'; p.sessions.at(-1).type='Laser CO2 theo chỉ định';
          p.procedure='Laser CO2 theo chỉ định';
        }
        if (id==='P027') p.crm.recommendationAt=addDays(DAY,-14);
        if (id==='P029') {p.total=6;p.completed=3;p.sessions=Array.from({length:3},(_,i)=>({id:'CRM-S29-'+i,date:addDays(last,-(2-i)*30),type:'Laser theo chỉ định',note:'Buổi tổng hợp',reviewed:true,aftercare:p.aftercare}));}
        if (id==='P032') p.crm.birthday='1996-09-23';
        // These cases genuinely have no future booking; preserve historical rows.
        if (['P027','P028','P029','P030','P031'].includes(id)) {
          for (const a of s.operations.appointments.filter(a=>a.patient===id)) {
            a.status='cancelled';a.cancelReason='Case CRM: chưa chọn được lịch quay lại';
            a.date=addDays(DAY,-2);a.cancelledAt=addDays(DAY,-2)+'T09:00:00+07:00';
          }
          p.next=null;p.time='';
        }
        if(id==='P028') {const a=s.operations.appointments.find(a=>a.patient===id);a.status='missed';}
      }
      delete s.crmFixturePending;
    }
    if(s.mobileCasesVersion!==1) {
      const names=['Nguyễn Ánh Dương','Trần Minh Châu','Lê Bảo Ngọc','Phạm Gia Linh','Vũ Thanh Mai','Đặng Hoàng Yến','Bùi Ngọc Hà','Ngô Hải Anh','Đỗ Thu Hương','Hồ Khánh Chi'];
      const ages=[1,3,7,30,44,35,60,95,185,10];
      rules.forEach((rule,i)=>{
        // Preserve any patient created by the user with this ID; allocate a free one.
        let n=37+i;while(s.patients.some(p=>p.id==='P'+String(n).padStart(3,'0')))n++;
        const id='P'+String(n).padStart(3,'0'),last=addDays(DAY,-ages[i]);
        const p={gender:'Nữ',concern:'Theo dõi da sau điều trị',plan:'Kế hoạch chăm sóc da cá nhân',procedure:i<3?'Laser CO2 theo chỉ định':'Chăm sóc theo chỉ định',consent:true,photoConsent:true,aftercare:'Tuân thủ hướng dẫn đã được bác sĩ trao đổi; liên hệ phòng khám khi cần hỗ trợ.'};
        Object.assign(p,{id,name:names[i],phone:'09•• ••• '+(237+i),age:25+i,doctor:i%2?'BS. Mai':'BS. Tâm',status:'Chưa có lịch hôm nay',lastVisit:last,next:null,time:'',completed:3,total:6,notes:'',alerts:[],events:[],invoices:[],meds:[],messages:[],servicePlans:[],prescriptions:[]});
        p.sessions=Array.from({length:3},(_,j)=>({id:'MOBILE-'+id+'-'+j,date:addDays(last,-(2-j)*14),type:p.procedure,reviewed:true,aftercare:p.aftercare,...(i<3&&j===2?{protocolId:'laser-co2'}:{})}));
        p.crm={source:'Tài khoản mẫu mobile',owner:i%2?'CSKH Mai Anh':'CSKH Thu',firstContactAt:addDays(last,-30),recommendationAt:i===3?DAY:i===4?addDays(DAY,-14):addDays(last,30),expectedVisitReason:'Bác sĩ hẹn đánh giá',expectedVisitSource:'doctor_recommendation',marketingOptOut:false,demoCase:rule.name,demoGroup:rule.id,...(i===9?{birthday:'1996-09-23'}:{})};
        p.events=[{id:'MOBILE-E-'+id,kind:'session',date:last,title:'Buổi điều trị gần nhất',detail:'Hồ sơ tổng hợp để kiểm thử chăm sóc.',by:p.doctor}];
        p.messages=[{from:'clinic',text:'Chào bạn, đội ngũ Pema sẵn sàng hỗ trợ hành trình chăm sóc của bạn.',date:'20/09 · 09:00'}];
        s.patients.push(p);
        if(rule.id==='no_show')s.operations.appointments.push({id:'MOBILE-A-'+id,patient:id,doctor:i%2?'D1':'D0',room:'R1',service:s.operations.services[0].id,date:addDays(DAY,-2),time:'10:00',duration:30,buffer:10,status:'missed',missedAt:addDays(DAY,-2)+'T10:00:00+07:00'});
      });
      s.mobileCasesVersion=1;
    }
    s.crmVersion=1;
    return true;
  }
  window.PemaCRMData={DAY,addDays,days,seed,rules};
})();
