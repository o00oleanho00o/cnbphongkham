/* Synthetic operations. Kept in the same transaction as Patient 360. */
(() => {
 const P=window.Pema, DAY='2026-09-20';
 const minutes=t=>/^([01]\d|2[0-3]):[0-5]\d$/.test(t||'')?Number(t.slice(0,2))*60+Number(t.slice(3)):NaN;
 const time=n=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;
 const dateOK=d=>/^\d{4}-\d{2}-\d{2}$/.test(d||'')&&Number.isFinite(Date.parse(d))&&new Date(d).toISOString().slice(0,10)===d;
 const active=a=>!['cancelled','missed'].includes(a.status);
 function seed(){
  if(P.state.operations)return P.state.operations;
  const doctors=['BS. Tâm','BS. Mai','BS. An','BS. Lan'].map((name,i)=>({id:'D'+i,name,start:'08:00',end:'18:00',breakStart:'12:00',breakEnd:'13:00'}));
  const rooms=['Khám da liễu','Tư vấn chuyên sâu','Laser & thủ thuật','Chăm sóc da'].map((name,i)=>({id:'R'+i,name,active:true}));
  const services=[{id:'S0',name:'Tái khám & đánh giá',duration:30,buffer:0,price:300000},{id:'S1',name:'Tư vấn da liễu',duration:45,buffer:15,price:500000},{id:'S2',name:'Laser theo chỉ định',duration:45,buffer:15,price:2500000},{id:'S3',name:'Chăm sóc theo chỉ định',duration:45,buffer:15,price:1200000}].map((s,i)=>({...s,active:true,rooms:i<2?['R0','R1']:['R'+i]}));
  const appointments=[];
  for(let day=0;day<7;day++)for(let i=0;i<(day===0?36:8);i++){
   const n=i%4,h=8+Math.floor(i/4)+(Math.floor(i/4)>=4?1:0),p=P.state.patients[(i+day*5)%P.state.patients.length],s=services[n];
   appointments.push({id:`A${day}-${i}`,patient:p.id,doctor:doctors[n].id,room:rooms[n].id,service:s.id,date:`2026-09-${20+day}`,time:time(h*60),duration:s.duration,buffer:s.buffer,price:s.price,status:'booked',note:'Lịch giả lập để thử điều phối'});
  }
  for(let i=0;i<12;i++){const p=P.state.patients[i],s=services[i%4];p.invoices.push({id:'HD-DEMO-'+String(i+1).padStart(3,'0'),date:DAY,label:s.name,amount:s.price,received:i%3===0?Math.floor(s.price/2):0,paid:false});}
  const o=P.state.operations={version:1,doctors,rooms,services,appointments,waitlist:P.state.patients.slice(0,6).map((p,i)=>({id:'W'+i,patient:p.id,service:'S'+i%4,note:i%2?'Ưu tiên buổi chiều':'Có thể đến trong ngày',status:'waiting'})),payments:[],blocks:[{id:'B1',room:'R2',doctor:'',date:'2026-09-21',start:'14:00',end:'15:00',reason:'Bảo trì thiết bị laser'}]};
  // Initial day remains the existing demo day; align reception with the resource schedule.
  for(const a of appointments.filter(a=>a.date===DAY)){const p=P.patient(a.patient);p.time=a.time;p.doctor=doctors.find(d=>d.id===a.doctor).name;}
  P.save();return o;
 }
 function sync(patient){const p=P.patient(patient),next=seed().appointments.filter(a=>a.patient===patient&&active(a)&&a.date>=DAY).sort((a,b)=>(a.date+a.time).localeCompare(b.date+b.time))[0];p.next=next?.date||null;p.time=next?.time||'';if(next)p.doctor=seed().doctors.find(d=>d.id===next.doctor).name;}
 function transact(fn){P.reload();seed();const snapshot=JSON.stringify(P.state);try{const result=fn();if(!P.save())throw Error('Không lưu được. Hãy thử lại; thay đổi chưa được ghi nhận.');return result;}catch(e){const state=P.state;Object.keys(state).forEach(k=>delete state[k]);Object.assign(state,JSON.parse(snapshot));throw e;}}
 function validate(a){const o=seed(),s=o.services.find(s=>s.id===a.service),d=o.doctors.find(d=>d.id===a.doctor),r=o.rooms.find(r=>r.id===a.room),start=minutes(a.time),end=start+a.duration,occupied=end+a.buffer;
  if(!P.state.patients.some(p=>p.id===a.patient)||!s||!d||!r)throw Error('Hãy chọn bệnh nhân, dịch vụ, bác sĩ và phòng.');
  if(!s.rooms.includes(a.room))throw Error('Phòng không phù hợp với dịch vụ đã chọn.');
  if(!s.active||!r.active)throw Error('Dịch vụ hoặc phòng đang tạm ngưng.');
  if(!dateOK(a.date)||a.date<DAY||!Number.isFinite(start)||!Number.isFinite(a.duration)||a.duration<15||a.duration>180||!Number.isFinite(a.buffer)||a.buffer<0||a.buffer>60)throw Error('Ngày, giờ hoặc thời lượng không hợp lệ.');
  if(start<minutes(d.start)||occupied>minutes(d.end)||(start<minutes(d.breakEnd)&&occupied>minutes(d.breakStart)))throw Error('Ngoài ca bác sĩ hoặc trùng giờ nghỉ 12:00–13:00.');
  for(const b of o.blocks.filter(b=>b.date===a.date&&(b.room===a.room||b.doctor===a.doctor)))if(start<minutes(b.end)&&occupied>minutes(b.start))throw Error('Trùng thời gian khóa: '+b.reason);
  for(const b of o.appointments.filter(b=>b.id!==a.id&&b.date===a.date&&active(b))){const bs=minutes(b.time),be=bs+b.duration,bo=be+b.buffer;
   if(start<be&&end>bs&&(b.doctor===a.doctor||b.patient===a.patient))throw Error('Trùng '+(b.patient===a.patient?'bệnh nhân':'bác sĩ')+' với lịch '+b.time+' của '+P.patient(b.patient).name+'.');
   if(b.room===a.room&&start<bo&&occupied>bs)throw Error('Phòng đang bận hoặc đang chuẩn bị sau lịch '+b.time+'.');
  }
  return true;
 }
 function saveAppointment(input){return transact(()=>{const o=seed(),old=o.appointments.find(a=>a.id===input.id);if(old&&!active(old))throw Error('Lịch đã hủy/vắng hẹn; hãy tạo lịch mới.');const s=o.services.find(s=>s.id===input.service);const a={...input,id:old?.id||'A-'+crypto.randomUUID(),duration:old&&old.service===input.service?old.duration:s?.duration,buffer:old&&old.service===input.service?old.buffer:s?.buffer,price:old&&old.service===input.service?old.price:s?.price,status:old?.status||'booked'};validate(a);const previousPatient=old?.patient;if(old)Object.assign(old,a);else o.appointments.push(a);if(input.waitlist){const w=o.waitlist.find(w=>w.id===input.waitlist);if(w)w.status='scheduled';}sync(a.patient);if(previousPatient&&previousPatient!==a.patient)sync(previousPatient);P.addEvent(P.patient(a.patient),'appointment',old?'Đã dời lịch hẹn':'Đã đặt lịch hẹn',`${a.date} · ${a.time} · ${s.name}`,'Lễ tân',a.date);P.log(old?'Dời lịch':'Đặt lịch',a.patient);return a;});}
 function setStatus(id,status){return transact(()=>{const a=seed().appointments.find(a=>a.id===id);if(!a||!active(a)||!['confirmed','arrived'].includes(status))throw Error('Không thể chuyển trạng thái lịch này.');a.status=status;const p=P.patient(a.patient);if(status==='arrived'&&a.date===DAY)p.status='Đang chờ';P.addEvent(p,'reception',status==='arrived'?'Đã check-in lịch hẹn':'Đã xác nhận lịch hẹn',a.date+' · '+a.time,'Lễ tân',a.date);P.log('Cập nhật trạng thái lịch',a.patient);});}
 function cancel(id,reason){return transact(()=>{const a=seed().appointments.find(a=>a.id===id);if(!a||!active(a)||!reason?.trim())throw Error('Cần lý do hủy cho lịch đang hoạt động.');a.status='cancelled';a.cancelReason=reason.trim();sync(a.patient);P.addEvent(P.patient(a.patient),'appointment','Đã hủy lịch hẹn',`${a.date} ${a.time} · ${reason}`,'Lễ tân',a.date);P.log('Hủy lịch',a.patient);});}
 function pay(patient,invoice,amount,method){return transact(()=>{const inv=P.patient(patient).invoices.find(i=>i.id===invoice);if(!inv)throw Error('Không tìm thấy hóa đơn.');const paid=inv.paid?inv.amount:(inv.received||0),due=inv.amount-paid;if(!Number.isSafeInteger(amount)||amount<=0||amount>due)throw Error('Số tiền phải lớn hơn 0 và không vượt số còn lại.');if(!['Tiền mặt','Chuyển khoản'].includes(method))throw Error('Phương thức không hợp lệ.');inv.received=paid+amount;inv.paid=inv.received===inv.amount;seed().payments.unshift({id:'PT-'+crypto.randomUUID(),patient,invoice,amount,method,at:new Date().toISOString()});P.log('Thu tiền demo',patient);});}
 function products(){const c=window.PemaProducts;return c&&Array.isArray(c.records)?c.records.map((r,i)=>({...r,id:r.id||'PRD-'+String(i+1).padStart(3,'0'),price:Number(r.price)||0})):[];}
 function updateService(id,input){return transact(()=>{const s=seed().services.find(s=>s.id===id);if(!s||!input.name.trim()||!Number.isInteger(input.duration)||input.duration<15||input.duration>180||!Number.isInteger(input.buffer)||input.buffer<0||input.buffer>60||!Number.isSafeInteger(input.price)||input.price<0)throw Error('Kiểm tra tên, thời lượng 15–180 phút, đệm 0–60 phút và giá không âm.');Object.assign(s,input);P.log('Sửa dịch vụ',id);});}
 function block(input){return transact(()=>{const o=seed();if(!dateOK(input.date)||!o.rooms.some(r=>r.id===input.room)||!input.reason.trim()||!(minutes(input.start)>=480&&minutes(input.end)<=1080&&minutes(input.start)<minutes(input.end)))throw Error('Khoảng khóa phải hợp lệ trong 08:00–18:00 và có lý do.');if(o.appointments.some(a=>active(a)&&a.date===input.date&&a.room===input.room&&minutes(a.time)<minutes(input.end)&&minutes(a.time)+a.duration+a.buffer>minutes(input.start)))throw Error('Có lịch hẹn trong khoảng này. Hãy dời lịch trước khi khóa phòng.');o.blocks.push({...input,id:'B-'+crypto.randomUUID()});P.log('Khóa phòng',input.room);});}
 window.PemaOps={seed,setStatus,minutes,time,active,validate,saveAppointment,cancel,pay,products,updateService,block,transact,sync};seed();
})();
