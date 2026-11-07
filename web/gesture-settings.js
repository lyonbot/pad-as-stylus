// Gesture toggles and tuning panel. State lives on the Mac (/api/gestures); the page only edits it.
window.createGestureSettings = ({root, fetchImpl = fetch.bind(window), delay = 150}) => {
 const $ = id => root.querySelector('#' + id);
 const sliders = [...root.querySelectorAll('input[type=range]')];
 const toggles = {panEnabled: $('toggle-pan'), zoomEnabled: $('toggle-zoom')};
 const checks = [...root.querySelectorAll('input[type=checkbox]')];
 let state = {}, timer = null;
 function render() {
  for (const [key, button] of Object.entries(toggles)) {
   button.setAttribute('aria-pressed', String(!!state[key]));
   button.classList.toggle('off', !state[key]);
  }
  for (const input of checks) input.checked = !!state[input.name];
  for (const input of sliders) {
   input.value = state[input.name];
   $('value-' + input.name).textContent = Number(state[input.name]).toFixed(input.step < 1 ? 1 : 0);
  }
 }
 async function push(patch) {
  const response = await fetchImpl('/api/gestures', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(patch)});
  if (response.ok) state = await response.json();
  render();
 }
 async function load() {
  try {const response = await fetchImpl('/api/gestures'); if (response.ok) state = await response.json();} catch {}
  render();
 }
 for (const [key, button] of Object.entries(toggles)) button.onclick = () => push({[key]: !state[key]});
 for (const input of checks) input.onchange = () => push({[input.name]: input.checked});
 for (const input of sliders) input.oninput = () => {
  state[input.name] = Number(input.value); render();
  clearTimeout(timer); timer = setTimeout(() => push({[input.name]: state[input.name]}), delay);
 };
 $('settings-open').onclick = () => { $('settings-panel').hidden = !$('settings-panel').hidden; };
 $('settings-close').onclick = () => { $('settings-panel').hidden = true; };
 $('settings-reset').onclick = () => push(JSON.parse($('settings-panel').dataset.defaults));
 load();
 return {load, get state() { return state; }};
};
