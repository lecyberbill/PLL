import { loadMonaco, detectLanguage } from './editor-setup.js';
import { set_virtual_file, get_virtual_file } from './pkg/pll_wasm.js';

const API_BASE = '';
let monaco, editor;
let filesList = [];
let openFiles = [];
let activeFile = null;
let currentProjectId = null;
let gcaSessionId = null;
let gcaGeneration = 0;
let agenticConversationHistory = [];

const DEFAULT_FILES = {
    'main.py': 'def hello():\n    print("Hello, PLL!")\n\nhello()',
    'helpers.pll': 'fn greet(name: str) -> str:\n    return str_concat("Hello, ", name)\n\nrender greet("PLL")',
};

const elTerminalLog = document.getElementById('terminal-log');
const elVfsList = document.getElementById('vfs-files-list');
const elProjectSelect = document.getElementById('project-select');
const elBtnNewProject = document.getElementById('btn-new-project');
const elBtnSaveProject = document.getElementById('btn-save-project');
const elBtnDeleteProject = document.getElementById('btn-delete-project');
const elBtnAddFile = document.getElementById('btn-add-file');
const elModalFilePath = document.getElementById('modal-file-path');
const elModalFileContent = document.getElementById('modal-file-content');
const elVfsModal = document.getElementById('vfs-modal');
const elModalCancel = document.getElementById('modal-cancel');
const elModalSave = document.getElementById('modal-save');
const elProjectModal = document.getElementById('project-modal');
const elProjectModalTitle = document.getElementById('project-modal-title');
const elModalProjectName = document.getElementById('modal-project-name');
const elModalProjectDesc = document.getElementById('modal-project-desc');
const elModalProjectPath = document.getElementById('modal-project-path');
const elProjectModalCancel = document.getElementById('project-modal-cancel');
const elProjectModalSave = document.getElementById('project-modal-save');
const elEditorContainer = document.getElementById('monaco-editor');
const elEditorTabsBar = document.getElementById('editor-tabs-bar');
const elLangBadge = document.getElementById('editor-lang-badge');
const elAgenticInput = document.getElementById('agentic-input');
const elAgenticSend = document.getElementById('btn-agentic-send');
const elAgenticClear = document.getElementById('btn-agentic-clear');
const elAgenticConversation = document.getElementById('agentic-conversation');
const elAgenticBackend = document.getElementById('agentic-backend');
const elGcaStatus = document.getElementById('gca-status');
const elGcaVault = document.getElementById('gca-vault');
const elPackagesList = document.getElementById('packages-list');
const elBtnRefreshPackages = document.getElementById('btn-refresh-packages');
const elGitBranch = document.getElementById('git-branch');
const elGitChanges = document.getElementById('git-changes');
const elGitRemote = document.getElementById('git-remote');

async function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`API ${resp.status}: ${text}`);
    }
    if (resp.status === 204) return null;
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) return resp.json();
    return resp.text();
}

function getEditorContent() { return editor ? editor.getValue() : ''; }
function setEditorContent(value) { if (editor) editor.setValue(value || ''); }
function setEditorLanguage(lang) {
    if (editor) { monaco.editor.setModelLanguage(editor.getModel(), lang || 'plaintext'); }
    if (elLangBadge) elLangBadge.textContent = lang || 'plaintext';
}

function clearEditor() {
    setEditorContent('');
    activeFile = null;
    setEditorLanguage('plaintext');
}

function clearDefaults() {
    filesList = [];
    clearEditor();
}

function closeFile(path) {
    const target = path || activeFile;
    if (!target) return;
    set_virtual_file(target, getEditorContent());
    const tabIdx = openFiles.indexOf(target);
    if (tabIdx === -1) return;
    openFiles.splice(tabIdx, 1);
    if (target === activeFile) {
        if (openFiles.length > 0) {
            const next = openFiles[Math.min(tabIdx, openFiles.length - 1)];
            activeFile = next;
            setEditorContent(get_virtual_file(next));
            setEditorLanguage(detectLanguage(next));
        } else {
            clearEditor();
        }
    }
    renderTabs();
    renderVfsList();
}

function logToTerminal(msg, className = '') {
    const div = document.createElement('div');
    div.className = className;
    div.textContent = msg;
    elTerminalLog.appendChild(div);
    elTerminalLog.scrollTop = elTerminalLog.scrollHeight;
}

function renderTabs() {
    elEditorTabsBar.innerHTML = '';
    if (openFiles.length === 0) {
        const empty = document.createElement('span');
        empty.className = 'sys-msg';
        empty.style.cssText = 'padding:4px 8px;font-size:12px;color:var(--text-muted)';
        empty.textContent = activeFile || '(aucun)';
        elEditorTabsBar.appendChild(empty);
        return;
    }
    const container = elEditorTabsBar;
    for (const path of openFiles) {
        const tab = document.createElement('div');
        tab.className = `editor-tab-item ${path === activeFile ? 'active' : ''}`;
        tab.title = path;
        const name = document.createElement('span');
        name.textContent = path.split('/').pop() || path;
        name.style.cssText = 'overflow:hidden;text-overflow:ellipsis;max-width:120px';
        tab.appendChild(name);
        const close = document.createElement('button');
        close.className = 'tab-close';
        close.textContent = '✕';
        close.onclick = (e) => { e.stopPropagation(); closeFile(path); };
        tab.appendChild(close);
        tab.onclick = () => loadFileToEditor(path);
        container.appendChild(tab);
    }
}

function renderVfsList() {
    elVfsList.innerHTML = '';
    const tree = {};
    for (const fp of filesList) {
        const parts = fp.replace(/\\/g, '/').split('/');
        let cur = tree;
        for (let i = 0; i < parts.length; i++) {
            const p = parts[i];
            if (i === parts.length - 1) {
                cur[p] = { type: 'file', path: fp };
            } else {
                if (!cur[p]) cur[p] = { type: 'dir', children: {} };
                cur = cur[p].children;
            }
        }
    }
    renderTree(elVfsList, tree, 0);
}

function renderTree(container, tree, depth) {
    const keys = Object.keys(tree).sort((a, b) => {
        const ta = tree[a].type, tb = tree[b].type;
        if (ta !== tb) return ta === 'dir' ? -1 : 1;
        return a.localeCompare(b);
    });
    for (const key of keys) {
        const node = tree[key];
        const item = document.createElement('div');
        item.className = 'vfs-item';
        item.style.paddingLeft = (12 + depth * 16) + 'px';
        if (node.type === 'dir') {
            const toggle = document.createElement('span');
            toggle.className = 'vfs-toggle';
            toggle.textContent = '▸';
            toggle.style.cursor = 'pointer';
            toggle.style.marginRight = '4px';
            item.appendChild(toggle);
            const name = document.createElement('span');
            name.className = 'vfs-item-name';
            name.textContent = key;
            item.appendChild(name);
            const childContainer = document.createElement('div');
            childContainer.style.display = 'none';
            renderTree(childContainer, node.children, depth + 1);
            toggle.onclick = () => {
                const expanded = childContainer.style.display !== 'none';
                childContainer.style.display = expanded ? 'none' : '';
                toggle.textContent = expanded ? '▸' : '▾';
            };
            container.appendChild(item);
            container.appendChild(childContainer);
        } else {
            const name = document.createElement('span');
            name.className = `vfs-item-name ${node.path === activeFile ? 'active' : ''}`;
            name.textContent = key;
            name.onclick = () => loadFileToEditor(node.path);
            const actions = document.createElement('div');
            actions.className = 'vfs-actions';
            const btnRename = document.createElement('button');
            btnRename.className = 'btn btn-sm btn-secondary';
            btnRename.textContent = '✎';
            btnRename.title = 'Renommer';
            btnRename.onclick = () => renameFile(node.path);
            const btnDelete = document.createElement('button');
            btnDelete.className = 'btn btn-sm btn-danger';
            btnDelete.textContent = '✕';
            btnDelete.title = 'Supprimer';
            btnDelete.onclick = () => deleteFile(node.path);
            actions.appendChild(btnRename);
            actions.appendChild(btnDelete);
            item.appendChild(name);
            item.appendChild(actions);
            container.appendChild(item);
        }
    }
}

async function loadFileToEditor(path) {
    if (!path) return;
    if (activeFile) set_virtual_file(activeFile, getEditorContent());
    if (!openFiles.includes(path)) openFiles.push(path);
    activeFile = path;
    let content = get_virtual_file(path);
    if (content === null || content === undefined) {
        if (currentProjectId) {
            try {
                const detail = await api(`/api/projects/${currentProjectId}/files/${encodeURIComponent(path)}`);
                content = detail.content || '';
                set_virtual_file(path, content);
            } catch { content = ''; }
        } else { content = ''; }
    }
    if (content !== null && content !== undefined) setEditorContent(content);
    setEditorLanguage(detectLanguage(path));
    renderTabs();
    renderVfsList();
}

async function renameFile(path) {
    const newName = prompt('Nouveau nom :', path);
    if (!newName || newName === path) return;
    const content = get_virtual_file(path);
    set_virtual_file(newName, content);
    const idx = filesList.indexOf(path);
    filesList.splice(idx, 1, newName);
    const tabIdx = openFiles.indexOf(path);
    if (tabIdx !== -1) openFiles.splice(tabIdx, 1, newName);
    if (activeFile === path) {
        activeFile = newName;
        setEditorContent(content);
        setEditorLanguage(detectLanguage(newName));
    }
    renderTabs();
    renderVfsList();
    if (currentProjectId) {
        try {
            await api(`/api/projects/${currentProjectId}/files/rename?old_path=${encodeURIComponent(path)}&new_path=${encodeURIComponent(newName)}`, { method: 'PUT' });
        } catch (e) {
            logToTerminal(`Erreur renommage: ${e.message}`, 'error-msg');
        }
    }
    logToTerminal(`Renommé: ${path} → ${newName}`, 'sys-msg');
}

async function deleteFileFromServer(path) {
    if (!currentProjectId) return;
    await api(`/api/projects/${currentProjectId}/files/${encodeURIComponent(path)}`, { method: 'DELETE' });
}

function deleteFile(path) {
    if (!confirm(`Supprimer "${path}" ?`)) return;
    const idx = filesList.indexOf(path);
    if (idx === -1) return;
    filesList.splice(idx, 1);
    if (activeFile === path) closeFile(path);
    else renderVfsList();
    deleteFileFromServer(path).catch(e => logToTerminal(`Erreur: ${e.message}`, 'error-msg'));
    logToTerminal(`Supprimé: ${path}`, 'sys-msg');
}

async function loadProjects() {
    try {
        const projects = await api('/api/projects');
        elProjectSelect.innerHTML = '<option value="">-- Projet local --</option>';
        projects.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            if (p.id === currentProjectId) opt.selected = true;
            elProjectSelect.appendChild(opt);
        });
    } catch (e) { console.warn('Server not running:', e.message); }
}

async function saveProjectToServer() {
    if (!currentProjectId) {
        const name = prompt('Nom du projet :', 'MonProjet');
        if (!name) return;
        const project = await api('/api/projects', {
            method: 'POST',
            body: JSON.stringify({ name, description: 'Créé depuis le playground' }),
        });
        currentProjectId = project.id;
    }
    if (activeFile) {
        set_virtual_file(activeFile, getEditorContent());
        if (!filesList.includes(activeFile)) filesList.push(activeFile);
    }
    for (const p of openFiles) {
        const c = get_virtual_file(p);
        if (c !== null && c !== undefined && !filesList.includes(p)) filesList.push(p);
    }
    for (const path of filesList) {
        const content = get_virtual_file(path);
        if (content !== null && content !== undefined) {
            await api(`/api/projects/${currentProjectId}/files`, {
                method: 'POST', body: JSON.stringify({ path, content }),
            });
        }
    }
    await loadProjects();
    logToTerminal(`Projet sauvegardé (ID: ${currentProjectId}).`, 'sys-msg');
}

async function loadProjectFromServer(projectId) {
    currentProjectId = projectId;
    clearDefaults();
    const tree = await api(`/api/projects/${projectId}/files`);
    filesList = [];
    async function walk(nodes) {
        for (const node of nodes) {
            if (node.type === 'dir' && node.children) await walk(node.children);
            else if (node.path) {
                if (node.content !== undefined) set_virtual_file(node.path, node.content);
                filesList.push(node.path);
            }
        }
    }
    await walk(tree);
    openFiles = [...filesList];
    if (filesList.length > 0) {
        activeFile = filesList[0];
        setEditorContent(get_virtual_file(activeFile));
        setEditorLanguage(detectLanguage(activeFile));
    }
    renderTabs();
    renderVfsList();
    logToTerminal(`Projet chargé (${filesList.length} fichiers).`, 'sys-msg');
    await loadProjects();
    refreshGitStatus();
}

async function refreshGitStatus() {
    if (!currentProjectId) {
        elGitBranch.textContent = '';
        elGitChanges.textContent = '';
        elGitRemote.textContent = '';
        return;
    }
    try {
        const st = await api(`/api/git/${currentProjectId}/status`);
        if (!st || !st.is_repo) {
            elGitBranch.textContent = '';
            elGitChanges.textContent = '';
            elGitRemote.textContent = '';
            return;
        }
        elGitBranch.textContent = `⎇ ${st.branch || 'main'}`;
        const changes = [];
        if (st.staged.length) changes.push(`${st.staged.length} staged`);
        if (st.modified.length) changes.push(`${st.modified.length} modified`);
        if (st.untracked.length) changes.push(`${st.untracked.length} untracked`);
        if (st.deleted.length) changes.push(`${st.deleted.length} deleted`);
        elGitChanges.textContent = changes.length ? `• ${changes.join(', ')}` : '';
        elGitChanges.className = changes.length ? 'changed' : '';
        if (st.ahead || st.behind) {
            const parts = [];
            if (st.ahead) parts.push(`↑${st.ahead}`);
            if (st.behind) parts.push(`↓${st.behind}`);
            elGitRemote.textContent = `• ${parts.join(' ')}`;
            elGitRemote.className = st.behind ? 'behind' : st.ahead ? 'ahead' : '';
        } else {
            elGitRemote.textContent = '';
            elGitRemote.className = '';
        }
    } catch {
        elGitBranch.textContent = '';
        elGitChanges.textContent = '';
        elGitRemote.textContent = '';
    }
}

function addAgenticMessage(role, content) {
    const div = document.createElement('div');
    div.className = `agentic-message ${role}`;
    const label = document.createElement('span');
    label.className = 'msg-label';
    label.textContent = role === 'user' ? 'VOUS' : role === 'assistant' ? 'AGENT 🤖' : 'SYSTÈME';
    div.appendChild(label);
    const text = document.createElement('div');
    text.innerHTML = content.replace(/\n/g, '<br>')
        .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    div.appendChild(text);
    elAgenticConversation.appendChild(div);
    elAgenticConversation.scrollTop = elAgenticConversation.scrollHeight;
}

async function ensureProjectForAgentic() {
    if (currentProjectId) return true;
    try {
        const project = await api('/api/projects', {
            method: 'POST',
            body: JSON.stringify({ name: 'Agentic Project', description: 'Créé par l\'agent' }),
        });
        currentProjectId = project.id;
        await loadProjects();
        if (activeFile) {
            set_virtual_file(activeFile, getEditorContent());
            if (!filesList.includes(activeFile)) filesList.push(activeFile);
        }
        for (const p of openFiles) {
            const c = get_virtual_file(p);
            if (c !== null && c !== undefined && !filesList.includes(p)) filesList.push(p);
        }
        for (const path of filesList) {
            const content = get_virtual_file(path);
            if (content !== null && content !== undefined) {
                await api(`/api/projects/${currentProjectId}/files`, {
                    method: 'POST', body: JSON.stringify({ path, content }),
                });
            }
        }
        addAgenticMessage('system', `Projet "${project.name}" (ID: ${project.id}).`);
        return true;
    } catch (e) {
        addAgenticMessage('system', `Erreur: ${e.message}`);
        return false;
    }
}

async function sendAgenticMessage() {
    const msg = elAgenticInput.value.trim();
    if (!msg) return;
    elAgenticInput.value = '';
    addAgenticMessage('user', msg);
    if (!await ensureProjectForAgentic()) return;
    await saveProjectToServer();
    const backend = elAgenticBackend.value;
    addAgenticMessage('system', `Agent réfléchit (${backend === 'auto' ? 'auto' : backend})...`);
    try {
        const result = await api('/api/agentic/go', {
            method: 'POST',
            body: JSON.stringify({
                project_id: currentProjectId,
                message: msg,
                backend: backend === 'auto' ? '' : backend,
            }),
        });
        let stepsHtml = '';
        if (result.steps && result.steps.length > 0) {
            const icons = { read_file: '📖', write_file: '✏️', edit_artifact: '✏️', glob_files: '🔍', grep_files: '🔍', list_dir: '📂', run_command: '⚡', search_vault: '💾', git_status: '⎇', git_commit: '📝', git_push: '⬆️', git_init: '🔧', git_remote: '🔗', exec_pll: '⚙️', web_fetch: '🌐', web_search: '🔎', edit_file: '✏️', exec_python: '🐍', exec_shell: '💻', tree: '🌳', diff_files: '📊', search_code: '🔍', count_tokens: '🔢', read_lines: '📄', zip_project: '📦', final_answer: '✅' };
            stepsHtml = result.steps.map(s => {
                const icon = icons[s.tool] || '➡️';
                let label = s.tool || s.subtask || `Step ${s.step}`;
                let detail = '';
                if (s.args) {
                    if (s.args.path) detail = s.args.path;
                    else if (s.args.pattern) detail = s.args.pattern;
                    else if (s.args.code) detail = (s.args.code + '').slice(0, 50);
                    else if (s.args.command) detail = s.args.command.slice(0, 50);
                    else if (s.args.url) detail = s.args.url;
                    else if (s.args.text) detail = s.args.text.slice(0, 60);
                }
                let preview = '';
                if (s.result && typeof s.result === 'string') {
                    const clean = s.result.replace(/```[\s\S]*?```/g, '[code]').slice(0, 80);
                    if (clean) preview = ` → ${clean}`;
                }
                const d = detail ? ` \`${detail}\`` : '';
                return `${icon} **${label}**${d}${preview}`;
            }).join('\n');
        }
        if (result.question) {
            addAgenticMessage('assistant', `**❓ Question :** ${result.question}\n\n_Réponds dans le chat._`);
        } else if (result.explanation) {
            addAgenticMessage('assistant', stepsHtml ? `${stepsHtml}\n\n${result.explanation}` : result.explanation);
        } else if (result.code && result.file_path) {
            set_virtual_file(result.file_path, result.code);
            if (!filesList.includes(result.file_path)) filesList.push(result.file_path);
            renderVfsList();
            const lang = detectLanguage(result.file_path);
            const labels = { create: '**Code créé**', edit: '**Code modifié**', react: '**ReAct**', orchestrate: '**Multi-agent**' };
            let response = `${labels[result.mode] || '**Terminé**'} → \`${result.file_path}\` (${lang})\n`;
            if (stepsHtml) response = `${stepsHtml}\n\n${response}`;
            response += `\n\`\`\`${lang}\n${result.code}\n\`\`\``;
            addAgenticMessage('assistant', response);
            await loadFileToEditor(result.file_path);
        } else if (result.answer) {
            addAgenticMessage('assistant', stepsHtml ? `${stepsHtml}\n\n${result.answer}` : result.answer);
        } else {
            addAgenticMessage('assistant', '✅ Terminé.');
        }
    } catch (e) {
        addAgenticMessage('system', `Erreur: ${e.message}`);
    }
}

async function main() {
    try {
        monaco = await loadMonaco();
        editor = monaco.editor.create(elEditorContainer, {
            value: '', language: 'python', theme: 'pll-dark',
            fontSize: 14, fontFamily: "'Fira Code', monospace",
            minimap: { enabled: false }, lineNumbers: 'on',
            automaticLayout: true, tabSize: 4, insertSpaces: true,
            bracketPairColorization: { enabled: true },
            renderLineHighlight: 'line', cursorBlinking: 'smooth',
        });
        editor.onDidChangeModelContent(() => {
            if (activeFile) set_virtual_file(activeFile, editor.getValue());
        });
        clearDefaults();
        for (const [path, content] of Object.entries(DEFAULT_FILES)) {
            set_virtual_file(path, content);
            filesList.push(path);
        }
        openFiles = ['main.py', 'helpers.pll'];
        activeFile = 'main.py';
        setEditorContent(DEFAULT_FILES['main.py']);
        setEditorLanguage(detectLanguage(activeFile));
        renderTabs();
        renderVfsList();
        logToTerminal('PLL WASM + Monaco Editor chargés.', 'sys-msg');
        await loadProjects();
        await refreshPackages();
        refreshGitStatus();
    } catch (e) {
        logToTerminal(`Erreur: ${e}`, 'error-msg');
    }
}

async function gcaRefreshStatus() {
    const pid = currentProjectId;
    if (!pid) return;
    try {
        const status = await api(`/api/gca/status/${pid}`);
        const p = status.current_primary, s = status.current_shadow;
        elGcaStatus.innerHTML = `<div class="gca-info">
            <p><strong>Générations:</strong> ${status.total_generations}</p>
            <p><strong>Primaire:</strong> ${p ? `#${p.id} (gen ${p.generation}, ${p.status})` : 'Aucun'}</p>
            <p><strong>Ombre:</strong> ${s ? `#${s.id} (gen ${s.generation}, ${s.status})` : 'Aucun'}</p>
            <p><strong>Vault:</strong> ${status.vault_entries_count} entrées</p></div>`;
        if (currentProjectId !== pid) return;
        const vault = await api(`/api/gca/vault/${pid}`);
        if (currentProjectId !== pid) return;
        elGcaVault.innerHTML = vault.length === 0
            ? '<div class="sys-msg">Vault vide.</div>'
            : vault.slice(-10).map(e =>
                `<div class="vault-entry"><strong>${e.key}</strong> <span class="sys-msg">(${new Date(e.created_at).toLocaleString()})</span><pre>${e.content.slice(0, 200)}</pre></div>`
            ).join('');
    } catch (e) { console.warn(e.message); }
}

async function refreshPackages() {
    try {
        const pkgs = await api('/api/packages');
        elPackagesList.innerHTML = pkgs.length === 0
            ? '<div class="sys-msg">Aucun paquet.</div>'
            : pkgs.map(p => `<div class="package-item"><strong>${p.name}</strong> v${p.version} <span class="sys-msg">par ${p.author || '?'}</span></div>`).join('');
    } catch {
        elPackagesList.innerHTML = '<div class="sys-msg">Serveur indisponible.</div>';
    }
}

// Event listeners
elProjectSelect.addEventListener('change', async (e) => {
    if (e.target.value) {
        try {
            await loadProjectFromServer(parseInt(e.target.value));
            elBtnDeleteProject.style.display = '';
        } catch (err2) { logToTerminal(`Erreur: ${err2.message}`, 'error-msg'); }
    } else {
        currentProjectId = null;
        elBtnDeleteProject.style.display = 'none';
        clearDefaults();
        for (const [path, content] of Object.entries(DEFAULT_FILES)) {
            set_virtual_file(path, content);
            filesList.push(path);
        }
        openFiles = ['main.py', 'helpers.pll'];
        activeFile = 'main.py';
        setEditorContent(DEFAULT_FILES['main.py']);
        setEditorLanguage(detectLanguage(activeFile));
        renderTabs();
        renderVfsList();
        logToTerminal('Mode local', 'sys-msg');
    }
});

elBtnSaveProject.addEventListener('click', async () => {
    try { await saveProjectToServer(); } catch (e) { logToTerminal(`Erreur: ${e.message}`, 'error-msg'); }
});

elBtnDeleteProject.addEventListener('click', async () => {
    if (!currentProjectId) return;
    const name = elProjectSelect.options[elProjectSelect.selectedIndex]?.text || 'ce projet';
    if (!confirm(`Supprimer "${name}" ? Les fichiers sont conservés.`)) return;
    try {
        await api(`/api/projects/${currentProjectId}?keep_files=true`, { method: 'DELETE' });
        logToTerminal(`Projet supprimé.`, 'sys-msg');
        currentProjectId = null;
        elBtnDeleteProject.style.display = 'none';
        clearDefaults();
        for (const [path, content] of Object.entries(DEFAULT_FILES)) {
            set_virtual_file(path, content);
            filesList.push(path);
        }
        openFiles = ['main.py', 'helpers.pll'];
        activeFile = 'main.py';
        setEditorContent(DEFAULT_FILES['main.py']);
        setEditorLanguage(detectLanguage(activeFile));
        renderTabs();
        renderVfsList();
        await loadProjects();
        refreshGitStatus();
    } catch (e) { logToTerminal(`Erreur: ${e.message}`, 'error-msg'); }
});

elBtnNewProject.addEventListener('click', () => {
    elProjectModalTitle.textContent = 'Nouveau Projet';
    elModalProjectName.value = '';
    elModalProjectDesc.value = '';
    elModalProjectPath.value = '';
    elProjectModal.classList.add('open');
});

elProjectModalCancel.addEventListener('click', () => elProjectModal.classList.remove('open'));
elProjectModalSave.addEventListener('click', async () => {
    const name = elModalProjectName.value.trim();
    if (!name) return;
    try {
        const pathVal = elModalProjectPath.value.trim();
        const project = await api('/api/projects', {
            method: 'POST',
            body: JSON.stringify({ name, description: elModalProjectDesc.value, disk_path: pathVal }),
        });
        logToTerminal(`Projet "${name}" créé.`, 'sys-msg');
        currentProjectId = project.id;
        elProjectModal.classList.remove('open');
        elBtnDeleteProject.style.display = '';
        clearDefaults();
        await saveProjectToServer();
        await loadProjectFromServer(currentProjectId);
    } catch (e) { logToTerminal(`Erreur: ${e.message}`, 'error-msg'); }
});

elBtnAddFile.addEventListener('click', () => elVfsModal.classList.add('open'));
elModalCancel.addEventListener('click', () => elVfsModal.classList.remove('open'));
elModalSave.addEventListener('click', async () => {
    const path = elModalFilePath.value.trim();
    const content = elModalFileContent.value;
    if (!path) return;
    set_virtual_file(path, content);
    if (!filesList.includes(path)) filesList.push(path);
    if (!openFiles.includes(path)) openFiles.push(path);
    if (openFiles.length === 1) {
        activeFile = path;
        setEditorContent(content);
        setEditorLanguage(detectLanguage(path));
    }
    renderTabs();
    renderVfsList();
    elVfsModal.classList.remove('open');
    elModalFilePath.value = '';
    elModalFileContent.value = '';
    if (currentProjectId) {
        try {
            await api(`/api/projects/${currentProjectId}/files`, {
                method: 'POST', body: JSON.stringify({ path, content }),
            });
        } catch (e) { logToTerminal(`Erreur: ${e.message}`, 'sys-msg'); }
    }
});

elAgenticSend.addEventListener('click', sendAgenticMessage);
elAgenticInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgenticMessage(); }
});
elAgenticClear.addEventListener('click', () => {
    elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
    agenticConversationHistory = [];
});

elBtnRefreshPackages.addEventListener('click', refreshPackages);

setInterval(() => { if (currentProjectId) gcaRefreshStatus(); }, 10000);
setInterval(refreshGitStatus, 15000);

main();
