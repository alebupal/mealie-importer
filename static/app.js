let currentRecipe = null;
let currentQuestions = [];
let foodsCache = [];
let unitsCache = [];

// Elementos DOM
const themeToggle = document.getElementById('themeToggle');
const extractForm = document.getElementById('extractForm');
const urlInput = document.getElementById('urlInput');
const btnExtract = document.getElementById('btnExtract');
const btnExtractText = document.getElementById('btnExtractText');
const btnExtractSpinner = document.getElementById('btnExtractSpinner');
const extractError = document.getElementById('extractError');

const questionsSection = document.getElementById('questionsSection');
const questionsList = document.getElementById('questionsList');

const reviewSection = document.getElementById('reviewSection');
const previewImg = document.getElementById('previewImg');
const recipeTitle = document.getElementById('recipeTitle');
const recipeYield = document.getElementById('recipeYield');
const recipeCookTime = document.getElementById('recipeCookTime');
const recipePrepTime = document.getElementById('recipePrepTime');
const recipeCategories = document.getElementById('recipeCategories');
const recipeTags = document.getElementById('recipeTags');
const recipeSource = document.getElementById('recipeSource');
const recipeNotes = document.getElementById('recipeNotes');
const checkUpdate = document.getElementById('checkUpdate');

const ingredientsList = document.getElementById('ingredientsList');
const instructionsList = document.getElementById('instructionsList');
const btnAddIngredient = document.getElementById('btnAddIngredient');
const btnAddStep = document.getElementById('btnAddStep');

const btnCancel = document.getElementById('btnCancel');
const btnImport = document.getElementById('btnImport');
const btnImportText = document.getElementById('btnImportText');
const btnImportSpinner = document.getElementById('btnImportSpinner');

const successModal = document.getElementById('successModal');
const btnNewRecipe = document.getElementById('btnNewRecipe');
const btnOpenMealie = document.getElementById('btnOpenMealie');

const btnChangeImage = document.getElementById('btnChangeImage');
const fileImageInput = document.getElementById('fileImageInput');
const historySection = document.getElementById('historySection');
const historyGrid = document.getElementById('historyGrid');

// --- 1. Inicialización de tema y PWA ---
const savedTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
document.documentElement.setAttribute('data-theme', savedTheme);

themeToggle.addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme') || 'dark';
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
});

// Registrar Service Worker para PWA
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(err => {
    console.log('Service Worker no registrado:', err);
  });
}

// Soporte Web Share Target (cuando se comparte desde el móvil)
window.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const sharedText = params.get('url') || params.get('text') || params.get('title') || '';
  if (sharedText) {
    const urlMatch = sharedText.match(/https?:\/\/[^\s]+/);
    if (urlMatch) {
      urlInput.value = urlMatch[0];
      // Limpiar query params de la barra de direcciones sin recargar
      window.history.replaceState({}, document.title, window.location.pathname);
      extractForm.dispatchEvent(new Event('submit'));
    }
  }
  loadHistory();
});

// --- 2. Cargar lista de alimentos y unidades de Mealie ---
async function loadMealieCatalogs() {
  try {
    const [resFoods, resUnits] = await Promise.all([
      fetch('/api/foods'),
      fetch('/api/units')
    ]);
    if (resFoods.ok) {
      foodsCache = await resFoods.json();
      const dlFoods = document.getElementById('mealieFoodsList');
      dlFoods.innerHTML = foodsCache.map(f => `<option value="${f}">`).join('');
    }
    if (resUnits.ok) {
      unitsCache = await resUnits.json();
      const dlUnits = document.getElementById('mealieUnitsList');
      dlUnits.innerHTML = unitsCache.map(u => `<option value="${u}">`).join('');
    }
  } catch (e) {
    console.warn("No se pudo cargar el catálogo de Mealie:", e);
  }
}
loadMealieCatalogs();

// --- 3. Extracción de receta ---
extractForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  extractError.classList.add('hidden');
  btnExtract.disabled = true;
  btnExtractText.textContent = "Extrayendo...";
  btnExtractSpinner.classList.remove('hidden');

  try {
    const resp = await fetch('/api/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });

    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "Error extrayendo receta del vídeo");
    }

    currentRecipe = data.recipe;
    currentQuestions = data.questions || [];

    renderQuestions(currentQuestions);
    renderReview(currentRecipe);

    reviewSection.classList.remove('hidden');
    reviewSection.scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    extractError.textContent = err.message;
    extractError.classList.remove('hidden');
  } finally {
    btnExtract.disabled = false;
    btnExtractText.textContent = "Analizar receta";
    btnExtractSpinner.classList.add('hidden');
  }
});

// --- 4. Renderizar Preguntas / Dudas ---
function renderQuestions(questions) {
  if (!questions || questions.length === 0) {
    questionsSection.classList.add('hidden');
    questionsList.innerHTML = '';
    return;
  }

  questionsList.innerHTML = questions.map((q, idx) => {
    let actionButtons = '';
    if (q.type === 'similar_food') {
      actionButtons = `
        <button type="button" class="btn-sm btn-sm-primary" onclick="resolveQuestion(${idx}, '${q.recommended}')">
          Usar "${q.recommended}"
        </button>
        <button type="button" class="btn-sm btn-sm-secondary" onclick="dismissQuestion(${idx})">
          Mantener "${q.ingredient}"
        </button>
      `;
    } else if (q.type === 'new_food') {
      actionButtons = `
        <button type="button" class="btn-sm btn-sm-secondary" onclick="dismissQuestion(${idx})">
          Entendido, crear nuevo
        </button>
      `;
    } else {
      actionButtons = `
        <button type="button" class="btn-sm btn-sm-secondary" onclick="dismissQuestion(${idx})">
          Aceptar
        </button>
      `;
    }

    return `
      <div class="question-item" id="q-item-${idx}">
        <div class="question-text">
          <strong>${q.title}</strong>
          <span>${q.description}</span>
        </div>
        <div class="question-actions">
          ${actionButtons}
        </div>
      </div>
    `;
  }).join('');

  questionsSection.classList.remove('hidden');
}

window.resolveQuestion = function(idx, chosenFood) {
  const q = currentQuestions[idx];
  if (!q) return;

  // Actualizar el valor en la fila de ingredientes
  const rows = ingredientsList.querySelectorAll('.ing-row:not(.header)');
  for (const row of rows) {
    const foodInput = row.querySelector('.ing-food');
    if (foodInput && foodInput.getAttribute('data-raw') === q.ingredient) {
      foodInput.value = chosenFood;
      row.style.background = 'var(--ok-bg)';
      setTimeout(() => { row.style.background = ''; }, 1000);
      break;
    }
  }

  dismissQuestion(idx);
};

window.dismissQuestion = function(idx) {
  const el = document.getElementById(`q-item-${idx}`);
  if (el) el.remove();
  if (questionsList.children.length === 0) {
    questionsSection.classList.add('hidden');
  }
};

// --- 5. Renderizar Ficha de Revisión ---
function renderReview(recipe) {
  previewImg.src = recipe.local_image_url || recipe.thumbnail || '';
  recipeTitle.value = recipe.name || '';
  recipeYield.value = recipe.yield || '';
  recipeCookTime.value = recipe.cookTime || '';
  recipePrepTime.value = recipe.prepTime || '';
  recipeCategories.value = (recipe.categories || []).join(', ');
  recipeTags.value = (recipe.tags || []).join(', ');
  recipeSource.value = recipe.source || '';

  const notesText = (recipe.notes || []).map(n => n.text).join('\n');
  recipeNotes.value = notesText;

  renderIngredients(recipe.ingredients || []);
  renderInstructions(recipe.instructions || []);
}

function renderIngredients(ingredients) {
  ingredientsList.innerHTML = '';
  ingredients.forEach((ing) => addIngredientRow(ing));
}

function addIngredientRow(ing = {}) {
  const row = document.createElement('div');
  row.className = 'ing-row';

  const section = ing.section || '';
  const qty = ing.quantity !== null && ing.quantity !== undefined ? ing.quantity : '';
  const unit = ing.unit || '';
  const food = ing.food || '';
  const note = ing.note || '';
  const rawFood = ing.raw_food || food;

  row.innerHTML = `
    <input type="text" class="form-input ing-section" placeholder="Sección" value="${section}" />
    <input type="number" step="any" class="form-input ing-qty" placeholder="Cant." value="${qty}" />
    <input type="text" list="mealieUnitsList" class="form-input ing-unit" placeholder="g, ml..." value="${unit}" />
    <input type="text" list="mealieFoodsList" class="form-input ing-food" placeholder="Alimento" value="${food}" data-raw="${rawFood}" />
    <input type="text" class="form-input ing-note" placeholder="Nota" value="${note}" />
    <button type="button" class="btn-del" title="Eliminar fila">&times;</button>
  `;

  row.querySelector('.btn-del').addEventListener('click', () => row.remove());
  ingredientsList.appendChild(row);
}

btnAddIngredient.addEventListener('click', () => {
  addIngredientRow({ section: '', quantity: '', unit: '', food: '', note: '' });
});

function renderInstructions(instructions) {
  instructionsList.innerHTML = '';
  instructions.forEach((inst, idx) => addInstructionRow(inst.text || '', idx + 1));
}

function addInstructionRow(text = '', num = null) {
  const row = document.createElement('div');
  row.className = 'inst-row';
  const displayNum = num !== null ? num : instructionsList.children.length + 1;

  row.innerHTML = `
    <div class="inst-num">${displayNum}.</div>
    <textarea class="form-textarea inst-textarea" rows="2" placeholder="Describe este paso...">${text}</textarea>
    <button type="button" class="btn-del" title="Eliminar paso">&times;</button>
  `;

  row.querySelector('.btn-del').addEventListener('click', () => {
    row.remove();
    reindexInstructions();
  });

  instructionsList.appendChild(row);
}

btnAddStep.addEventListener('click', () => {
  addInstructionRow('', instructionsList.children.length + 1);
});

function reindexInstructions() {
  const rows = instructionsList.querySelectorAll('.inst-row');
  rows.forEach((row, i) => {
    const numEl = row.querySelector('.inst-num');
    if (numEl) numEl.textContent = `${i + 1}.`;
  });
}

btnCancel.addEventListener('click', () => {
  reviewSection.classList.add('hidden');
  questionsSection.classList.add('hidden');
  currentRecipe = null;
  currentQuestions = [];
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// --- 6. Importar Receta Definitiva ---
btnImport.addEventListener('click', async () => {
  const title = recipeTitle.value.trim();
  if (!title) {
    alert("El título de la receta es obligatorio.");
    recipeTitle.focus();
    return;
  }

  // Recoger ingredientes
  const ingRows = ingredientsList.querySelectorAll('.ing-row:not(.header)');
  const ingredients = [];
  for (const r of ingRows) {
    const sec = r.querySelector('.ing-section').value.trim() || null;
    const qtyStr = r.querySelector('.ing-qty').value.trim();
    const unit = r.querySelector('.ing-unit').value.trim() || null;
    const food = r.querySelector('.ing-food').value.trim();
    const note = r.querySelector('.ing-note').value.trim();

    if (!food && !qtyStr) continue;

    ingredients.push({
      section: sec,
      quantity: qtyStr ? parseFloat(qtyStr) : null,
      unit: unit,
      food: food,
      note: note,
    });
  }

  // Recoger pasos
  const instRows = instructionsList.querySelectorAll('.inst-row');
  const instructions = [];
  for (const r of instRows) {
    const txt = r.querySelector('.inst-textarea').value.trim();
    if (txt) {
      instructions.push({ title: null, text: txt });
    }
  }

  // Recoger notas
  const notesText = recipeNotes.value.trim();
  const notes = notesText ? [{ title: "Nota", text: notesText }] : [];

  // Categorías y tags
  const categories = recipeCategories.value.split(',').map(s => s.trim()).filter(Boolean);
  const tags = recipeTags.value.split(',').map(s => s.trim()).filter(Boolean);

  const payload = {
    name: title,
    description: currentRecipe ? currentRecipe.description : '',
    yield_text: recipeYield.value.trim(),
    prepTime: recipePrepTime.value.trim() || null,
    cookTime: recipeCookTime.value.trim() || null,
    totalTime: null,
    categories: categories,
    tags: tags,
    source: recipeSource.value.trim(),
    orgURL: currentRecipe ? currentRecipe.orgURL : '',
    image_file: currentRecipe ? currentRecipe.image_file : null,
    ingredients: ingredients,
    instructions: instructions,
    notes: notes,
    update_if_exists: checkUpdate.checked,
  };

  btnImport.disabled = true;
  btnImportText.textContent = "Guardando en Mealie...";
  btnImportSpinner.classList.remove('hidden');

  try {
    const resp = await fetch('/api/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const resData = await resp.json();
    if (!resp.ok) {
      throw new Error(resData.detail || "Error importando la receta a Mealie");
    }

    // Modal de éxito
    document.getElementById('modalTitle').textContent = `¡${resData.title} añadida!`;
    document.getElementById('modalDesc').textContent = "La receta y su imagen se han guardado correctamente en tu recetario.";
    btnOpenMealie.href = resData.mealie_url;

    successModal.classList.remove('hidden');
    loadHistory();
  } catch (err) {
    alert("Error al importar: " + err.message);
  } finally {
    btnImport.disabled = false;
    btnImportText.textContent = "Añadir a Mealie";
    btnImportSpinner.classList.add('hidden');
  }
});

// --- Cambio manual de imagen ---
btnChangeImage.addEventListener('click', () => {
  fileImageInput.click();
});

fileImageInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  btnChangeImage.disabled = true;
  btnChangeImage.textContent = "Subiendo imagen...";

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/upload-image', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Error al subir la imagen');
    }

    previewImg.src = data.url;
    if (currentRecipe) {
      currentRecipe.image_file = data.filename;
    }
  } catch (err) {
    alert("No se pudo cambiar la foto: " + err.message);
  } finally {
    btnChangeImage.disabled = false;
    btnChangeImage.textContent = "Cambiar foto 📷";
    fileImageInput.value = '';
  }
});

// --- Historial de Recetas ---
async function loadHistory() {
  try {
    const res = await fetch('/api/history');
    if (!res.ok) return;
    const items = await res.json();
    if (!items || items.length === 0) {
      historySection.classList.add('hidden');
      return;
    }

    historyGrid.innerHTML = items.map(item => {
      const imgTag = item.image_url 
        ? `<img src="${item.image_url}" class="history-thumb" alt="${item.title}" />` 
        : `<div class="history-thumb" style="display:flex;align-items:center;justify-content:center;font-size:2rem;">🍰</div>`;
      
      const dateStr = item.timestamp ? new Date(item.timestamp * 1000).toLocaleDateString() : '';

      return `
        <div class="history-item">
          ${imgTag}
          <div class="history-body">
            <div class="history-title" title="${item.title}">${item.title}</div>
            <div class="history-meta">${item.source || 'Vídeo'} ${dateStr ? '• ' + dateStr : ''}</div>
            <a href="${item.mealie_url}" target="_blank" class="history-link">
              Abrir en Mealie ↗
            </a>
          </div>
        </div>
      `;
    }).join('');

    historySection.classList.remove('hidden');
  } catch (e) {
    console.warn("No se pudo cargar el historial:", e);
  }
}

btnNewRecipe.addEventListener('click', () => {
  successModal.classList.add('hidden');
  reviewSection.classList.add('hidden');
  questionsSection.classList.add('hidden');
  urlInput.value = '';
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// --- 7. Modal de Configuración ---
const settingsBtn = document.getElementById('settingsBtn');
const settingsModal = document.getElementById('settingsModal');
const btnCloseSettings = document.getElementById('btnCloseSettings');
const settingsForm = document.getElementById('settingsForm');
const cfgMealieUrl = document.getElementById('cfgMealieUrl');
const cfgMealieToken = document.getElementById('cfgMealieToken');
const tokenStatusText = document.getElementById('tokenStatusText');
const settingsAlert = document.getElementById('settingsAlert');
const btnTestConn = document.getElementById('btnTestConn');
const navMealieLink = document.getElementById('navMealieLink');

async function loadCurrentConfig() {
  try {
    const res = await fetch('/api/config');
    if (res.ok) {
      const data = await res.json();
      cfgMealieUrl.value = data.url || '';
      navMealieLink.href = data.url || '#';
      if (!data.url) {
        navMealieLink.classList.add('hidden');
      } else {
        navMealieLink.classList.remove('hidden');
      }
      if (data.configured) {
        tokenStatusText.textContent = `Token activo actual: ${data.token_preview}`;
      } else {
        tokenStatusText.textContent = 'No hay token configurado aún.';
      }
    }
  } catch (e) {
    console.warn("No se pudo cargar la configuración actual:", e);
  }
}
loadCurrentConfig();

settingsBtn.addEventListener('click', () => {
  settingsAlert.classList.add('hidden');
  loadCurrentConfig();
  settingsModal.classList.remove('hidden');
});

btnCloseSettings.addEventListener('click', () => {
  settingsModal.classList.add('hidden');
});

btnTestConn.addEventListener('click', async () => {
  settingsAlert.classList.remove('hidden');
  settingsAlert.style.background = 'var(--surface-2)';
  settingsAlert.style.color = 'var(--text)';
  settingsAlert.textContent = 'Probando conexión...';

  try {
    const res = await fetch('/api/test-connection');
    const data = await res.json();
    if (res.ok) {
      settingsAlert.style.background = 'var(--ok-bg)';
      settingsAlert.style.color = 'var(--ok-fg)';
      settingsAlert.textContent = `✓ Conexión exitosa con Mealie (Grupo: ${data.group})`;
    } else {
      throw new Error(data.detail || 'Fallo de conexión');
    }
  } catch (err) {
    settingsAlert.style.background = 'var(--err-bg)';
    settingsAlert.style.color = 'var(--err-fg)';
    settingsAlert.textContent = `✕ ${err.message}`;
  }
});

settingsForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const url = cfgMealieUrl.value.trim();
  const token = cfgMealieToken.value.trim();

  settingsAlert.classList.remove('hidden');
  settingsAlert.style.background = 'var(--surface-2)';
  settingsAlert.style.color = 'var(--text)';
  settingsAlert.textContent = 'Guardando y validando...';

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, token })
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Error al guardar la configuración');
    }

    settingsAlert.style.background = 'var(--ok-bg)';
    settingsAlert.style.color = 'var(--ok-fg)';
    settingsAlert.textContent = '✓ Configuración guardada correctamente';
    cfgMealieToken.value = '';
    loadCurrentConfig();
    loadMealieCatalogs();
    setTimeout(() => { settingsModal.classList.add('hidden'); }, 1200);
  } catch (err) {
    settingsAlert.style.background = 'var(--err-bg)';
    settingsAlert.style.color = 'var(--err-fg)';
    settingsAlert.textContent = `✕ ${err.message}`;
  }
});

