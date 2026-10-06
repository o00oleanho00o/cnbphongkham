/* Completely synthetic clinic data. No real patient records or clinical claims. */
(function () {
  const KEY = 'pema-demo-v2';
  const names = ['Nguyễn Minh Linh','Trần Ngọc Anh','Lê Hoàng Nam','Phạm Thảo Vy','Vũ Quỳnh Trang','Đặng Gia Hân','Bùi Khánh An','Ngô Đức Minh','Đỗ Phương Nhi','Hồ Bảo Ngọc','Dương Tuấn Kiệt','Võ Thanh Trúc','Nguyễn Mai Chi','Trần Quốc Bảo','Lê Ngọc Diệp','Phạm Minh Khang','Vũ Hà My','Đặng Phương Linh','Bùi Anh Thư','Ngô Nhật Hạ','Đỗ Đức Huy','Hồ Mỹ Duyên','Dương Thanh Hà','Võ Tường Vy','Nguyễn Bảo Châu','Trần Minh Đức','Lê Hồng Nhung','Phạm Hải Yến','Vũ Gia Bảo','Đặng Ngọc Hân','Bùi Thùy Dương','Ngô Khánh Vy','Đỗ Thanh Tùng','Hồ Lan Anh','Dương Phúc An','Võ Minh Châu'];
  const groups = [
    ['Nám · tăng sắc tố','Liệu trình kiểm soát sắc tố','Chăm sóc & laser theo chỉ định',5,'SPF 50+ mỗi sáng; thoa lại theo hướng dẫn'],
    ['Mụn viêm','Theo dõi mụn & chăm sóc tại nhà','Tái khám và đánh giá đáp ứng',4,'Sữa rửa mặt dịu nhẹ; tránh tự nặn mụn'],
    ['Thâm sau viêm','Phục hồi sau mụn','Chăm sóc da & peel theo chỉ định',4,'Dưỡng ẩm dịu nhẹ; bảo vệ da khỏi nắng'],
    ['Đỏ da / nhạy cảm','Phục hồi hàng rào da','Đánh giá đỏ da định kỳ',3,'Tránh sản phẩm mới khi chưa hỏi bác sĩ'],
    ['Sẹo sau mụn','Theo dõi cải thiện sẹo','Laser phân đoạn theo chỉ định',5,'Tuân thủ hướng dẫn chăm sóc sau thủ thuật'],
    ['Trẻ hóa da','Kế hoạch thẩm mỹ cá nhân','Đánh giá trước thủ thuật',3,'Theo dõi vùng điều trị theo hướng dẫn']
  ];
  function initial() {
    return {
      version: 2, selected: 'P001', audit: [], crmFixturePending: true,
      patients: names.map((name,i)=>{
        const g=groups[i%groups.length], total=g[3], completed=i===0?2:1+(i%Math.max(1,total-1));
        const visitDate = i===0 ? '2026-09-06' : i%4===0 ? '2026-08-16' : '2026-09-06';
        const sessions = Array.from({length:completed},(_,j)=>({id:`s${i}-${j}`,date:new Date(new Date(visitDate+'T12:00:00Z').getTime()-(completed-1-j)*14*86400000).toISOString().slice(0,10),type:g[2],note:'Đã ghi nhận đáp ứng và gửi hướng dẫn chăm sóc.',reviewed:true,view:'Chính diện',region:'Mặt',image:'placeholder',aftercare:g[4]}));
        return {id:'P'+String(i+1).padStart(3,'0'),name,age:i===0?32:19+(i*7%43),gender:i%7===2?'Nam':'Nữ',phone:'09•• ••• '+String(100+i),concern:g[0],plan:g[1],procedure:g[2],total,completed,doctor:i%3===2?'BS. Mai':'BS. Tâm',lastVisit:visitDate,next:'2026-09-20',time:`${String(9+Math.floor(i/4)).padStart(2,'0')}:${String(i%4*15).padStart(2,'0')}`,status:i===0?'Đang chờ':i%5===1?'Đã đến':i%5===2?'Đặt hẹn':i%7===0?'Vắng hẹn':'Đang điều trị',alerts:i===0?['Da nhạy cảm','Theo dõi đỏ da sau điều trị']:i%7===0?['Cần cập nhật tiền sử dị ứng']:[],consent:i%9!==2,photoConsent:true,aftercare:g[4],meds:[{name:'Sữa rửa mặt dịu nhẹ',use:'Sáng & tối · theo hướng dẫn đã duyệt'},{name:'Dưỡng ẩm phục hồi',use:'Sau làm sạch · dùng lượng phù hợp'},{name:'Chống nắng SPF 50+',use:'Buổi sáng · thoa lại theo hướng dẫn'}],notes:'',events:[{id:'e'+i+'-1',kind:'followup',date:'2026-09-13',title:'Cập nhật tại nhà đã được xem',detail:i===0?'Đỏ nhẹ khoảng 2 ngày, hiện đã ổn. Không ghi nhận dấu hiệu cảnh báo trong báo cáo.':'Người bệnh báo đã làm theo hướng dẫn chăm sóc.',by:'Điều dưỡng Hương'},{id:'e'+i+'-2',kind:'session',date:visitDate,title:'Hoàn tất buổi '+completed+'/'+total,detail:g[2]+'. Đã gửi hướng dẫn chăm sóc sau buổi điều trị.',by:'BS. Tâm'},{id:'e'+i+'-3',kind:'photo',date:visitDate,title:'Bộ ảnh theo dõi · chính diện',detail:'Ảnh minh họa giả lập · đồng ý sử dụng trong chăm sóc.',by:'Điều dưỡng Hương'},{id:'e'+i+'-4',kind:'plan',date:'2026-06-26',title:'Bắt đầu '+g[1].toLowerCase(),detail:'Mục tiêu và lịch đánh giá đã được trao đổi với người bệnh.',by:'BS. Tâm'}],messages:[{from:'clinic',text:'Chào bạn, Pema đã lưu hướng dẫn chăm sóc của buổi điều trị gần nhất. Bạn có thể gửi cập nhật bất cứ lúc nào.',date:'13/09 · 09:15'}],sessions,invoices:[{id:'HD-'+String(i+1).padStart(4,'0'),date:visitDate,label:'Buổi chăm sóc / điều trị',amount:1200000+(i%4)*300000,paid:true}]};
      }),
      followups:[{id:'F001',patient:'P001',type:'Ảnh cần bác sĩ xem',priority:'review',symptom:'Đỏ nhẹ đã giảm, không đau. Em gửi ảnh trước buổi hẹn.',date:'2026-09-20T08:42:00',image:'placeholder',status:'open',owner:'BS. Tâm'},{id:'F002',patient:'P004',type:'Phản hồi triệu chứng',priority:'urgent',symptom:'Rát tăng lên sau chăm sóc, muốn được phòng khám gọi lại.',date:'2026-09-20T08:30:00',image:null,status:'open',owner:'BS. Tâm'},{id:'F003',patient:'P005',type:'Quá hạn phản hồi 3 ngày',priority:'overdue',symptom:'Chưa có phản hồi kiểm tra sau buổi điều trị.',date:'2026-09-17T09:00:00',image:null,status:'open',owner:'CSKH Thu'},{id:'F004',patient:'P010',type:'Thiếu ảnh mốc đánh giá',priority:'missing',symptom:'Chưa lưu bộ ảnh chính diện của buổi 2.',date:'2026-09-20T08:00:00',image:null,status:'open',owner:'Điều dưỡng Hương'},{id:'F005',patient:'P007',type:'Kiểm tra chăm sóc ngày 2',priority:'review',symptom:'Da ổn, hơi khô. Đã dùng dưỡng ẩm như hướng dẫn.',date:'2026-09-20T07:35:00',image:'placeholder',status:'open',owner:'CSKH Thu'}]
    };
  }
  const valid=s=>!!(s&&s.version===2&&Array.isArray(s.patients)&&s.patients.length>=30&&Array.isArray(s.followups)&&Array.isArray(s.audit)&&s.patients.every(p=>p&&['id','name','concern','plan','procedure','doctor','aftercare'].every(k=>typeof p[k]==='string')&&Number.isFinite(p.total)&&p.total>0&&Number.isFinite(p.completed)&&['events','alerts','meds','messages','sessions','invoices'].every(k=>Array.isArray(p[k]))&&p.events.every(x=>x&&typeof x.id==='string')&&p.sessions.every(x=>x&&typeof x.id==='string')&&p.meds.every(x=>x&&typeof x.name==='string')&&p.messages.every(x=>x&&typeof x.text==='string')&&p.invoices.every(x=>x&&Number.isFinite(x.amount)))&&s.followups.every(f=>f&&typeof f.id==='string'&&s.patients.some(p=>p.id===f.patient)));
  let state;
  try {state=JSON.parse(localStorage.getItem(KEY))} catch (_) {}
  if (!valid(state)) state=initial();
  const P = window.Pema = {
    get state(){return state},
    save(){try{localStorage.setItem(KEY,JSON.stringify(state));window.dispatchEvent(new Event('pema-change'));return true}catch(e){window.dispatchEvent(new CustomEvent('pema-save-error',{detail:'Không lưu được: bộ nhớ trình duyệt đã đầy. Hãy dùng ảnh nhỏ hơn hoặc đặt lại dữ liệu demo.'}));return false}},
    reload(){try {const s=JSON.parse(localStorage.getItem(KEY));if(valid(s)) state=s}catch(_){}},
    reset(){state=initial();this.save()},
    patient(id){return state.patients.find(p=>p.id===(id||state.selected))||state.patients[0]},
    select(id){state.selected=id;this.save()},
    log(action,patient){state.audit.unshift({action,patient,at:new Date().toISOString(),actor:'Tài khoản demo'})},
    esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))},
    date(s){return s&&!isNaN(new Date(s))?new Date(s).toLocaleDateString('vi-VN'):'Chưa ghi nhận'},
    money(n){return n.toLocaleString('vi-VN')+' ₫'},
    initials(p){return p.name.split(' ').slice(-2).map(n=>n[0]).join('')},
    async imageData(file){if(!file)return null;if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('Chỉ hỗ trợ PNG, JPEG hoặc WebP.');if(file.size>2500000)throw new Error('Ảnh demo tối đa 2,5 MB.');return await new Promise((resolve,reject)=>{const r=new FileReader();r.onerror=()=>reject(new Error('Không đọc được ảnh.'));r.onload=()=>{const img=new Image();img.onerror=()=>reject(new Error('Tệp không phải ảnh hợp lệ.'));img.onload=()=>{const c=document.createElement('canvas'),scale=Math.min(1,900/Math.max(img.width,img.height));c.width=Math.round(img.width*scale);c.height=Math.round(img.height*scale);c.getContext('2d').drawImage(img,0,0,c.width,c.height);resolve(c.toDataURL('image/jpeg',.72))};img.src=r.result};r.readAsDataURL(file)})},
    addEvent(p,kind,title,detail,by='BS. Tâm',date='2026-09-20'){p.events.unshift({id:'e'+Date.now()+'-'+Math.random().toString(36).slice(2,7),date,kind,title,detail,by})},
    brief(p){const open=state.followups.filter(f=>f.patient===p.id&&f.status==='open');return `${p.name}, ${p.age} tuổi, quay lại để đánh giá ${p.concern.toLowerCase()}. Đã hoàn tất ${p.completed}/${p.total} buổi của ${p.plan.toLowerCase()}. Lần gần nhất: ${this.date(p.lastVisit)}. ${p.events.find(e=>e.kind==='followup')?.detail||'Chưa có cập nhật sau điều trị.'} ${open.length?`Có ${open.length} mục theo dõi chưa xử lý; cần kiểm tra trước buổi tiếp theo.`:'Không có mục theo dõi đang mở.'} Bước tiếp theo: bác sĩ đánh giá đáp ứng, xác nhận dữ liệu và quyết định kế hoạch.`},
    face(stage='before',label='Ảnh minh họa',id='face'){
      const after=stage==='after';
      return `<div class="clinical-photo ${after?'after':''}"><svg viewBox="0 0 300 300" role="img" aria-label="${this.esc(label)} — minh họa tổng hợp, không phải ảnh bệnh nhân"><defs><linearGradient id="${id}" x2="0.2" y2="1"><stop stop-color="#e6c6af"/><stop offset="1" stop-color="#cda184"/></linearGradient></defs><rect width="300" height="300" fill="${after?'#dfdfd4':'#e5e3da'}"/><ellipse cx="150" cy="326" rx="114" ry="75" fill="#bba997"/><path d="M125 216h50l8 57-34 18-35-18z" fill="#c89b7e"/><ellipse cx="150" cy="135" rx="74" ry="104" fill="url(#${id})"/><path d="M76 128c-9-57 15-106 74-106 62 0 89 51 75 110l-15-61c-53 21-81-5-89-11l-29 76z" fill="#474139"/><path d="M100 126q18-11 34 0M167 126q18-11 33 0" fill="none" stroke="#6b5344" stroke-width="3"/><path d="M107 139q12 8 22 0M173 139q12 8 23 0" fill="none" stroke="#504438" stroke-width="2"/><path d="M151 142l-8 34q8 6 18 0" fill="none" stroke="#b17c61" stroke-width="2"/><path d="M126 197q24 12 48-1-23 4-48 1z" fill="#9f6e61"/><g fill="#aa7964" opacity="${after?'.15':'.44'}"><ellipse cx="104" cy="160" rx="17" ry="10"/><ellipse cx="194" cy="160" rx="17" ry="10"/><ellipse cx="112" cy="172" rx="11" ry="7"/><ellipse cx="182" cy="171" rx="11" ry="7"/></g><path d="M20 34v-14h14M266 20h14v14M20 266v14h14M266 280h14v-14" fill="none" stroke="white" opacity=".65"/></svg><span class="photo-disclaimer">MINH HỌA TỔNG HỢP</span></div>`
    }
  };
  window.addEventListener('storage',e=>{if(e.key===KEY){P.reload();window.dispatchEvent(new Event('pema-external'))}});
  P.save();
})();

