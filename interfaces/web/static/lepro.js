(() => {
const status = document.getElementById('lepro-status');
const list = document.getElementById('lepro-devices');
const button = document.getElementById('lepro-discover');
async function refresh() {
 try { const r = await (await fetch('/api/lepro/selection')).json();
 status.textContent = r.selected ? `${(r.devices || []).length} configured · ${r.registered ? 'ready for commands' : 'setup required'}` : 'No light selected';
 } catch (e) { status.textContent = `Status unavailable: ${e.message}`; }
}
button.addEventListener('click', async () => {
 button.disabled = true; status.textContent = 'Scanning nearby BLE devices…'; list.replaceChildren();
 try {
  const result = await (await fetch('/api/lepro/devices')).json();
  if (result.error) throw new Error(result.error);
  if (!result.devices.length) status.textContent = 'No lights advertising the supported LEPRO service were found.';
  else status.textContent = `Found ${result.devices.length} candidate(s). Choose your light.`;
  for (const device of result.devices) {
   const row = document.createElement('div');
   const select = document.createElement('button'); select.type = 'button';
   select.textContent = `Select ${device.name} (${device.mac})${device.bonded ? '' : ' — bonding required'}`;
   select.disabled = !device.bonded;
   select.addEventListener('click', async () => {
    select.disabled = true;
    if (!window.confirm('The bundled Lepro CLI has only been verified with Lepro ZB1 RGB-IC string lights. Confirm this device is a ZB1 before enabling AI control.')) { select.disabled = false; return; }
    try { const r = await (await fetch('/api/lepro/select', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mac:device.mac,model:'ZB1'})})).json();
      if (!r.ok) throw new Error(r.error); status.textContent = `Selected ${r.name}. Ready for light commands.`;
    } catch(e) { status.textContent = `Selection failed: ${e.message}`; select.disabled = false; }
   });
   row.append(select); list.append(row);
  }
 } catch(e) { status.textContent = `Discovery failed: ${e.message}`; }
 finally { button.disabled = false; }
});
refresh();
})();
