const $ = (id) => document.getElementById(id);
let state = { folder: null, photos: [], categories: [] };
let current = 0;
let mode = localStorage.getItem('photo-sorter-mode') === 'grid' ? 'grid' : 'focus';
let activeCategory = null;
let busy = false;
let toastTimer;

function visiblePhotos() {
  return activeCategory ? state.photos.filter(photo => photo.categories.includes(activeCategory)) : state.photos;
}

function positionKey() {
  return 'photo-sorter-index:' + state.folder + (activeCategory ? ':' + activeCategory : '');
}

async function request(path, data) {
  const response = await fetch(path, data === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Something went wrong.');
  return result;
}

function notify(message, error = false) {
  const toast = $('toast');
  toast.textContent = message;
  toast.className = 'toast visible' + (error ? ' error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.className = 'toast', 3200);
}

async function change(path, data, success) {
  if (busy) return;
  busy = true;
  try {
    const nextState = await request(path, data);
    if (path === '/api/folder') {
      localStorage.setItem('photo-sorter-folder', nextState.folder);
      activeCategory = localStorage.getItem('photo-sorter-filter:' + nextState.folder);
      if (!nextState.categories.includes(activeCategory)) activeCategory = null;
      state = nextState;
      current = Number(localStorage.getItem(positionKey())) || 0;
    } else {
      state = nextState;
      if (!state.categories.includes(activeCategory)) activeCategory = null;
    }
    current = Math.max(0, Math.min(current, visiblePhotos().length - 1));
    rememberPosition();
    render();
    if (success) notify(success);
    return true;
  } catch (error) {
    notify(error.message, true);
    return false;
  } finally {
    busy = false;
  }
}

function photoUrl(photo) { return '/api/photo/' + photo.index; }

function tagButton(category, photo, compact = false) {
  const active = photo.categories.includes(category);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'tag-button' + (active ? ' selected' : '') + (compact ? ' compact' : '');
  button.setAttribute('aria-pressed', String(active));
  button.title = `${active ? 'Remove from' : 'Add to'} ${category}`;
  const dot = document.createElement('span');
  dot.className = 'tag-dot';
  const text = document.createElement('span');
  text.textContent = category;
  button.append(dot, text);
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    change('/api/toggle', { category, filename: photo.name });
  });
  return button;
}

function renderCategories() {
  const list = $('category-list');
  list.replaceChildren();
  $('category-count').textContent = state.categories.length;
  const all = document.createElement('div');
  all.className = 'category-row all-row' + (activeCategory === null ? ' active' : '');
  const allButton = document.createElement('button');
  allButton.type = 'button';
  allButton.className = 'category-filter';
  allButton.setAttribute('aria-pressed', String(activeCategory === null));
  const allSwatch = document.createElement('span');
  allSwatch.className = 'category-swatch';
  const allLabel = document.createElement('span');
  allLabel.className = 'category-label';
  allLabel.textContent = 'All photos';
  const allCount = document.createElement('span');
  allCount.className = 'category-amount';
  allCount.textContent = state.photos.length;
  allButton.append(allSwatch, allLabel, allCount);
  allButton.addEventListener('click', () => setFilter(null));
  all.append(allButton);
  list.append(all);
  if (!state.categories.length) {
    const empty = document.createElement('p');
    empty.className = 'category-empty';
    empty.textContent = 'No categories yet. Add one below.';
    list.append(empty);
  }
  state.categories.forEach((name, index) => {
    const row = document.createElement('div');
    row.className = 'category-row' + (activeCategory === name ? ' active' : '');
    const filter = document.createElement('button');
    filter.type = 'button';
    filter.className = 'category-filter';
    filter.title = `Show only photos in ${name}`;
    filter.setAttribute('aria-pressed', String(activeCategory === name));
    filter.addEventListener('click', () => setFilter(name));
    const swatch = document.createElement('span');
    swatch.className = 'category-swatch';
    const label = document.createElement('span');
    label.className = 'category-label';
    label.textContent = name;
    label.title = name;
    const amount = document.createElement('span');
    amount.className = 'category-amount';
    amount.textContent = state.photos.filter(photo => photo.categories.includes(name)).length;
    const remove = document.createElement('button');
    remove.className = 'remove-category';
    remove.type = 'button';
    remove.textContent = '×';
    remove.title = `Remove ${name}`;
    remove.setAttribute('aria-label', `Remove category ${name}`);
    remove.addEventListener('click', () => {
      if (confirm(`Remove “${name}” and delete its category text file?`))
        change('/api/categories/remove', { name }, `Removed ${name}`);
    });
    filter.append(swatch, label, amount);
    row.append(filter, remove);
    if (index < 9) {
      filter.title += ` · Press ${index + 1} to toggle on the current photo`;
    }
    list.append(row);
  });
}

function renderFocus(photos = visiblePhotos()) {
  const photo = photos[current];
  const image = $('focus-image');
  image.src = photoUrl(photo);
  image.alt = photo.name;
  $('photo-name').textContent = photo.name;
  const count = photo.categories.length;
  $('tag-summary').textContent = count ? `In ${count} ${count === 1 ? 'category' : 'categories'}` : 'Not categorized yet';
  $('position').textContent = `${current + 1} / ${photos.length}`;
  $('image-counter').textContent = `${current + 1} of ${photos.length}`;
  $('previous').disabled = current === 0;
  $('next').disabled = current === photos.length - 1;
  const tags = $('focus-tags');
  tags.replaceChildren();
  state.categories.forEach((category) => tags.append(tagButton(category, photo)));
  if (!state.categories.length) {
    const hint = document.createElement('p');
    hint.className = 'no-tags';
    hint.textContent = 'Create a category on the left to start tagging.';
    tags.append(hint);
  }
}

function renderGrid(photos = visiblePhotos()) {
  const grid = $('grid');
  const scroll = $('grid-view').scrollTop;
  grid.replaceChildren();
  photos.forEach((photo, index) => {
    const card = document.createElement('article');
    card.className = 'photo-card';
    const picture = document.createElement('button');
    picture.type = 'button';
    picture.className = 'card-picture';
    picture.title = `Open ${photo.name}`;
    picture.addEventListener('click', () => { current = index; setMode('focus'); rememberPosition(); });
    const image = document.createElement('img');
    image.src = photoUrl(photo);
    image.alt = photo.name;
    image.loading = 'lazy';
    picture.append(image);
    const info = document.createElement('div');
    info.className = 'card-info';
    const heading = document.createElement('div');
    heading.className = 'card-heading';
    const filename = document.createElement('span');
    filename.textContent = photo.name;
    filename.title = photo.name;
    const number = document.createElement('span');
    number.textContent = String(index + 1).padStart(2, '0');
    heading.append(filename, number);
    const tags = document.createElement('div');
    tags.className = 'card-tags';
    state.categories.forEach(category => tags.append(tagButton(category, photo, true)));
    if (!state.categories.length) {
      const hint = document.createElement('span');
      hint.className = 'no-tags';
      hint.textContent = 'Add a category to start tagging';
      tags.append(hint);
    }
    info.append(heading, tags);
    card.append(picture, info);
    grid.append(card);
  });
  $('grid-view').scrollTop = scroll;
}

function render() {
  const hasFolder = Boolean(state.folder);
  const photos = visiblePhotos();
  current = Math.max(0, Math.min(current, photos.length - 1));
  $('welcome').classList.toggle('hidden', hasFolder);
  $('content').classList.toggle('hidden', !hasFolder);
  $('folder-label').textContent = hasFolder ? state.folder.split('/').filter(Boolean).at(-1) || '/' : 'No folder open';
  $('folder-path').textContent = hasFolder ? state.folder : 'Open a local folder to begin.';
  if (hasFolder) $('folder-input').value = state.folder;
  $('collection-title').textContent = hasFolder ? $('folder-label').textContent : 'Photos';
  $('collection-subtitle').textContent = activeCategory
    ? `${photos.length} of ${state.photos.length} photos · ${activeCategory}`
    : `${state.photos.length} ${state.photos.length === 1 ? 'photo' : 'photos'} · ${state.categories.length} ${state.categories.length === 1 ? 'category' : 'categories'}`;
  renderCategories();
  $('add-input').disabled = !hasFolder;
  $('import-button').disabled = !hasFolder;
  $('empty-photos').classList.toggle('hidden', !hasFolder || photos.length !== 0);
  $('empty-title').textContent = activeCategory ? `No photos in ${activeCategory}` : 'No photos here yet';
  $('empty-description').textContent = activeCategory
    ? 'Choose another category or All photos to see the rest of your collection.'
    : 'Add JPG, PNG, WEBP, GIF, BMP or AVIF images to this folder, then open it again.';
  $('focus-view').classList.toggle('hidden', !hasFolder || !photos.length || mode !== 'focus');
  $('grid-view').classList.toggle('hidden', !hasFolder || !photos.length || mode !== 'grid');
  $('focus-mode').classList.toggle('active', mode === 'focus');
  $('grid-mode').classList.toggle('active', mode === 'grid');
  $('position').textContent = photos.length ? `${current + 1} / ${photos.length}` : '';
  if (photos.length) {
    if (mode === 'focus') renderFocus(photos);
    else renderGrid(photos);
  }
}

function rememberPosition() {
  if (state.folder) localStorage.setItem(positionKey(), current);
}

function setFilter(category) {
  if (category === activeCategory) return;
  const previousPhoto = visiblePhotos()[current];
  activeCategory = category;
  localStorage.setItem('photo-sorter-filter:' + state.folder, category || '');
  const index = visiblePhotos().findIndex(photo => photo.name === previousPhoto?.name);
  current = index < 0 ? 0 : index;
  rememberPosition();
  $('grid-view').scrollTop = 0;
  render();
}

function move(delta) {
  const photos = visiblePhotos();
  if (!photos.length) return;
  current = Math.max(0, Math.min(photos.length - 1, current + delta));
  rememberPosition();
  renderFocus(photos);
}

function setMode(next) {
  mode = next;
  localStorage.setItem('photo-sorter-mode', mode);
  render();
}

$('folder-form').addEventListener('submit', (event) => {
  event.preventDefault();
  change('/api/folder', { path: $('folder-input').value });
});
$('add-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const name = $('add-input').value.trim();
  if (!name) return;
  change('/api/categories/add', { name }, `Added ${name}`).then((ok) => { if (ok) $('add-input').value = ''; });
});
$('import-button').addEventListener('click', () => $('import-input').click());
$('import-input').addEventListener('change', async (event) => {
  const files = await Promise.all(Array.from(event.target.files).map(async file => ({ name: file.name, content: await file.text() })));
  event.target.value = '';
  if (files.length) change('/api/import', { files }, `Imported ${files.length} ${files.length === 1 ? 'category file' : 'category files'}`);
});
$('previous').addEventListener('click', () => move(-1));
$('next').addEventListener('click', () => move(1));
$('focus-mode').addEventListener('click', () => setMode('focus'));
$('grid-mode').addEventListener('click', () => setMode('grid'));
$('fullscreen').addEventListener('click', async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await $('app').requestFullscreen();
  } catch { notify('Fullscreen is not available in this browser.', true); }
});
document.addEventListener('keydown', (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey || ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
  if (mode === 'focus' && event.key === 'ArrowLeft') { event.preventDefault(); move(-1); }
  if (mode === 'focus' && event.key === 'ArrowRight') { event.preventDefault(); move(1); }
  if (mode === 'focus' && /^[1-9]$/.test(event.key) && visiblePhotos().length) {
    const category = state.categories[Number(event.key) - 1];
    if (category) change('/api/toggle', { category, filename: visiblePhotos()[current].name });
  }
});

(async () => {
  try {
    state = await request('/api/state');
    const previousFolder = localStorage.getItem('photo-sorter-folder');
    if (!state.folder && previousFolder) {
      try { state = await request('/api/folder', { path: previousFolder }); }
      catch { $('folder-input').value = previousFolder; }
    }
    if (state.folder) {
      activeCategory = localStorage.getItem('photo-sorter-filter:' + state.folder);
      if (!state.categories.includes(activeCategory)) activeCategory = null;
      current = Math.max(0, Math.min(visiblePhotos().length - 1, Number(localStorage.getItem(positionKey())) || 0));
    }
    render();
  } catch (error) { notify(error.message, true); }
})();
