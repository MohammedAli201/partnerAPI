const test=require('node:test');
const assert=require('node:assert/strict');
const {validateDraft,createLatestRequester,languagePath}=require('../static/hubaal/core.js');
const copy={required:'Required',validation_error:'Invalid',invalid_email:'Email invalid',invalid_website:'Website invalid',select_method:'Choose method'};
const valid={company:'Example Company',name:'Example Contact',email:'contact@example.test',website:'https://example.test',countries:'Somalia',volume:'1000_10000',methods:['mobile_wallet'],message:'A synthetic partnership enquiry.'};
test('language switching retains the route, existing query and destination anchor',()=>{
 assert.equal(languagePath('http://localhost:8000/partners?lang=en#enquiry','so'),'/partners?lang=so#enquiry');
 assert.equal(languagePath('http://localhost:8000/receive','so'),'/receive?lang=so');
 assert.throws(()=>languagePath('http://localhost:8000/','ar'));
});
test('partner draft validates required details and URL schemes',()=>{
 assert.deepEqual(validateDraft('partner',valid,copy),{});
 for(const [key,value] of Object.entries({email:'bad',website:'javascript:alert(1)',company:' ',methods:[],volume:'invalid',message:'short'})){
  assert.ok(validateDraft('partner',{...valid,[key]:value},copy)[key]);
 }
});
test('support validation rejects too-short and oversized contents',()=>{
 const data={name:'Example',email:'help@example.test',topic:'delivery',message:'A synthetic request for guidance.'};
 assert.deepEqual(validateDraft('support',data,copy),{});
 assert.ok(validateDraft('support',{...data,message:'x'.repeat(2001)},copy).message);
 assert.ok(validateDraft('support',{...data,topic:'other-private-field'},copy).topic);
});
test('old responses cannot overwrite a later selection even if abort is ignored',async()=>{
 const waiting=[];const request=createLatestRequester(()=>new Promise(resolve=>waiting.push(resolve)));
 const first=request('/processing'),second=request('/action');
 waiting[1]({ok:true,json:async()=>({status:'UNKNOWN'})});
 assert.deepEqual(await second,{status:'UNKNOWN'});
 waiting[0]({ok:true,json:async()=>({status:'SENT'})});
 assert.equal(await first,null);
});
test('current failures are reported; superseded failures are ignored',async()=>{
 const waiting=[];const request=createLatestRequester(()=>new Promise(resolve=>waiting.push(resolve)));
 const old=request('/old'),current=request('/current');
 waiting[0]({ok:false,status:503,json:async()=>({detail:'Unavailable'})});assert.equal(await old,null);
 waiting[1]({ok:false,status:503,json:async()=>({detail:'Unavailable'})});await assert.rejects(current,e=>e.status===503);
});
