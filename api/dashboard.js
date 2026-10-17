'use strict';
let token = '', expiresAt = 0, timer, config;
const el = id => document.getElementById(id);
const b64 = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const labels = {cpu:'CPU ECS',memory:'Memoria ECS',alb_requests:'Solicitudes ALB / minuto',alb_latency:'Latencia p95 ALB',alb_5xx:'Errores 5xx del ALB / minuto',target_5xx:'Errores 5xx backend / minuto',gateway_requests:'Solicitudes Gateway / minuto',gateway_latency:'Latencia p95 Gateway',gateway_4xx:'Respuestas 4xx Gateway / minuto',gateway_5xx:'Errores 5xx Gateway / minuto'};
function node(tag, text, cls) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
function message(text, warning = false) { el('status').textContent = text; el('status').className = warning ? 'status warn' : 'status'; }
async function login() {
  if (!config.client_id || !config.oauth_base) throw new Error('OAuth no está configurado en este entorno.');
  const verifier = b64(crypto.getRandomValues(new Uint8Array(48))), state = b64(crypto.getRandomValues(new Uint8Array(24)));
  sessionStorage.setItem('infra_pkce', JSON.stringify({verifier,state,created:Date.now()}));
  const challenge = b64(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  const url = new URL(config.oauth_base + '/oauth2/authorize');
  url.search = new URLSearchParams({response_type:'code',client_id:config.client_id,redirect_uri:location.origin+'/dashboard',scope:'openid email infra-metrics/read',state,code_challenge:challenge,code_challenge_method:'S256'});
  location.assign(url);
}
function chart(points) {
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns,'svg');
  svg.setAttribute('viewBox','0 0 300 70'); svg.setAttribute('role','img');svg.setAttribute('aria-label','Serie de los últimos 15 minutos');
  if (points.length < 2) return svg;
  const max = Math.max(...points.map(p=>p.value), 0.001), first=Date.parse(points[0].at), span=Math.max(1,Date.parse(points[points.length-1].at)-first), line=document.createElementNS(ns,'polyline');
  line.setAttribute('points',points.map(p=>`${(Date.parse(p.at)-first)/span*300},${65-p.value/max*60}`).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#61ddb4');line.setAttribute('stroke-width','2');svg.append(line);return svg;
}
function render(s) {
  const age = (Date.now()-Date.parse(s.collected_at))/1000;
  message(`Fuente: AWS CloudWatch + ECS · Guardado: ${new Date(s.collected_at).toLocaleString()} · Antigüedad del snapshot: ${Math.max(0,Math.round(age))} s${age>180?' · SNAPSHOT DESACTUALIZADO':''}`,age>180);
  const svc=el('service');svc.hidden=false;svc.replaceChildren(node('h2',s.service.id),node('p',`Entorno: ${s.service.environment} · Estado: ${s.service.status} · Tareas: ${s.service.running_tasks}/${s.service.desired_tasks} · Pendientes: ${s.service.pending_tasks}`),node('code',s.service.task_definition));
  el('metrics').replaceChildren();
  for (const m of s.metrics) {
    const card=node('article',undefined,'card'), p=m.points[m.points.length-1], old=p&&(Date.now()-Date.parse(p.at)>300000);
    card.append(node('div',labels[m.id]||m.name),node('div',p?`${Number(p.value.toFixed(3)).toLocaleString()} ${m.unit}`:'Sin datos','value'),chart(m.points),node('p',p?`Medido: ${new Date(p.at).toLocaleString()}${old?' · DESACTUALIZADO':''}`:'CloudWatch no devolvió muestras para este periodo.','detail'),node('p',`${m.namespace} · ${m.statistic} · periodo ${m.period_seconds} s · ${m.status}`,'detail'));el('metrics').append(card);
  }
  const table=node('table'), head=node('tr');for(const label of ['Despliegue','Estado','Rollout','Creado'])head.append(node('th',label));table.append(head);
  for(const d of s.deployments){const row=node('tr');for(const value of [d.id,d.status,d.rollout_state,d.created_at?new Date(d.created_at).toLocaleString():'Sin fecha'])row.append(node('td',value));table.append(row)}el('deployments').replaceChildren(table);
}
async function poll() {
  if (!token || Date.now() >= expiresAt) {token='';message('Sesión vencida. Inicia sesión para continuar.',true);el('login').disabled=false;return;}
  try {const r=await fetch('/v1/metrics',{headers:{Authorization:`Bearer ${token}`},cache:'no-store'});if(!r.ok){if(r.status===401){token='';el('login').disabled=false;}throw new Error(`API respondió ${r.status}; las cifras anteriores pueden estar desactualizadas.`);}render(await r.json());}
  catch(e){message(e.message,true);}finally{if(token)timer=setTimeout(poll,3000);}
}
(async()=>{
  try {
    config=await (await fetch('/dashboard/config')).json();el('login').onclick=()=>login().catch(e=>message(e.message,true));
    const params=new URLSearchParams(location.search);const saved=sessionStorage.getItem('infra_pkce');
    if(params.has('error')){history.replaceState(null,'','/dashboard');sessionStorage.removeItem('infra_pkce');throw new Error('Cognito no completó el acceso. Intenta iniciar sesión de nuevo.');}
    if(!params.has('code'))return;
    const pkce=saved?JSON.parse(saved):null;sessionStorage.removeItem('infra_pkce');history.replaceState(null,'','/dashboard');
    if(!pkce||pkce.state!==params.get('state')||Date.now()-pkce.created>600000)throw new Error('Validación OAuth fallida. Inicia sesión otra vez.');
    const response=await fetch(config.oauth_base+'/oauth2/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'authorization_code',client_id:config.client_id,redirect_uri:location.origin+'/dashboard',code:params.get('code'),code_verifier:pkce.verifier})});
    if(!response.ok)throw new Error('No fue posible completar el intercambio de Cognito.');const data=await response.json();if(!data.access_token)throw new Error('Cognito no devolvió un access token.');token=data.access_token;expiresAt=Date.now()+data.expires_in*1000;el('login').disabled=true;await poll();
  }catch(e){message(e.message,true);}
})();
