// Structured JSON editors use DOM nodes only; no HTML or executable templates.
function structuredField(initial,key){
 const box=document.createElement('div');box.className='structured-fields';
 const hidden=document.createElement('input');hidden.type='hidden';box.append(hidden);
 let data=initial??(['flags','shop_buy_filter','objectives','definition'].includes(key)?[]:{});
 const sync=()=>{hidden.value=JSON.stringify(data);};
 const renderValue=(value,onchange)=>{
  const panel=document.createElement('div');panel.className='field-panel';
  if(value!==null&&typeof value==='object'){
   const array=Array.isArray(value);
   for(const [k,v] of Object.entries(value)){
    const line=document.createElement('div');line.className='field-row';
    const label=document.createElement('span');label.textContent=array?'Entry '+(Number(k)+1):k.replaceAll('_',' ');
    line.append(label,renderValue(v,x=>{value[k]=x;onchange(value);}));
    const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';remove.onclick=()=>{if(array)value.splice(Number(k),1);else delete value[k];onchange(value);draw();};line.append(remove);panel.append(line);
   }
   const name=document.createElement('input');name.placeholder=array?'New value':'Property name';name.setAttribute('aria-label',name.placeholder);
   const type=document.createElement('select');for(const t of ['text','number','checkbox','object','list']){const o=document.createElement('option');o.textContent=t;type.append(o);}
   const add=document.createElement('button');add.type='button';add.textContent='Add';add.onclick=()=>{if(!name.value.trim())return;const v=type.value==='number'?0:type.value==='checkbox'?false:type.value==='object'?{}:type.value==='list'?[]:array?name.value:'';if(array)value.push(v);else if(!['__proto__','constructor','prototype'].includes(name.value))value[name.value]=v;onchange(value);draw();};panel.append(name,type,add);
  }else{
   const input=document.createElement('input');input.type=typeof value==='boolean'?'checkbox':typeof value==='number'?'number':'text';if(input.type==='checkbox')input.checked=value;else input.value=value??'';input.oninput=()=>onchange(input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value);panel.append(input);
  }
  return panel;
 };
 function draw(){box.replaceChildren(hidden);if(key==='flags'){
  const choices=new Set(['MINING_NODE','HERBALISM_NODE','SKINNING_NODE','FISHING_NODE','LOGGING_NODE','FARMING_NODE','HUNTING_NODE','SMITHING_STATION','ALCHEMY_STATION','COOKING_STATION','RUNECRAFTING_STATION','BREWING_STATION','TAVERN','AGGRESSIVE','CAN_HIDE','NODE','SAFE_ZONE','LIT','OUTDOORS','SHOP','BANK','ROUGH_TERRAIN','MUD','SNOWY','CIVILIAN','SKINNABLE','PATROL','FLEES','NOSELL',...data]);
  for(const flag of choices){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=data.includes(flag);input.onchange=()=>{data=input.checked?[...data,flag]:data.filter(x=>x!==flag);sync();};label.append(input,document.createTextNode(flag));box.append(label);}
 }else {if(key==='details'){for(const [title,preset] of [['Door',{is_door:true,is_open:false,is_locked:true,lockpick_dc:15}],['River crossing',{skill_check:{skill:'swimming',dc:16,fail_damage:8}}],['Rockwall',{skill_check:{skill:'climbing',dc:16,fail_damage:8}}]]){const b=document.createElement('button');b.type='button';b.textContent='Use '+title;b.onclick=()=>{data=structuredClone(preset);draw();};box.append(b);}}box.append(renderValue(data,v=>{data=v;sync();}));}sync();}
 draw();return {box,input:hidden};
}
function inspectValue(value){
 if(value===null||typeof value!=='object'){const p=document.createElement('span');p.textContent=String(value??'—');return p;}
 const dl=document.createElement('dl');for(const [key,v] of Object.entries(value)){const dt=document.createElement('dt');dt.textContent=key.replaceAll('_',' ');const dd=document.createElement('dd');dd.append(inspectValue(v));dl.append(dt,dd);}return dl;
}
function creationWizard(){
 const fields=$('fields');if(current||!['rooms','item_templates'].includes(table.name))return;
 const labels=[...fields.children],steps=[[],[],[]];
 for(const label of labels){const key=label.querySelector('[data-key]')?.dataset.key;steps[['name','description','type','area_id'].includes(key)?0:['stats','flags','spawners','damage_type'].includes(key)?1:2].push(label);}
 const controls=document.createElement('div');controls.className='toolbar';const back=node('button','Back'),next=node('button','Next'),heading=node('p','');back.type=next.type='button';controls.append(back,heading,next);fields.prepend(controls);let step=0;
 const save=$('editForm').querySelector('[type=submit]');function draw(){steps.forEach((group,i)=>group.forEach(label=>label.hidden=i!==step));heading.textContent=['1 · Identity and description','2 · Mechanics and flags','3 · Placement and review'][step];back.disabled=step===0;next.hidden=step===2;save.hidden=step!==2;}
 back.onclick=()=>{step--;draw();};next.onclick=()=>{for(const label of steps[step]){const input=label.querySelector('[data-key]');if(input&&!input.reportValidity())return;}step++;draw();};draw();
}
