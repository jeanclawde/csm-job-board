const STAR_KEY = 'csm-job-board:starred-job-ids:v1';

function loadStarredIds() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STAR_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    console.warn('Could not read starred jobs from localStorage. Resetting stars.', error);
    try { localStorage.removeItem(STAR_KEY); } catch (_) {}
    return [];
  }
}

const state = {
  jobs: [],
  starred: new Set(loadStarredIds()),
  starredOnly: false,
};

const $ = (id) => document.getElementById(id);
const els = {
  search: $('searchInput'), region: $('regionFilter'), provider: $('providerFilter'),
  department: $('departmentFilter'), company: $('companyFilter'), starredOnly: $('starredOnly'),
  clear: $('clearFilters'),
  list: $('jobList'), template: $('jobCardTemplate'), empty: $('emptyState'),
  filterPanel: $('filterPanel'), toolbar: document.querySelector('.toolbar'),
};

function uniq(values) { return [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b)); }
function addOptions(select, values) {
  for (const value of values) {
    const option = document.createElement('option'); option.value = value; option.textContent = value; select.append(option);
  }
}
function saveStars() {
  try {
    localStorage.setItem(STAR_KEY, JSON.stringify([...state.starred]));
  } catch (error) {
    console.warn('Could not save starred jobs to localStorage.', error);
  }
}
function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}
function matches(job) {
  const q = els.search.value.trim().toLowerCase();
  const haystack = [job.title, job.company, job.location, job.department, job.provider, job.source_key, job.short_description].join(' ').toLowerCase();
  return (!q || haystack.includes(q))
    && (!els.region.value || job.region_tags.includes(els.region.value))
    && (!els.provider.value || job.provider === els.provider.value)
    && (!els.department.value || job.department === els.department.value)
    && (!els.company.value || job.company === els.company.value)
    && (!state.starredOnly || state.starred.has(job.id));
}
function render() {
  const jobs = state.jobs.filter(matches);
  els.list.replaceChildren();
  els.empty.hidden = jobs.length > 0;
  for (const job of jobs) {
    const node = els.template.content.firstElementChild.cloneNode(true);
    const star = node.querySelector('.star');
    const isStarred = state.starred.has(job.id);
    star.textContent = isStarred ? '★' : '☆';
    star.classList.toggle('active', isStarred);
    star.setAttribute('aria-label', `${isStarred ? 'Unstar' : 'Star'} ${job.title}`);
    star.addEventListener('click', () => {
      state.starred.has(job.id) ? state.starred.delete(job.id) : state.starred.add(job.id);
      saveStars(); render();
    });
    node.querySelector('.company').textContent = job.company;
    node.querySelector('.updated').textContent = formatDate(job.updated_at);
    node.querySelector('h2').textContent = job.title;
    node.querySelector('.meta').textContent = `${job.location} · ${job.employment_type}`;
    const description = node.querySelector('.description');
    description.textContent = job.short_description || 'Description coming soon.';
    description.hidden = !job.short_description;
    const chips = node.querySelector('.chips');
    for (const value of [job.department, job.provider, ...job.region_tags].filter(Boolean)) {
      const chip = document.createElement('span'); chip.className = 'chip'; chip.textContent = value; chips.append(chip);
    }
    const link = node.querySelector('.open'); link.href = job.job_url; link.textContent = 'Open offer ↗';
    els.list.append(node);
  }
}
function openFilters() {
  els.filterPanel.open = true;
}

function closeFiltersIfOutside(event) {
  if (!els.toolbar.contains(event.target)) {
    els.filterPanel.open = false;
  }
}

function wireEvents() {
  [els.search, els.region, els.provider, els.department, els.company].forEach(el => el.addEventListener('input', render));
  els.search.addEventListener('focus', openFilters);
  els.search.addEventListener('click', openFilters);
  document.addEventListener('pointerdown', closeFiltersIfOutside);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') els.filterPanel.open = false;
  });
  els.starredOnly.addEventListener('click', () => {
    state.starredOnly = !state.starredOnly;
    els.starredOnly.setAttribute('aria-pressed', String(state.starredOnly));
    render();
  });
  els.clear.addEventListener('click', () => {
    els.search.value = els.region.value = els.provider.value = els.department.value = els.company.value = '';
    state.starredOnly = false; els.starredOnly.setAttribute('aria-pressed', 'false'); render();
    els.search.focus();
  });
}
async function init() {
  const response = await fetch('data/jobs.json');
  const data = await response.json();
  state.jobs = data.jobs;
  addOptions(els.region, uniq(state.jobs.flatMap(j => j.region_tags)));
  addOptions(els.provider, uniq(state.jobs.map(j => j.provider)));
  addOptions(els.department, uniq(state.jobs.map(j => j.department)));
  addOptions(els.company, uniq(state.jobs.map(j => j.company)));
  wireEvents(); render();
}
init().catch(err => {
  console.error(err);
  els.list.innerHTML = '<p class="empty">Could not load jobs data.</p>';
});
