const $=id=>document.getElementById(id);let catalog=[],table,offset=0,current=null;
async function api(path,method='GET',body){const r=await fetch('/api/admin/'+path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail));return d;}
function notice(t){$('notice').textContent=t;}function node(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}
async function status(){const s=await api('status');$('stats').replaceChildren(...[['Players online',s.players],['Rooms',s.rooms],['Active NPCs',s.npcs]].map(([k,v])=>{const c=node('div',k);c.className='card stat';c.append(node('strong',v));return c;}));}
const pageSize=10;
function showRows(rows,editable=false){
 const t=node('table','');t.className='entity-list';
 if(!rows.length){$('rows').replaceChildren(node('p','No entries found.'));return;}
 const keys=['id',...['name','first_name','direction','level','min_level','profession','room_id','source_room_id','destination_room_id','attack_type','max_coinage'].filter(k=>rows.some(r=>k in r))].slice(0,5);
 const header=node('tr','');keys.forEach(k=>header.append(node('th',k.replaceAll('_',' '))));header.append(node('th','Actions'));t.append(header);
 for(const r of rows){const tr=node('tr','');for(const k of keys)tr.append(node('td',r[k]??'—'));const td=node('td',''),view=node('button',editable?'Inspect / edit':'Inspect');view.onclick=()=>{if(editable)edit(r);else{const panel=node('section','');panel.className='entity-inspector';const back=node('button','Back to list');back.onclick=()=>load();panel.append(back,inspectValue(r));$('rows').replaceChildren(panel);}};td.append(view);tr.append(td);t.append(tr);}
 $('rows').replaceChildren(t);
}
async function load(){if(!table)return;if(['characters','character_equipment','character_stats','character_skills','character_abilities'].includes(table.name)){await characterList();return;}
 const result=await api(`entity-page/${table.name}?limit=${pageSize}&offset=${offset}&q=${encodeURIComponent($('search').value)}&area_id=${encodeURIComponent($('areaSelect').value||'1')}`);
 $('title').textContent=table.name.replaceAll('_',' ');$('new').hidden=!table.editable;showRows(result.rows,table.editable);pageControls(result.total);
}
function pageControls(total){const pages=Math.max(1,Math.ceil(total/pageSize));$('pageLabel').textContent=`Page ${Math.floor(offset/pageSize)+1} of ${pages} · ${total} entries`;$('pageJump').max=pages;$('pageJump').value=Math.floor(offset/pageSize)+1;$('previous').disabled=offset===0;$('next').disabled=offset+pageSize>=total;}
function edit(row){current=row;$('fields').replaceChildren();$('editError').textContent='';$('editTitle').textContent=(row?'Edit ':'Create ')+table.name.replaceAll('_',' ');for(const col of table.columns){const k=col.column_name;if(['id','created_at','updated_at','claimed_by','claimed_at','instance_id','remaining','depleted_at','uses'].includes(k))continue;const label=node('label',({max_coinage:'Maximum Talons (0 disables coin drops)',drop_chance:'Item drop chance (0–1)',damage_rng:'Damage die maximum',speed:'Roundtime seconds'}[k]||k.replaceAll('_',' ')));let input;const value=row?.[k];if(['jsonb','json'].includes(col.data_type)){const field=guidedField(typeof value==='string'?JSON.parse(value):value,k,table.name);input=field.input;label.append(field.box);}
else if(k==='description'||k==='lore'||k==='script_text'){input=document.createElement('textarea');input.value=value===undefined?'':typeof value==='object'?JSON.stringify(value,null,2):value;}
else if(references[k]){const field=referenceField(references[k],value);input=field.input;label.append(field.box);}
else if(k==='type'&&table.name==='item_templates'){input=choice(itemKinds,value);}
else if(k==='ability_type'){input=choice(['SPELL','ABILITY'],value);}
else if(k==='target_type'){input=choice(['SELF','CHAR','MOB','CHAR_OR_MOB','AREA','NONE'],value);}
else if(k==='effect_type'){input=choice(['DAMAGE','HEAL','BUFF','DEBUFF','MODIFIED_ATTACK','STUN_ATTEMPT','CURE','RESURRECT','CONTESTED_DEBUFF'],value);}
else if(k==='attack_type'){input=choice(['physical','ranged','spell','breath',...damageKinds],value);}
else if(k==='damage_type'){input=choice(damageKinds,value);}
else if(k==='profession'){input=choice(table.name==='recipes'?['smithing','alchemy','cooking','runecrafting','brewing']:['mining','herbalism','skinning','fishing','logging','farming','hunting'],value);}
else if(col.data_type==='boolean'){input=document.createElement('select');for(const [v,t] of [['','Use default'],['true','Yes'],['false','No']]){const option=node('option',t);option.value=v;input.append(option);}input.value=value===undefined?'':String(value);}
else{input=document.createElement('input');input.value=value??'';if(['integer','bigint','real','double precision','numeric'].includes(col.data_type)){input.type='number';input.step='any';}}
input.dataset.key=k;input.dataset.type=col.data_type;input.dataset.nullable=col.is_nullable;input.placeholder=col.column_default?'Default: '+col.column_default:col.is_nullable==='YES'?'Optional':'Required';if(!row&&col.is_nullable==='NO'&&!col.column_default)input.required=true;if(!input.parentNode)label.append(input);$('fields').append(label);}$('editForm').querySelector('[type=submit]').hidden=false;creationWizard();if(table.name==='rooms'&&row)roomExits(row);if(table.name==='exits'&&row)exitDeleteButton(row);$('editor').showModal();}
$('editForm').onsubmit=async e=>{e.preventDefault();const values={};try{for(const input of $('fields').querySelectorAll('[data-key]')){let v=input.value;const k=input.dataset.key,type=input.dataset.type;if(v===''){if(!current)continue;v=input.dataset.nullable==='YES'?null:'';}else if(['json','jsonb'].includes(type))v=JSON.parse(v);else if(type==='boolean')v=v==='true';else if(['integer','bigint','real','double precision','numeric'].includes(type))v=Number(v);if(!current||JSON.stringify(current[k])!==JSON.stringify(v))values[k]=v;}if(!Object.keys(values).length){$('editor').close();return;}await api('entities/'+table.name,'POST',{values,original:current});$('editor').close();notice('Saved. Publish to load these world definitions without disconnecting players.');await load();}catch(e){$('editError').textContent=e.message;}};
$('goPage').onclick=()=>{offset=(Math.max(1,Math.min(Number($('pageJump').max)||1,Number($('pageJump').value)||1))-1)*pageSize;load().catch(e=>notice(e.message));};
$('cancel').onclick=()=>$('editor').close();$('new').onclick=()=>edit(null);$('find').onclick=()=>{offset=0;load().catch(e=>notice(e.message));};$('search').onkeydown=e=>{if(e.key==='Enter')$('find').click();};$('previous').onclick=()=>{offset=Math.max(0,offset-pageSize);load().catch(e=>notice(e.message));};$('next').onclick=()=>{offset+=pageSize;load().catch(e=>notice(e.message));};$('refresh').onclick=()=>status().catch(e=>notice(e.message));$('publish').onclick=async()=>{try{await api('publish','POST');notice('World published. Connected players and progress were preserved.');await status();}catch(e){notice(e.message);}};
$('logs').onclick=async()=>{try{const d=await api('logs');$('title').textContent='Runtime logs & builder audit';$('rows').replaceChildren(node('pre',JSON.stringify(d,null,2)));}catch(e){notice(e.message);}};$('live').onclick=async()=>{try{const s=await api('status');$('title').textContent='Live characters & NPCs';showRows([...s.online.map(c=>({...c,kind:'player'})),...s.mobs.map(c=>({...c,kind:'NPC'}))]);}catch(e){notice(e.message);}};
(async()=>{try{catalog=await api('catalog');$('builder').hidden=false;notice('Builder access confirmed.');for(const entry of catalog){const b=node('button',entry.name.replaceAll('_',' ')+(entry.editable?'':' ◇'));b.onclick=()=>{table=entry;offset=0;$('search').value='';load().catch(e=>notice(e.message));};$('catalog').append(b);}table=catalog.find(t=>t.name==='rooms');await status();await load();}catch(e){notice(e.message+'. Sign in through the realm with a builder account.');}})();

async function loadBuilds(){const builds=await api('builds');$('buildStates').replaceChildren(...builds.map(b=>{const o=node('option',b.name+' · '+b.created_at);o.value=b.id;return o;}));}
$('saveBuild').onclick=async()=>{try{await api('builds','POST',{name:$('buildName').value});await loadBuilds();notice('Build state saved.');}catch(e){notice(e.message);}};
$('restoreBuild').onclick=async()=>{try{if(!$('buildStates').value)return;const result=await api('builds/'+$('buildStates').value+'/restore','POST');notice(result.note);await load();await status();}catch(e){notice(e.message);}};
loadBuilds().catch(()=>{});

async function roomExits(room){
 const panel=node('section','');panel.append(node('h3','Exits from this room'));$('fields').prepend(panel);
 try{const map=await api('map?area_id='+room.area_id);for(const exit of map.exits.filter(e=>e.source_room_id===room.id)){
 const button=node('button',exit.direction+' → '+(map.rooms.find(r=>r.id===exit.destination_room_id)?.name||'another area'));button.type='button';button.onclick=()=>{$('editor').close();table=catalog.find(t=>t.name==='exits');const row={...exit,details:typeof exit.details==='string'?JSON.parse(exit.details):exit.details};edit(row);};panel.append(button);}
 const add=node('button','Connect a room');add.type='button';add.onclick=()=>{$('editor').close();table=catalog.find(t=>t.name==='exits');edit(null);$('fields').querySelector('[data-key="source_room_id"]').value=room.id;};panel.append(add);
 }catch(e){panel.append(node('p',e.message));}
}
api('entities/areas?limit=100').then(areas=>{for(const a of areas){const o=node('option',a.name);o.value=a.id;$('areaSelect').append(o);}}).catch(e=>notice(e.message));
$('areaSelect').onchange=()=>mapButton.onclick();

const analyticsButton=node('button','Analytics');$('live').after(analyticsButton);analyticsButton.onclick=async()=>{try{const d=await api('analytics');$('title').textContent='Connection and balancing metrics';showRows([...d.connections.map(x=>({category:'Connection',...x})),...d.economy.map(x=>({category:'Economy',...x})),...d.gameplay.map(x=>({category:'Gameplay',...x}))]);}catch(e){notice(e.message);}};

async function characterList(){
 const result=await api(`entity-page/characters?limit=${pageSize}&offset=${offset}&q=${encodeURIComponent($('search').value)}`),rows=result.rows;pageControls(result.total);
 $('title').textContent='Characters — select one to inspect';$('new').hidden=true;
 const list=node('div','');for(const c of rows){const b=node('button',`${c.first_name} ${c.last_name} · level ${c.level} · ${c.status} · room ${c.location_id}`);b.onclick=()=>characterDetails(c.id,0);list.append(b);}
 list.className='character-selector';$('rows').replaceChildren(list);
}
async function characterDetails(id,page){
 const d=await api(`characters/${id}?offset=${page}`),panel=node('section','');
 panel.className='entity-inspector';panel.append(node('h2',d.character.first_name+' '+d.character.last_name));
 for(const [title,value] of Object.entries({Character:d.character,Attributes:d.stats,Skills:d.skills,Abilities:d.abilities,Conditions:d.conditions,Equipment:d.equipment,Inventory:d.inventory})){const section=node('details','');section.open=['Character','Equipment'].includes(title);section.append(node('summary',title),inspectValue(value));panel.append(section);}
 const prev=node('button','Previous items'),next=node('button','Next items');prev.disabled=page===0;next.disabled=!d.inventory_more;prev.onclick=()=>characterDetails(id,Math.max(0,page-50));next.onclick=()=>characterDetails(id,page+50);panel.append(prev,next);$('rows').replaceChildren(panel);
}
let logOffset=0;
async function logView(){
 const d=await api(`logs?q=${encodeURIComponent($('search').value)}&offset=${logOffset}`);$('title').textContent='Searchable runtime logs — newest first';
 const pre=node('pre',d.runtime.map(e=>new Date(e.time*1000).toISOString()+' '+e.level+' '+e.logger+' '+e.message).join('\n')||'No matching recent entries. Persistent warnings/errors are available in the archive.');
 const prev=node('button','Newer logs'),next=node('button','Older logs'),find=node('button','Search logs');prev.disabled=logOffset===0;next.disabled=!d.has_more;prev.onclick=()=>{logOffset=Math.max(0,logOffset-50);logView();};next.onclick=()=>{logOffset+=50;logView();};find.onclick=()=>{logOffset=0;logView();};$('rows').replaceChildren(find,prev,next,pre);
}
$('logs').onclick=()=>{logOffset=0;logView().catch(e=>notice(e.message));};

let liveOffset=0;
async function liveView(){const s=await api(`status?offset=${liveOffset}`),panel=node('section','');$('title').textContent='Online characters — select one to inspect';for(const c of s.online){const b=node('button',c.name+' · level '+c.level+' · room '+c.room+(c.link_lost?' · link lost':''));b.onclick=()=>characterDetails(c.id,0);panel.append(b);}const prev=node('button','Previous'),next=node('button','Next');prev.disabled=liveOffset===0;next.disabled=s.online.length<50&&s.mobs.length<50;prev.onclick=()=>{liveOffset=Math.max(0,liveOffset-50);liveView();};next.onclick=()=>{liveOffset+=50;liveView();};panel.append(prev,next,node('h3','Live creatures'),inspectValue(s.mobs));$('rows').replaceChildren(panel);}
$('live').onclick=()=>{liveOffset=0;liveView().catch(e=>notice(e.message));};

function exitDeleteButton(row){const panel=node('section',''),button=node('button','Delete this exit direction'),confirm=node('input',''),label=node('label','Type DELETE to confirm removal of this direction. The reverse exit is separate.');confirm.placeholder='DELETE';label.append(confirm);button.type='button';button.onclick=async()=>{if(confirm.value!=='DELETE'){notice('Type DELETE in the exit editor to confirm.');return;}try{const r=await api('exits/'+row.id+'/delete','POST',{original:row});$('editor').close();notice(r.note);await load();}catch(e){$('editError').textContent=e.message;}};panel.append(label,button);$('fields').append(panel);}
