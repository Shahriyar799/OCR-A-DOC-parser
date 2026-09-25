const form = document.querySelector('#upload-form');
const input = document.querySelector('#file-input');
const dropzone = document.querySelector('#dropzone');
const filename = document.querySelector('#filename');
const status = document.querySelector('#status');
const submit = document.querySelector('#submit');
const result = document.querySelector('#result');
const fieldsEl = document.querySelector('#fields');
const notesEl = document.querySelector('#notes');
const documentSummaryEl = document.querySelector('#document-summary');
const crossChecksEl = document.querySelector('#cross-checks');
const preview = document.querySelector('#preview');
const copyButton = document.querySelector('#copy');
const certificateButton = document.querySelector('#certificate');
let latest = null;

const labels = {
  full_name: 'Ad, soyad, ata adı',
  application_date: 'Müraciət tarixi',
  date_of_birth: 'Doğum tarixi',
  birth_place: 'Doğulduğu yer',
  sex: 'Cins',
  citizenship: 'Vətəndaşlıq',
  personal_id: 'FIN / şəxsi kod',
  passport_number: 'Pasport seriyası və nömrəsi',
  passport_issuer: 'Pasportu verən orqan',
  passport_issue_date: 'Pasportun verilmə tarixi',
  passport_expiry: 'Pasportun bitmə tarixi',
  visa_number: 'Viza nömrəsi',
  entry_date: 'Giriş tarixi',
  phone: 'Telefon',
  email: 'E-poçt',
  address: 'Ünvan',
  application_type: 'Müraciət növü',
  permit_basis: 'Vəsatətin əsası',
  basis_note: 'Vəsatətin əsası haqqında qeyd',
  special_note: 'Xüsusi qeyd',
  temporary_permit_history: 'MYİ müraciət tarixçəsi',
  permanent_permit_history: 'DYİ müraciət tarixçəsi',
  conclusion: 'Nəticə',
};

const documentTypeLabels = {
  passport: 'Pasport', application_form: 'Ərizə / anket', birth_certificate: 'Doğum şəhadətnaməsi',
  medical_certificate: 'Tibbi arayış', school_certificate: 'Məktəb arayışı',
  notarized_application: 'Notarial ərizə', property_document: 'Daşınmaz əmlak sənədi',
  residence_permit: 'Yaşayış icazəsi', reference_letter: 'Arayış', other: 'Digər sənəd',
};

const longFields = new Set([
  'address', 'permit_basis', 'basis_note', 'special_note',
  'temporary_permit_history', 'permanent_permit_history', 'conclusion',
]);

const certificateKeys = [
  'full_name', 'application_date', 'citizenship', 'sex', 'passport_number',
  'passport_issuer', 'passport_issue_date', 'passport_expiry', 'date_of_birth',
  'birth_place', 'permit_basis', 'basis_note', 'special_note',
  'temporary_permit_history', 'permanent_permit_history', 'conclusion',
];

function selectedFiles() {
  return Array.from(input.files || []);
}

function updateFiles() {
  const files = selectedFiles();
  if (!files.length) {
    filename.textContent = '';
  } else if (files.length === 1) {
    filename.textContent = files[0].name;
  } else {
    filename.textContent = `${files.length} sənəd seçildi`;
  }
}

input.addEventListener('change', updateFiles);
['dragenter', 'dragover'].forEach(type => dropzone.addEventListener(type, event => {
  event.preventDefault();
  dropzone.classList.add('dragover');
}));
['dragleave', 'drop'].forEach(type => dropzone.addEventListener(type, event => {
  event.preventDefault();
  dropzone.classList.remove('dragover');
}));
dropzone.addEventListener('drop', event => {
  input.files = event.dataTransfer.files;
  updateFiles();
});

function render(data) {
  latest = data;
  result.hidden = false;
  fieldsEl.innerHTML = '';
  notesEl.innerHTML = '';
  documentSummaryEl.innerHTML = '';
  crossChecksEl.innerHTML = '';
  data.notes.forEach(noteText => {
    const note = document.createElement('p');
    note.textContent = noteText;
    notesEl.append(note);
  });

  if (data.documents?.length) {
    const title = document.createElement('h3');
    title.textContent = 'Tanınan sənədlər';
    const list = document.createElement('ul');
    data.documents.forEach(documentInfo => {
      const item = document.createElement('li');
      item.textContent = `${documentInfo.name}: ${documentTypeLabels[documentInfo.document_type] || documentInfo.document_type} · ${documentInfo.page_count} səhifə · ${documentInfo.extraction_method}`;
      list.append(item);
    });
    documentSummaryEl.append(title, list);
  }

  if (data.cross_checks?.length) {
    const title = document.createElement('h3');
    title.textContent = 'Sənədlərarası yoxlama';
    crossChecksEl.append(title);
    data.cross_checks.forEach(check => {
      const item = document.createElement('article');
      item.className = `cross-check ${check.status}`;
      const field = document.createElement('strong');
      field.textContent = labels[check.field] || check.field;
      const message = document.createElement('p');
      message.textContent = check.message;
      const sources = document.createElement('small');
      sources.textContent = check.sources.join(' | ') || 'Mənbə tapılmadı';
      item.append(field, message, sources);
      crossChecksEl.append(item);
    });
  }

  Object.entries(data.fields).forEach(([key, field]) => {
    const box = document.createElement('div');
    box.className = `field${longFields.has(key) ? ' field-wide' : ''}`;
    const label = document.createElement('label');
    label.textContent = labels[key] || key;
    label.htmlFor = `field-${key}`;
    const value = document.createElement(longFields.has(key) ? 'textarea' : 'input');
    value.id = `field-${key}`;
    value.value = field.value;
    value.autocomplete = 'off';
    if (value.tagName === 'TEXTAREA') value.rows = 3;
    const confidence = document.createElement('span');
    confidence.className = `confidence ${field.confidence}`;
    confidence.textContent = field.confidence === 'not_found'
      ? 'Tapılmadı - operator doldurmalıdır'
      : `Etibar: ${field.confidence} · ${field.source || 'mənbə göstərilməyib'}${field.source_page ? ` · səhifə ${field.source_page}` : ''}`;
    box.append(label, value, confidence);
    fieldsEl.append(box);
  });
  preview.textContent = data.text_preview || 'Bu rejimdə mətn ayrıca əldə olunmayıb.';
}

function currentValues() {
  const values = {};
  if (!latest) return values;
  Object.keys(latest.fields).forEach(key => {
    values[key] = document.querySelector(`#field-${key}`).value.trim();
  });
  return values;
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const files = selectedFiles();
  if (!files.length) return;
  submit.disabled = true;
  status.textContent = `${files.length} sənəd analiz edilir…`;
  result.hidden = true;
  try {
    const body = new FormData();
    files.forEach(file => body.append('files', file));
    const response = await fetch('/api/extract-many', {method: 'POST', body});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Xəta baş verdi.');
    render(data);
    status.textContent = data.extraction_method === 'vision'
      ? 'Sənədlər üzrə nəticə hazırdır.'
      : 'PDF mətnləri üzrə nəticə hazırdır.';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

copyButton.addEventListener('click', async () => {
  if (!latest) return;
  await navigator.clipboard.writeText(JSON.stringify(currentValues(), null, 2));
  copyButton.textContent = 'Kopyalandı';
  setTimeout(() => { copyButton.textContent = 'JSON kopyala'; }, 1400);
});

certificateButton.addEventListener('click', async () => {
  if (!latest) return;
  const values = currentValues();
  const payload = {
    recipient: document.querySelector('#report-recipient').value.trim(),
    manager_title: document.querySelector('#manager-title').value.trim(),
    manager_name: document.querySelector('#manager-name').value.trim(),
  };
  certificateKeys.forEach(key => { payload[key] = values[key] || ''; });

  certificateButton.disabled = true;
  status.textContent = 'Arayış PDF-i hazırlanır…';
  try {
    const response = await fetch('/api/certificate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Arayış yaradıla bilmədi.');
    }
    const blob = await response.blob();
    const link = document.createElement('a');
    const safeName = (values.full_name || 'ecnebi').replace(/[^\p{L}\p{N}_-]+/gu, '_');
    link.href = URL.createObjectURL(blob);
    link.download = `arayis_${safeName}.pdf`;
    link.click();
    URL.revokeObjectURL(link.href);
    status.textContent = 'Arayış PDF-i hazırdır.';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    certificateButton.disabled = false;
  }
});
