'use strict';
// Actual app exportData function with controlled platform APIs. NOT native device behavior.
const fs=require('fs'),vm=require('vm'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'pocket/web/app.js'),'utf8');
const fn=source.slice(source.indexOf('async function exportData('),source.indexOf('function textActions('));
let nativeApp=false,notices=[],downloads=[],shared=[],prompts=[];
global.notice=t=>notices.push(t);
global.el=()=>({click(){downloads.push({href:this.href,name:this.download})},remove(){}});
global.document={body:{append(){}}};
Object.defineProperty(global,'navigator',{value:{},configurable:true});global.window={prompt:(...x)=>{prompts.push(x);return 'opened'}};
const originalTimeout=global.setTimeout;
global.setTimeout=()=>0;
vm.runInThisContext(fn);
let checks=[];
function check(name,v){checks.push({name,status:v?'PASS':'FAIL'});if(!v)throw Error(name)}
async function main(){
 const text='SYNTHETIC_EXPORT_ONLY',encoded=Buffer.from(text).toString('base64');
 global.nativeApp=false;
 await exportData('save','synthetic.txt','text/plain',encoded,text);
 check('browser download created',downloads.length===1&&downloads[0].name==='synthetic.txt'&&downloads[0].href.startsWith('blob:'));
 check('browser notice is request, not delivery assertion',notices.includes('Browser download requested.'));
 navigator.share=async value=>shared.push(value);
 await exportData('share','synthetic.txt','text/plain',encoded,text);
 check('Web Share receives only synthetic text',shared.length===1&&shared[0].text===text);
 navigator.canShare=()=>true;
 await exportData('share','synthetic.txt','text/plain',encoded);
 check('file-share branch receives synthetic file',shared[1].files.length===1&&shared[1].files[0].name==='synthetic.txt');
 check('file-share content exact',await shared[1].files[0].text()===text);
 delete navigator.share;delete navigator.canShare;
 let unavailable=false;try{await exportData('share','synthetic.txt','text/plain',encoded)}catch(e){unavailable=e.message.includes('unavailable')}
 check('unsupported browser sharing fails visibly',unavailable);
 global.nativeApp=true;
 await exportData('save','synthetic.txt','text/plain',encoded,text);
 check('mock native save requests explicit action',JSON.parse(prompts[0][1]).action==='save');
 check('mock native payload exact',JSON.parse(prompts[0][1]).data===encoded);
 window.prompt=()=> 'cancelled';let rejected=false;try{await exportData('save','synthetic.txt','text/plain',encoded,text)}catch(e){rejected=e.message==='cancelled'}
 check('mock native refusal not called saved',rejected);
 const out={checks,passed:checks.filter(x=>x.status==='PASS').length,failed:checks.filter(x=>x.status==='FAIL').length,actual_phone_rendering:false,native_picker_share_save:false,platform_apis_mocked:true};
 fs.writeFileSync(path.join(__dirname,'EXPORT_ADAPTER_RESULTS.json'),JSON.stringify(out,null,2));
 console.log(JSON.stringify(out));
}
main().catch(e=>{console.error(e.message);process.exitCode=1}).finally(()=>{global.setTimeout=originalTimeout});
