/* Demo identity/navigation boundary, NOT authentication or production RBAC. */
(() => {
 const accounts=[
  {id:'owner-tam',name:'BS. Tâm',role:'owner',label:'Chủ phòng khám',doctor:'D0'},
  {id:'doctor-tam',name:'BS. Tâm',role:'doctor',label:'Bác sĩ điều trị',doctor:'D0'},
  {id:'doctor-mai',name:'BS. Mai',role:'doctor',label:'Bác sĩ điều trị',doctor:'D1'},
  {id:'doctor-an',name:'BS. An',role:'doctor',label:'Bác sĩ điều trị',doctor:'D2'},
  {id:'doctor-lan',name:'BS. Lan',role:'doctor',label:'Bác sĩ điều trị',doctor:'D3'},
  {id:'care-maianh',name:'Mai Anh',role:'care',label:'CSKH',owner:'CSKH Mai Anh'},
  {id:'care-thu',name:'Thu',role:'care',label:'CSKH',owner:'CSKH Thu'},
  {id:'accountant',name:'Kế toán',role:'accountant',label:'Đối soát & thu ngân'}
 ];
 let account=accounts[0];try{account=accounts.find(x=>x.id===sessionStorage.getItem('pema-staff'))||account;}catch(_){}
 const pages={owner:['dashboard','today','schedule','patients','patient','crm','followups','studio','resources','services','cashier','ask','guide'],doctor:['dashboard','today','schedule','patients','patient','followups','studio','guide'],care:['crm','schedule','patients','patient','guide'],accountant:['cashier','patients','patient','guide']};
 const capabilities={clinical:['owner','doctor'],crm:['owner','care','doctor'],booking:['owner','care','doctor'],billing:['owner','accountant'],config:['owner'],readFinance:['owner','accountant','doctor']};
 function current(){return account;}
 function can(action){return capabilities[action]?.includes(account.role)||false;}
 function assert(action){if(!can(action))throw Error('Tài khoản '+account.name+' không có tác vụ này. Chuyển đúng không gian làm việc.');}
 function owns(p){return account.role!=='doctor'||p.doctor===account.name||window.Pema?.state.operations?.appointments.some(a=>a.patient===p.id&&a.doctor===account.doctor&&!['cancelled','missed'].includes(a.status));}
 function allowed(page){return pages[account.role].includes(page);}
 function home(){return account.role==='care'?'crm':account.role==='accountant'?'cashier':'dashboard';}
 function switchTo(id){const a=accounts.find(x=>x.id===id);if(!a)throw Error('Tài khoản demo không hợp lệ.');account=a;try{sessionStorage.setItem('pema-staff',id)}catch(_){}window.dispatchEvent(new Event('pema-staff-change'));}
 function picker(){return `<label class="staff-picker">Tài khoản demo<select id="staff-account" aria-label="Tài khoản nhân viên demo">${accounts.map(a=>`<option value="${a.id}" ${a.id===account.id?'selected':''}>${a.name} · ${a.label}</option>`).join('')}</select></label>`;}
 function financeUrl(){return '../finance/?staff='+account.id;}
 function apply(){
  if(account.role==='doctor'){const d=document.getElementById('ops-doctor');if(d){d.value=account.doctor;d.disabled=true;}}
  const picker=document.getElementById('staff-account');if(picker)picker.onchange=()=>switchTo(picker.value);
  document.querySelectorAll('[data-nav]').forEach(b=>{if(!allowed(b.dataset.nav))b.remove();});
  document.querySelectorAll('.sidebar .nav-section').forEach(section=>{let n=section.nextElementSibling,found=false;while(n&&!n.classList.contains('nav-section')&&!n.classList.contains('sidebar-bottom')){if(n.classList.contains('nav-item'))found=true;n=n.nextElementSibling;}if(!found)section.remove();});
  document.querySelectorAll('[data-tab]').forEach(b=>{if(account.role==='care'&&['consult','session','photos'].includes(b.dataset.tab)||account.role==='accountant'&&['consult','session','photos','crm'].includes(b.dataset.tab))b.remove();});
  if(!can('clinical'))document.querySelectorAll('[data-action="generate-note"],[data-action="approve-note"],[data-action="save-session"],[data-action="review-submit"],[data-care-action="approve-prescription"],[data-care-action="add-prescription"],[data-modal="note"],[data-modal="edit"],[data-modal="care"],[data-modal="plan-edit"],[data-tab="session"],#crm-clinical-form button').forEach(b=>b.remove());
  if(!can('billing'))document.querySelectorAll('[data-care-action="add-service"],[data-care-nav="cashier"],[data-ops="pay"],[data-ops="quick-order"],[data-quick-edit]').forEach(b=>b.remove());
  if(account.role==='care'||account.role==='accountant')document.querySelectorAll('[data-modal="message"]').forEach(b=>b.remove());
 }
 window.PemaStaff={accounts,current,can,assert,owns,allowed,home,switchTo,picker,financeUrl,apply};
})();
