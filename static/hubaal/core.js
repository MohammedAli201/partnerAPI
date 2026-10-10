(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.HubaalCore=api})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function validateDraft(kind,data,copy){
    const errors={},ranges=kind==='partner'?{company:[2,160],name:[2,100],email:[5,254],website:[8,500],countries:[2,200],message:[10,2000]}:{name:[2,100],email:[5,254],message:[10,2000]};
    for(const [key,[min,max]] of Object.entries(ranges)){const value=String(data[key]||'').trim();if(!value)errors[key]=copy.required;else if(value.length<min||value.length>max)errors[key]=copy.validation_error}
    if(data.email&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email.trim()))errors.email=copy.invalid_email;
    if(kind==='partner'){
      try{const u=new URL(data.website);if(!['https:','http:'].includes(u.protocol)||!u.hostname||u.username||u.password)throw Error()}catch{errors.website=copy.invalid_website}
      if(!['under_1000','1000_10000','10001_50000','over_50000'].includes(data.volume))errors.volume=copy.required;
      if(!Array.isArray(data.methods)||!data.methods.length||data.methods.some(x=>!['mobile_wallet','other'].includes(x)))errors.methods=copy.select_method;
    }else if(!['delivery','details','other'].includes(data.topic))errors.topic=copy.required;
    return errors;
  }
  function createLatestRequester(fetchImpl){let generation=0,controller=null;return async function(url,options={}){
    const current=++generation;if(controller)controller.abort();controller=new AbortController();
    try{const response=await fetchImpl(url,{...options,signal:controller.signal});const data=await response.json();if(current!==generation)return null;
      if(!response.ok){const error=Error('Request failed');error.status=response.status;error.details=data.detail;throw error}return data;
    }catch(error){if(current!==generation||error.name==='AbortError')return null;throw error}
  }}
  function languagePath(current,lang){if(!['en','so'].includes(lang))throw Error('Unsupported locale');const url=new URL(current);url.searchParams.set('lang',lang);return url.pathname+url.search+url.hash}
  return {validateDraft,createLatestRequester,languagePath};
});
