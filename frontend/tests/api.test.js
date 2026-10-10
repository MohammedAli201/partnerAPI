import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createLatestRequester, validateDraft, previewDraft } from '../src/api.js';
const copy = { required: 'required', validation_error: 'invalid', invalid_email: 'email', invalid_website: 'website', select_method: 'methods' };
const draft = { company: 'Example Company', name: 'Example Contact', email: 'contact@example.test', website: 'https://example.test', countries: 'Somalia', volume: '1000_10000', methods: ['mobile_wallet'], message: 'A synthetic preview request.' };

test('partner draft rejects credentials in URLs, missing details and unexpected methods', () => {
  assert.deepEqual(validateDraft('partner', draft, copy), {});
  for (const website of ['javascript:alert(1)','https://user:secret@example.test']) assert.ok(validateDraft('partner', {...draft,website},copy).website);
  for (const methods of [[], 'mobile_wallet', ['cash']]) assert.ok(validateDraft('partner',{...draft,methods},copy).methods);
  assert.ok(validateDraft('partner',{...draft,email:'bad',company:''},copy).email);
});
test('support draft bounds free text and validates topics', () => {
  const support = { name:'Example Contact',email:'help@example.test',topic:'delivery',message:'A synthetic support note.' };
  assert.deepEqual(validateDraft('support',support,copy),{});
  assert.ok(validateDraft('support',{...support,message:'x'.repeat(2001),topic:'private'},copy).message);
  assert.ok(validateDraft('support',{...support,topic:'private'},copy).topic);
});
test('late delivered result cannot overwrite the current UNKNOWN selection', async () => {
  const pending=[];
  const request=createLatestRequester(()=>new Promise(resolve=>pending.push(resolve)));
  const previous=request('/delivered'),current=request('/action');
  pending[1]({ok:true,json:async()=>({status:'UNKNOWN'})});
  assert.deepEqual(await current,{status:'UNKNOWN'});
  pending[0]({ok:true,json:async()=>({status:'SENT'})});
  assert.equal(await previous,null);
});
test('superseded error is ignored and the current failure is surfaced',async()=>{
  const pending=[];const request=createLatestRequester(()=>new Promise((resolve,reject)=>pending.push({resolve,reject})));
  const old=request('/old'),current=request('/current');
  pending[0].reject(Error('old'));assert.equal(await old,null);
  pending[1].resolve({ok:false,json:async()=>({detail:'unavailable'})});await assert.rejects(current);
});
test('preview adapter requires honest unsent and unstored confirmation',async()=>{
  const originalFetch=globalThis.fetch,originalDocument=globalThis.document;
  globalThis.document={cookie:''};
  try{
    globalThis.fetch=async()=>({ok:true,json:async()=>({mode:'preview',sent:false,stored:false,draft})});
    assert.equal((await previewDraft('partner',draft)).sent,false);
    globalThis.fetch=async()=>({ok:true,json:async()=>({mode:'preview',sent:true,stored:false})});
    await assert.rejects(previewDraft('partner',draft));
  }finally{globalThis.fetch=originalFetch;globalThis.document=originalDocument;}
});
