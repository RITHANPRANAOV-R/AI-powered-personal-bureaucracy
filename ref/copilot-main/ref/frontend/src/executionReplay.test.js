import test from 'node:test';
import assert from 'node:assert/strict';
async function fixture(){
 const api=await import(`./documentApi.js?replay=${Math.random()}`), original=globalThis.fetch;
 const context={session_id:'server',review_context:{id:'context'},facts:{}}; const calls=[];
 let behavior=async()=>{throw new Error('timeout');};
 globalThis.fetch=async(url,options={})=>{
  if(url.endsWith('/submit-step')){calls.push(options.body);return behavior();}
  const body=url.endsWith('/confirm')?{confirmed_context:context,review_capability:'synthetic'}:url.endsWith('/launch-uidai')?{current_stage:'stage_3_address',execution_state_version:0}:{confirmed_context:context};
  return {ok:true,json:async()=>body};
 };
 await api.confirmAadhaarDocument({}, {}, 'client'); await api.launchUidaiBrowser(context);
 return {api,calls,set(value){behavior=value;},restore(){globalThis.fetch=original;}};
}
test('timeout retry and input edits reuse immutable envelope; status cannot authorize retry',async()=>{
 const f=await fixture();try{
 await assert.rejects(f.api.submitBrowserStep('client',true,'',{pincode:'641025'}),/timeout/);
 await f.api.getBrowserSessionStatus('client');
 await assert.rejects(f.api.submitBrowserStep('client',true,'',{pincode:'560001'}),/timeout/);
 assert.equal(f.calls[0],f.calls[1]);assert.equal(JSON.parse(f.calls[1]).user_inputs.pincode,'641025');
 }finally{f.restore();}
});
test('uncertainty blocks dispatch; reload cannot reconstruct attempt',async()=>{
 const f=await fixture();try{
 f.set(async()=>({ok:true,json:async()=>({execution_uncertain:true,execution_result:{status:'UNKNOWN'}})}));
 await f.api.submitBrowserStep('client');await assert.rejects(f.api.submitBrowserStep('client'),/uncertain/);assert.equal(f.calls.length,1);
 const reloaded=await import(`./documentApi.js?reload=${Math.random()}`);await assert.rejects(reloaded.submitBrowserStep('client'),/Confirm a new/);
 }finally{f.restore();}
});
test('proven non-dispatch allows explicit fresh attempt at authoritative version',async()=>{
 const f=await fixture();try{
 f.set(async()=>({ok:true,json:async()=>({retry_permitted:true,execution_result:{status:'UNKNOWN'},current_stage:'stage_3_address',execution_state_version:1})}));
 await f.api.submitBrowserStep('client',false);await f.api.submitBrowserStep('client',true);
 assert.notEqual(JSON.parse(f.calls[0]).request_id,JSON.parse(f.calls[1]).request_id);assert.equal(JSON.parse(f.calls[1]).expected_state_version,1);
 }finally{f.restore();}
});


test('authoritative authentication failure cannot silently recreate or retry an execution attempt', async () => {
 const f=await fixture();try{
 f.set(async()=>({ok:false,status:403,json:async()=>({detail:{code:'REVIEW_CAPABILITY_AUTH_FAILED',message:'Expired'}})}));
 await assert.rejects(f.api.submitBrowserStep('client'),error=>error.code==='REVIEW_CAPABILITY_AUTH_FAILED');
 await assert.rejects(f.api.submitBrowserStep('client'),/Confirm a new/);
 await assert.rejects(f.api.submitBrowserStep('server'),/Confirm a new/);
 assert.equal(f.calls.length,1);
 assert.equal(JSON.parse(f.calls[0]).expected_state_version,0);
 }finally{f.restore();}
});
