/* Browser DOM checks for owned offline snapshots. No desktop automation. */
(async()=>{
 const results=[];const assert=(value,name)=>{if(!value)throw Error(name);results.push(name)};
 const qs=s=>document.querySelector(s),tick=()=>new Promise(r=>setTimeout(r,20));
 const wait=async predicate=>{for(let n=0;n<50;n++){if(predicate())return;await tick()}throw Error('Timed out waiting for DOM state')};
 try{
  await document.fonts.ready;await tick();
  assert(document.documentElement.scrollWidth<=innerWidth+1,'no horizontal overflow');
  assert(qs('main h1')&&document.querySelectorAll('main h1').length===1,'one page heading');
  assert(qs('main')&&qs('header')&&qs('footer'),'semantic landmarks');
  assert(qs('.skip-link').getAttribute('href')==='#main','skip link target');
  const controls=[...document.querySelectorAll('input:not([type=checkbox]),select,textarea')];
  assert(controls.every(x=>x.labels?.length||x.getAttribute('aria-label')),'labelled form controls');
  assert([...document.querySelectorAll('img')].every(x=>x.hasAttribute('alt')&&x.width>0),'image alternatives and dimensions');
  const toggle=qs('#menu-toggle'),menu=qs('#mobile-menu');
  if(getComputedStyle(toggle).display!=='none'){
   toggle.click();assert(menu.open,'mobile drawer opens');assert(qs('#menu-close')===document.activeElement,'drawer focuses close control');
   assert(getComputedStyle(document.body).overflow==='hidden','body scroll locked');
   const all=[...menu.querySelectorAll('a[href],button')],first=all[0],last=all.at(-1);
   last.focus();last.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));assert(document.activeElement===first,'drawer forward focus wraps');
   first.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}));assert(document.activeElement===last,'drawer reverse focus wraps');
   menu.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await tick();assert(!menu.open&&document.activeElement===toggle,'Escape closes and restores focus');
   assert(!document.body.classList.contains('dialog-open'),'body scroll unlocked');
  }
  if(qs('#help-search')){
   const s=qs('#help-search');s.value='no-matching-question-xyz';s.dispatchEvent(new Event('input'));
   assert(!qs('#no-results').hidden,'search empty state');assert(qs('#search-status').textContent.includes('0'),'search result announcement');
   s.value=document.documentElement.lang==='so'?'khidmad':'fee';s.dispatchEvent(new Event('input'));
   assert([...document.querySelectorAll('.faq-item')].some(x=>!x.hidden),'help filters matching answers');
   const item=[...document.querySelectorAll('.faq-item')].find(x=>!x.hidden);item.querySelector('summary').click();assert(item.open,'FAQ opens with native control');
  }
  if(qs('#scenario')){
   await wait(()=>qs('#tracking-status .tracking-title'));
   qs('#scenario').value='action';qs('#scenario').dispatchEvent(new Event('change'));
   await wait(()=>qs('#tracking-status .action'));
   const copy=JSON.parse(qs('#public-copy').textContent);
   assert(qs('#tracking-status .tracking-title').textContent===copy.status_unknown,'UNKNOWN is action required');
   assert(!qs('#tracking-status .status-timeline').textContent.includes(copy.status_sent),'UNKNOWN timeline has no delivered outcome');
  }
  const form=qs('form[data-draft]');if(form){
   form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
   assert(form.querySelector('[aria-invalid=true]')===document.activeElement,'invalid draft focuses its first field');
   const kind=form.dataset.draft,fields=kind==='partner'?{company:'Example Company',name:'Example Contact',email:'contact@example.test',website:'https://example.test',countries:'Somalia',volume:'1000_10000',message:'Synthetic enquiry used only for a local preview.'}:{name:'Example Contact',email:'help@example.test',topic:'delivery',message:'Synthetic note used only for a local preview.'};
   for(const [key,value]of Object.entries(fields))form.querySelector(`[name="${key}"]`).value=value;
   if(kind==='partner')form.querySelector('[name=methods]').checked=true;
   form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
   assert(form.querySelector('[type=submit]').disabled,'draft loading state');await wait(()=>qs('#draft-dialog').open);
   assert(qs('.form-status').textContent.includes(JSON.parse(qs('#public-copy').textContent).preview_ready),'preview says enquiry not sent');
   assert(document.activeElement===qs('#edit-draft'),'review dialog focus');
   qs('#draft-dialog').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));await tick();
   assert(document.activeElement===form.querySelector('[type=submit]'),'review dialog restores focus');
   window.__forceDraftFailure=true;form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
   await wait(()=>!form.querySelector('[type=submit]').disabled);
   assert(!qs('#draft-dialog').open&&qs('.form-status').textContent===JSON.parse(qs('#public-copy').textContent).request_error,'failure is honest and retains form');
   assert(form.querySelector('[name=name]').value==='Example Contact','failure retains editable contents');
  }
  document.body.dataset.checks='passed';
 }catch(error){document.body.dataset.checks='failed';results.push('FAIL: '+error.message)}
 const output=document.createElement('script');output.type='application/json';output.id='browser-check-results';output.textContent=JSON.stringify(results);document.body.appendChild(output);
})();
