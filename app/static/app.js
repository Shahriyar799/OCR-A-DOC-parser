const form = document.querySelector('#upload-form');
const input = document.querySelector('#file-input');
const dropzone = document.querySelector('#dropzone');
const filename = document.querySelector('#filename');
const status = document.querySelector('#status');
const submit = document.querySelector('#submit');
const result = document.querySelector('#result');
const fieldsEl = document.querySelector('#fields');
const notesEl = document.querySelector('#notes');
const preview = document.querySelector('#preview');
const copyButton = document.querySelector('#copy');
let latest = null;

const labels = {full_name:'Ad, soyad, ata adı', date_of_birth:'Doğum tarixi', sex:'Cins', citizenship:'Vətəndaşlıq', personal_id:'FIN / şəxsi kod', passport_number:'Pasport nömrəsi', passport_expiry:'Pasportun bitmə tarixi', visa_number:'Viza nömrəsi', entry_date:'Giriş tarixi', phone:'Telefon', email:'E-poçt', address:'Ünvan', application_type:'Müraciət növü'};
function updateFile(file) { if (file) filename.textContent = file.name; }
input.addEventListener('change', () => updateFile(input.files[0]));
['dragenter','dragover'].forEach(type => dropzone.addEventListener(type, e => { e.preventDefault(); dropzone.classList.add('dragover'); }));
['dragleave','drop'].forEach(type => dropzone.addEventListener(type, e => { e.preventDefault(); dropzone.classList.remove('dragover'); }));
dropzone.addEventListener('drop', e => { input.files = e.dataTransfer.files; updateFile(input.files[0]); });
function render(data) {
  latest = data; result.hidden = false; fieldsEl.innerHTML = ''; notesEl.innerHTML = data.notes.map(note => `<p>${note}</p>`).join('');
  Object.entries(data.fields).forEach(([key, field]) => {
    const box = document.createElement('div'); box.className = 'field';
    const label = document.createElement('label'); label.textContent = labels[key]; label.htmlFor = `field-${key}`;
    const value = document.createElement('input'); value.id = `field-${key}`; value.value = field.value; value.autocomplete = 'off';
    const confidence = document.createElement('span'); confidence.className = `confidence ${field.confidence}`; confidence.textContent = field.confidence === 'not_found' ? 'Tapılmadı' : `Etibar: ${field.confidence}`;
    box.append(label, value, confidence); fieldsEl.append(box);
  });
  preview.textContent = data.text_preview || 'Bu rejimdə mətn ayrıca əldə olunmayıb.';
}
form.addEventListener('submit', async event => {
  event.preventDefault(); if (!input.files[0]) return; submit.disabled = true; status.textContent = 'Sənəd analiz edilir…'; result.hidden = true;
  try { const body = new FormData(); body.append('file', input.files[0]); const response = await fetch('/api/extract', {method:'POST', body}); const data = await response.json(); if (!response.ok) throw new Error(data.detail || 'Xəta baş verdi.'); render(data); status.textContent = data.extraction_method === 'vision' ? 'Şəkil üzrə nəticə hazırdır.' : 'PDF mətni üzrə nəticə hazırdır.'; }
  catch (error) { status.textContent = error.message; } finally { submit.disabled = false; }
});
copyButton.addEventListener('click', async () => { if (!latest) return; const values = {}; Object.keys(latest.fields).forEach(key => { values[key] = document.querySelector(`#field-${key}`).value; }); await navigator.clipboard.writeText(JSON.stringify(values, null, 2)); copyButton.textContent = 'Kopyalandı'; setTimeout(() => copyButton.textContent = 'JSON kopyala', 1400); });
