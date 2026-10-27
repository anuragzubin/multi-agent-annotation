const $ = id => document.getElementById(id);
let audioFiles = [], currentJob = null, running = false;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const STT_APIS = {
  openai:{label:'OpenAI-compatible (OpenAI, Groq, …)',url:'https://api.openai.com/v1/audio/transcriptions',model:'whisper-1',modelLabel:'Model'},
  azure:{label:'Azure AI Speech (fast transcription)',url:'https://<resource>.cognitiveservices.azure.com/speechtotext/transcriptions:transcribe?api-version=2025-10-15',model:'',modelLabel:'Locales (optional, e.g. en-US or en-US,hi-IN)'},
  deepgram:{label:'Deepgram',url:'https://api.deepgram.com/v1/listen',model:'nova-3',modelLabel:'Model'},
  elevenlabs:{label:'ElevenLabs',url:'https://api.elevenlabs.io/v1/speech-to-text',model:'scribe_v1',modelLabel:'Model ID'}
};
function providerForm(id, title, badge, model, url) {
  return `<div class="provider"><h3><b>${badge}</b>${title}</h3><label for="${id}-url">API endpoint</label><input id="${id}-url" type="url" value="${url}" autocomplete="off"><label for="${id}-model">Model</label><input id="${id}-model" value="${model}" autocomplete="off"><label for="${id}-key">API key</label><input id="${id}-key" type="password" placeholder="Enter your API key" autocomplete="off"></div>`;
}
function sttForm(id, title, badge, kind, model, url) {
  const options = Object.entries(STT_APIS).map(([value,api]) => `<option value="${value}"${value===kind?' selected':''}>${api.label}</option>`).join('');
  return `<div class="provider"><h3><b>${badge}</b>${title}</h3><label for="${id}-kind">Speech API</label><select id="${id}-kind">${options}</select><label for="${id}-url">API endpoint</label><input id="${id}-url" type="url" value="${url}" autocomplete="off"><label for="${id}-model" id="${id}-model-label">${STT_APIS[kind].modelLabel}</label><input id="${id}-model" value="${model}" autocomplete="off"><label for="${id}-key">API key</label><input id="${id}-key" type="password" placeholder="Enter your API key" autocomplete="off"></div>`;
}
$('providers').innerHTML = sttForm('a','STT provider A','A','openai','whisper-1','https://api.openai.com/v1/audio/transcriptions') + sttForm('b','STT provider B','B','openai','whisper-large-v3-turbo','https://api.groq.com/openai/v1/audio/transcriptions');
$('agents').innerHTML = providerForm('transcriber','Transcriber agent','T','gpt-audio','https://api.openai.com/v1/chat/completions') + providerForm('reviewer','Reviewer agent','R','gpt-audio','https://api.openai.com/v1/chat/completions');
$('providers').addEventListener('change',e=>{
  const select=e.target.closest('select[id$="-kind"]');if(!select)return;
  const id=select.id.slice(0,-5), api=STT_APIS[select.value];
  const url=$(`${id}-url`), model=$(`${id}-model`);
  if(!url.value.trim()||Object.values(STT_APIS).some(a=>a.url===url.value.trim())) url.value=api.url;
  if(!model.value.trim()||Object.values(STT_APIS).some(a=>a.model&&a.model===model.value.trim())) model.value=api.model;
  $(`${id}-model-label`).textContent=api.modelLabel;
});
function config(id) {
  const c=Object.fromEntries(['url','model','key'].map(k => [k,$(`${id}-${k}`).value.trim()]));
  if($(`${id}-kind`)) c.kind=$(`${id}-kind`).value;
  return c;
}
function showFiles() {
  $('file-count').innerHTML = `${audioFiles.length} <em>in this batch</em>`;
  $('files').innerHTML = audioFiles.map((item,i) => `<div><div class="file-row"><div class="file-name">♫ &nbsp; ${esc(item.file.name)}<small>${(item.file.size / 1024 / 1024).toFixed(2)} MB · two submissions</small></div><button class="remove" data-remove="${i}" aria-label="Remove ${esc(item.file.name)}" ${running?'disabled':''}>✕</button></div><details class="reference"><summary>Optional reference transcript · ${esc(item.file.name)}</summary><textarea data-reference="${i}" rows="3" placeholder="A trusted reference enables measured word error rate.">${esc(item.reference)}</textarea></details></div>`).join('');
}
function addFiles(files) {
  if(running) return;
  let errors=[];
  for(const file of files) {
    if(audioFiles.some(x=>x.file.name===file.name)){errors.push(`${file.name}: filename already added.`);continue;}
    if(!/\.(mp3|wav)$/i.test(file.name)) {errors.push(`${file.name}: use MP3 or WAV.`);continue;}
    if(!file.size || file.size > 20*1024*1024) {errors.push(`${file.name}: must be nonempty and at most 20 MB.`);continue;}
    if(audioFiles.length>=10 || audioFiles.reduce((n,x)=>n+x.file.size,0)+file.size>45*1024*1024) {errors.push('Batch limit: 10 files and 45 MB total.');break;}
    audioFiles.push({file,reference:''});
  }
  showFiles(); if(errors.length) alert(errors.join('\n'));
}
$('audio').addEventListener('change',e=>{addFiles(e.target.files);e.target.value='';});
$('drop').addEventListener('dragover',e=>{e.preventDefault();$('drop').classList.add('drag');});
$('drop').addEventListener('dragleave',()=>$('drop').classList.remove('drag'));
$('drop').addEventListener('drop',e=>{e.preventDefault();$('drop').classList.remove('drag');addFiles(e.dataTransfer.files);});
$('files').addEventListener('click',e=>{const button=e.target.closest('[data-remove]');if(button&&!running){audioFiles.splice(+button.dataset.remove,1);showFiles();}});
$('files').addEventListener('input',e=>{if(e.target.dataset.reference!==undefined) audioFiles[+e.target.dataset.reference].reference=e.target.value;});
function base64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});}
function renderResult(result) {
 const last=result.history.at(-1);
 return `<article class="result-card"><div class="result-head"><h4>Provider ${result.provider} <span class="subtle">${esc(result.provider_model)}</span></h4><span class="badge ${result.accepted?'':'flagged'}">${result.accepted?'WITHIN THRESHOLD':'NEEDS ATTENTION'}</span></div><div class="metric-row"><div><strong>${last.agreement}%</strong><small>AGREEMENT</small></div><div><strong>${last.error_rate}%</strong><small>${last.reference_wer===null?'ESTIMATED ERRORS':'MAX OF WER & REVIEW ERRORS'}</small></div><div><strong>${result.history.length}</strong><small>CYCLES</small></div></div><div class="transcript">${esc(last.transcript)}</div><details><summary>Original STT draft</summary><div class="transcript">${esc(result.auto_transcript)}</div></details><details><summary>Reviewer feedback & rework history · ${result.history.length} cycles</summary>${result.history.map(h=>`<h4>Cycle ${h.cycle} · ${h.error_rate}% errors</h4><p class="small">Reviewer estimate: ${h.estimated_error_rate}%${h.reference_wer===null?'':` · Reference WER: ${h.reference_wer}%`}</p><ul>${h.review.issues.map(x=>`<li>${esc(x)}</li>`).join('')||'<li>No issues reported.</li>'}</ul><details><summary>Submitted transcript</summary><div class="transcript">${esc(h.transcript)}</div></details>`).join('')}</details></article>`;
}
function render(job) {
 currentJob=job;
 $('status').textContent=job.activity;
 const groups=new Map();for(const result of job.results){if(!groups.has(result.file))groups.set(result.file,[]);groups.get(result.file).push(result);}
 $('results').innerHTML=[...groups].map(([file,rs])=>`<div class="result-pair"><h3>${esc(file)}</h3><div class="result-columns">${rs.map(renderResult).join('')}${rs.length===1&&job.status==='running'?'<div class="pending">The second submission is being processed…</div>':''}</div></div>`).join('')+(job.status==='failed'?`<div class="error">${esc(job.activity)} Completed submissions are available above. Correct the provider settings and start a new run.</div>`:'')+(!job.results.length&&job.status==='running'?'<div class="pending">Processing audio and running agents. This may take several minutes per cycle.</div>':'');
 if(job.results.length){const score=job.results.reduce((n,r)=>n+r.history.at(-1).agreement,0)/job.results.length;$('agreement').innerHTML=`${score.toFixed(1)}% <em>${job.status==='running'?'partial mean':'mean agreement'}</em>`;}
 $('export').hidden=!job.results.length;
}
$('run').addEventListener('click',async()=>{
 const providers=[config('a'),config('b')],transcriber=config('transcriber'),reviewer=config('reviewer');
 if(!audioFiles.length) return alert('Add at least one audio file.');
 if(![transcriber,reviewer].every(c=>c.url.startsWith('https://')&&c.model&&c.key)) return alert('Set a HTTPS endpoint, model and API key for both agents. Expand Agent configuration to enter agent keys.');
 if(!providers.every(c=>c.url.startsWith('https://')&&c.key&&(c.model||c.kind==='azure'))) return alert('Set a HTTPS endpoint, API key and model for both STT providers. Azure takes optional locales instead of a model.');
 if(['kind','url','model'].every(k=>providers[0][k]===providers[1][k])) return alert('Choose different STT APIs, endpoints or models for the two sources.');
 if(!Number.isInteger(+$('cycles').value)||+$('cycles').value<1||+$('cycles').value>10) return alert('Choose 1–10 review cycles.');
 if(!$('guidelines').value.trim()) return alert('Enter transcription guidelines.');
 running=true;$('run').disabled=true;$('run').textContent='Agents working…';$('agreement').innerHTML='— <em>awaiting review</em>';$('export').hidden=true;
 try{
   const files=await Promise.all(audioFiles.map(async x=>({name:x.file.name,data:await base64(x.file),reference:x.reference})));
   const response=await fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({files,providers,transcriber,reviewer,guidelines:$('guidelines').value,max_cycles:+$('cycles').value})});
   const result=await response.json();if(!response.ok)throw Error(result.error);
   $('results-section').scrollIntoView({behavior:'smooth',block:'start'});
   while(true){const res=await fetch(`/api/jobs/${result.id}`);const job=await res.json();if(!res.ok)throw Error(job.error);render(job);if(job.status!=='running')break;await new Promise(r=>setTimeout(r,1800));}
 }catch(error){$('status').textContent='Unable to finish';$('results').innerHTML=`<div class="error">${esc(error.message)}</div>`;}
 finally{running=false;$('run').disabled=false;$('run').innerHTML='Start annotation <span>→</span>';}
});
$('export').addEventListener('click',()=>{if(!currentJob)return;const url=URL.createObjectURL(new Blob([JSON.stringify(currentJob,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='accord-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
