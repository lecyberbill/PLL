import { loadMonaco, detectLanguage } from './editor-setup.js';
import { set_virtual_file, get_virtual_file } from './pkg/pll_wasm.js';

const API_BASE = '';
let monaco, editor;
let monacoDiffEditor = null;
let gitAheadFiles = [];
let filesList = [];
let openFiles = ['logic_flow.agent'];
let activeFile = 'logic_flow.agent';
let currentProjectId = null;
let gcaSessionId = null;
let gcaGeneration = 0;
let agenticConversationHistory = [];
let gitFileStatus = {};  // { "path": "M"|"A"|"?"|"D" } for VFS badges

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
const elResizeHandle = document.getElementById('resize-handle');
const elResizeHandleLeft = document.getElementById('resize-handle-left');
const elAgenticInput = document.getElementById('agentic-input');
const elAgenticSend = document.getElementById('btn-agentic-send');
const elAgenticClear = document.getElementById('btn-agentic-clear');
const elAgenticConversation = document.getElementById('agentic-conversation');
const elBtnSettings = document.getElementById('btn-settings');
const elSettingsModal = document.getElementById('settings-modal');
const elBtnSettingsClose = document.getElementById('btn-settings-close');
const elSettingsBackend = document.getElementById('settings-backend');
const elSettingsSessionSelect = document.getElementById('settings-session-select');
const elBtnNewSession = document.getElementById('btn-new-session');
const elAgenticSessionSelect = document.getElementById('agentic-session-select');
const elBtnAgenticNewSession = document.getElementById('btn-agentic-new-session');
const elSettingsEnableGca = document.getElementById('settings-enable-gca');
const elTabBtnGca = document.getElementById('tab-btn-gca');
const elBtnRunCode = document.getElementById('btn-run-code');
const elBtnSaveFile = document.getElementById('btn-save-file');
const elGcaStatus = document.getElementById('gca-status');
const elGcaVault = document.getElementById('gca-vault');
const elPackagesList = document.getElementById('packages-list');
const elBtnRefreshPackages = document.getElementById('btn-refresh-packages');
const elGitBranch = document.getElementById('git-branch');
const elGitChanges = document.getElementById('git-changes');
const elGitRemote = document.getElementById('git-remote');
const elGitDebug = document.getElementById('git-debug');
const elConvList = document.getElementById('conv-list');
const elBtnRefreshConv = document.getElementById('btn-refresh-conv');
const elTerminalInput = document.getElementById('terminal-input');

// Terminal command history
let termHistory = [];
let termHistIdx = -1;

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


if (elAgenticConversation) {
    elAgenticConversation.addEventListener('click', async (e) => {
        if (e.target.classList.contains('collab-btn-accept')) {
            const container = e.target.closest('.collab-diff-container');
            if (!container) return;
            const sessionId = container.dataset.sessionId;
            e.target.disabled = true;
            try {
                await api(`/api/agentic/sessions/${sessionId}/accept`, { method: 'POST' });
                container.innerHTML = `<div class="sys-msg" style="color: var(--success); font-weight: bold; margin-top: 8px;">✅ Modifications validées et enregistrées.</div>`;
                if (currentProjectId) await loadProjectFromServer(currentProjectId);
            } catch (err) {
                alert("Erreur lors de la validation : " + err.message);
                e.target.disabled = false;
            }
        } else if (e.target.classList.contains('collab-btn-reject')) {
            const container = e.target.closest('.collab-diff-container');
            if (!container) return;
            const sessionId = container.dataset.sessionId;
            e.target.disabled = true;
            try {
                await api(`/api/agentic/sessions/${sessionId}/reject`, { method: 'POST' });
                container.innerHTML = `<div class="sys-msg" style="color: var(--error); font-weight: bold; margin-top: 8px;">❌ Modifications rejetées et fichiers restaurés.</div>`;
                if (currentProjectId) await loadProjectFromServer(currentProjectId);
            } catch (err) {
                alert("Erreur lors du rejet : " + err.message);
                e.target.disabled = false;
            }
        }
    });
}

function clearDefaults() {
    filesList = [];
    openFiles = [];
    activeFile = null;
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
    // Save expanded state before re-render
    const expanded = new Set();
    document.querySelectorAll('.vfs-toggle').forEach(el => {
        if (el.textContent === '▾') {
            const parent = el.closest('.vfs-item');
            if (parent) {
                const nameEl = parent.querySelector('.vfs-item-name');
                if (nameEl && nameEl.dataset.path) expanded.add(nameEl.dataset.path);
            }
        }
    });
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
    renderTree(elVfsList, tree, 0, expanded, '');
}

function renderTree(container, tree, depth, expanded = new Set(), parentPath = '') {
    const keys = Object.keys(tree).sort((a, b) => {
        const ta = tree[a].type, tb = tree[b].type;
        if (ta !== tb) return ta === 'dir' ? -1 : 1;
        return a.localeCompare(b);
    });
    for (const key of keys) {
        const node = tree[key];
        const currentPath = parentPath ? `${parentPath}/${key}` : key;
        const item = document.createElement('div');
        item.className = 'vfs-item';
        item.style.paddingLeft = (12 + depth * 16) + 'px';
        if (node.type === 'dir') {
            const toggle = document.createElement('span');
            toggle.className = 'vfs-toggle';
            const isExpanded = expanded.has(currentPath);
            toggle.textContent = isExpanded ? '▾' : '▸';
            toggle.style.cursor = 'pointer';
            toggle.style.marginRight = '4px';
            item.appendChild(toggle);
            const name = document.createElement('span');
            name.className = 'vfs-item-name';
            name.dataset.path = currentPath;
            name.textContent = `${isExpanded ? '📂' : '📁'} ${key}`;
            item.appendChild(name);
            const childContainer = document.createElement('div');
            childContainer.style.display = isExpanded ? '' : 'none';
            renderTree(childContainer, node.children, depth + 1, expanded, currentPath);
            toggle.onclick = () => {
                const nowExpanded = childContainer.style.display !== 'none';
                childContainer.style.display = nowExpanded ? 'none' : '';
                toggle.textContent = nowExpanded ? '▸' : '▾';
                name.textContent = `${nowExpanded ? '📁' : '📂'} ${key}`;
            };
            container.appendChild(item);
            container.appendChild(childContainer);
        } else {
            const name = document.createElement('span');
            name.className = `vfs-item-name ${node.path === activeFile ? 'active' : ''}`;
            name.dataset.path = node.path;
            name.onclick = () => loadFileToEditor(node.path);

            const badge = gitFileStatus[node.path];
            let badgeText = '';
            let statusClass = '';
            let tooltipText = '';
            let textColor = '';
            
            if (badge) {
                badgeText = badge;
                statusClass = badge === '?' ? 'untracked' : badge === 'D' ? 'deleted' : badge === 'M' ? 'modified' : 'staged';
                tooltipText = badge === '?' ? 'Non suivi — Nouveau fichier' : badge === 'D' ? 'Supprimé' : badge === 'M' ? 'Modifié — Modifications locales non indexées' : 'Indexé — Prêt à être commité';
                textColor = badge === '?' ? '#2dd4bf' : badge === 'D' ? '#f87171' : badge === 'M' ? '#eab308' : '#22c55e';
            } else if (gitAheadFiles.includes(node.path)) {
                badgeText = '↑';
                statusClass = 'ahead';
                tooltipText = 'Commité localement — En attente de push';
                textColor = '#60a5fa';
            } else if (currentProjectId) {
                badgeText = '✓';
                statusClass = 'synced';
                tooltipText = 'Synchronisé avec le dépôt';
                textColor = '#a5b4fc'; // Subtle violet/indigo
            }
            
            if (statusClass) {
                const badgeEl = document.createElement('span');
                badgeEl.className = `vfs-git-badge ${statusClass}`;
                badgeEl.textContent = badgeText;
                badgeEl.title = tooltipText;
                badgeEl.style.marginRight = '6px';
                name.appendChild(badgeEl);
            }

            const textNode = document.createElement('span');
            textNode.textContent = `📄 ${key}`;
            if (textColor) textNode.style.color = textColor;
            name.appendChild(textNode);
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
    if (path === 'logic_flow.agent') {
        const navOrch = document.getElementById('nav-item-orchestrator');
        if (navOrch && !navOrch.classList.contains('active')) {
            navOrch.click();
        }
        activeFile = path;
        renderTabs();
        return;
    }
    const navVfs = document.getElementById('nav-item-vfs');
    if (navVfs && !navVfs.classList.contains('active')) {
        navVfs.click();
    }
    if (activeFile && activeFile !== 'logic_flow.agent') set_virtual_file(activeFile, getEditorContent());
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
    // Update VFS active highlight without full re-render (preserves expanded dirs)
    document.querySelectorAll('.vfs-item-name.active').forEach(el => el.classList.remove('active'));
    const activeEl = document.querySelector(`.vfs-item-name[data-path="${CSS.escape(path)}"]`);
    if (activeEl) activeEl.classList.add('active');
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
        if (Array.isArray(projects)) {
            projects.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.name;
                if (p.id === currentProjectId) opt.selected = true;
                elProjectSelect.appendChild(opt);
            });
        } else {
            console.warn('api/projects did not return an array:', projects);
        }
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
        if (path === '.gitkeep') continue;
        const content = get_virtual_file(path);
        if (content !== null && content !== undefined) {
            await api(`/api/projects/${currentProjectId}/files`, {
                method: 'POST', body: JSON.stringify({ path, content }),
            });
        }
    }
    await loadProjects();
    logToTerminal(`Projet sauvegardé (ID: ${currentProjectId}).`, 'sys-msg');
    
    const buttons = [elBtnSaveFile, elBtnSaveProject];
    for (const btn of buttons) {
        if (btn) {
            const originalText = btn.innerHTML;
            btn.innerHTML = btn === elBtnSaveProject ? "✅ Sauvé !" : "✅ Enregistré !";
            const originalBg = btn.style.backgroundColor;
            const originalBc = btn.style.borderColor;
            btn.style.backgroundColor = "#2e7d32";
            btn.style.borderColor = "#2e7d32";
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.style.backgroundColor = originalBg;
                btn.style.borderColor = originalBc;
            }, 2000);
        }
    }
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
    openFiles = ['logic_flow.agent'];
    activeFile = 'logic_flow.agent';
    clearEditor();
    renderTabs();
    renderVfsList();
    logToTerminal(`Projet chargé (${filesList.length} fichiers).`, 'sys-msg');
    localStorage.setItem('pll-last-project', projectId.toString());
    elBtnDeleteProject.style.display = '';
    const navOrch = document.getElementById('nav-item-orchestrator');
    if (navOrch && !navOrch.classList.contains('active')) {
        navOrch.click();
    }
    await loadProjects();
    refreshGitStatus();
    loadConversations();
    await loadAgenticHistory(projectId);
}

async function loadSessions() {
    if (!currentProjectId) return;
    try {
        const sessions = await api(`/api/agentic/projects/${currentProjectId}/sessions`);
        elSettingsSessionSelect.innerHTML = '';
        if (elAgenticSessionSelect) elAgenticSessionSelect.innerHTML = '';
        
        const sidebarList = document.getElementById('sidebar-sessions-list');
        if (sidebarList) sidebarList.innerHTML = '';

        const activeId = elAgenticSessionSelect ? elAgenticSessionSelect.value : null;

        sessions.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = `Session #${s.id} (${s.status}) - ${new Date(s.created_at).toLocaleTimeString('fr-FR')}`;
            if (s.status === 'active') opt.selected = true;
            
            elSettingsSessionSelect.appendChild(opt.cloneNode(true));
            if (elAgenticSessionSelect) elAgenticSessionSelect.appendChild(opt);
            
            if (sidebarList) {
                const item = document.createElement('div');
                const isSelected = String(s.id) === String(activeId) || (s.status === 'active' && !activeId);
                item.className = `session-sidebar-item ${isSelected ? 'active' : ''}`;
                item.style.cssText = `padding: 8px; border-radius: var(--radius-sm); border: 1px solid var(--border-color); background: ${isSelected ? 'rgba(255,255,255,0.08)' : 'rgba(255,255,255,0.02)'}; cursor: pointer; display: flex; flex-direction: column; gap: 4px; margin-bottom: 4px;`;
                item.onclick = () => selectSession(s.id);
                
                const header = document.createElement('div');
                header.style.cssText = 'display: flex; justify-content: space-between; align-items: center;';
                header.innerHTML = `<span style="font-weight: bold; font-size: 12px; color: var(--text-primary);">Session #${s.id}</span> <span class="badge ${s.status}" style="font-size: 9px; padding: 2px 4px; border-radius: 2px; text-transform: uppercase; background: ${s.status === 'active' ? 'var(--success)' : 'var(--text-muted)'}; color: white;">${s.status}</span>`;
                
                const time = document.createElement('div');
                time.style.cssText = 'font-size: 10px; color: var(--text-muted);';
                time.textContent = new Date(s.created_at).toLocaleString('fr-FR');
                
                item.appendChild(header);
                item.appendChild(time);
                sidebarList.appendChild(item);
            }
        });
        syncTabs();
    } catch (e) {
        console.warn('Error loading sessions:', e.message);
    }
}

// Sync tabs with session dropdown — compact, scrollable, with close button
function syncTabs() {
    const tabsContainer = document.getElementById('agentic-tabs');
    if (!tabsContainer || !elAgenticSessionSelect) return;
    tabsContainer.innerHTML = '';
    const activeId = elAgenticSessionSelect.value;
    const allOptions = [...elAgenticSessionSelect.options].filter(o => o.value);
    const activeOptions = allOptions.filter(o => !o.textContent.includes('(archived)'));
    
    // Show last 8 active sessions max, older ones go to overflow
    const show = activeOptions.slice(-8);
    if (activeOptions.length > 8) {
        const overflow = document.createElement('button');
        overflow.className = 'agentic-tab';
        overflow.textContent = `⋯ +${activeOptions.length - 8}`;
        overflow.title = `${activeOptions.length - 8} sessions plus anciennes`;
        overflow.onclick = () => {
            elAgenticSessionSelect.value = activeOptions[activeOptions.length - 9]?.value || show[0]?.value;
            elAgenticSessionSelect.dispatchEvent(new Event('change'));
        };
        tabsContainer.appendChild(overflow);
    }
    for (const opt of show) {
        const tab = document.createElement('button');
        tab.className = `agentic-tab ${opt.value === activeId ? 'active' : ''}`;
        const num = opt.textContent.match(/#(\d+)/)?.[1] || '?';
        // Close button
        const closeBtn = document.createElement('span');
        closeBtn.textContent = '✕';
        closeBtn.style.cssText = 'margin-left:3px;font-size:9px;opacity:0.5;cursor:pointer;';
        closeBtn.title = 'Archiver';
        closeBtn.onclick = async (e) => {
            e.stopPropagation();
            try {
                await api(`/api/agentic/sessions/${opt.value}/archive`, { method: 'POST' });
                await loadSessions();
                if (opt.value === activeId) {
                    const remainingActive = [...elAgenticSessionSelect.options].filter(o => o.value && !o.textContent.includes('(archived)'));
                    if (remainingActive.length > 0) {
                        elAgenticSessionSelect.value = remainingActive[0].value;
                        elAgenticSessionSelect.dispatchEvent(new Event('change'));
                    } else {
                        await startNewSession();
                    }
                }
            } catch {
                await startNewSession();
            }
        };
        tab.textContent = `#${num}`;
        tab.title = opt.textContent;
        tab.dataset.sid = opt.value;
        tab.onclick = () => { elAgenticSessionSelect.value = opt.value; elAgenticSessionSelect.dispatchEvent(new Event('change')); };
        tab.appendChild(closeBtn);
        tabsContainer.appendChild(tab);
    }
}

function renderStepsGraph(steps) {
    let graphWrapper = document.getElementById('agentic-steps-graph-replay');
    if (!graphWrapper) {
        graphWrapper = document.createElement('div');
        graphWrapper.id = 'agentic-steps-graph-replay';
        graphWrapper.className = 'agentic-message system';
        graphWrapper.style.cssText = 'border: 1px solid var(--border-color); background: rgba(0,0,0,0.15); padding: 12px; margin: 8px 0; border-radius: 8px;';
    }
    
    // Always append at the end of the history
    elAgenticConversation.appendChild(graphWrapper);

    if (!steps || steps.length === 0) {
        graphWrapper.style.display = 'none';
        return;
    }
    graphWrapper.style.display = 'block';
    graphWrapper.innerHTML = '<strong>Pensée de l\'Agent (Session Replay) :</strong><div class="agent-nodes-container" style="margin-top: 8px;"></div>';
    const graphContainer = graphWrapper.querySelector('.agent-nodes-container');
    
    steps.forEach((step, idx) => {
        const icons = { read_file: '📖', write_file: '✏️', glob_files: '🔍', grep_files: '🔍', list_dir: '📂', exec_shell: '💻', git_status: '⎇', git_commit: '📝', git_init: '🔧', web_fetch: '🌐', web_search: '🔎', probe_path: '🔎', final_answer: '✅' };
        const icon = icons[step.tool] || '➡️';
        
        if (idx > 0) {
            const arrow = document.createElement('div');
            arrow.className = 'agent-node-arrow';
            arrow.textContent = '🠗';
            graphContainer.appendChild(arrow);
        }
        
        const node = document.createElement('div');
        node.className = 'agent-node active';
        node.style.cursor = 'pointer';
        
        let details = '';
        if (step.result) {
            details = step.result.replace(/\n/g, ' ').slice(0, 100);
        }
        
        const isErr = step.result && step.result.startsWith('ERROR');
        node.innerHTML = `
            <span class="agent-node-icon">${icon}</span>
            <span class="agent-node-title">${step.tool}</span>
            <span class="agent-node-details">${escHtml(details)}</span>
            <span class="agent-node-status ${isErr ? 'error' : 'success'}">${isErr ? 'Erreur' : 'Succès'}</span>
        `;
        node.stepData = {
            tool: step.tool,
            icon: icon,
            args: step.args,
            result: step.result,
            thinking: step.thinking || ''
        };
        node.onclick = () => openNodeDetailsDrawer(node.stepData);
        graphContainer.appendChild(node);
    });
}

async function selectSession(sessionId) {
    if (!sessionId) return;
    if (elSettingsSessionSelect) elSettingsSessionSelect.value = sessionId;
    if (elAgenticSessionSelect) elAgenticSessionSelect.value = sessionId;
    
    // Highlight sidebar item
    document.querySelectorAll('.session-sidebar-item').forEach(el => {
        el.style.background = 'rgba(255,255,255,0.02)';
    });
    const sidebarList = document.getElementById('sidebar-sessions-list');
    if (sidebarList) {
        // Refresh sessions list to update active highlight
        setTimeout(async () => {
            const activeItems = sidebarList.children;
            for (let i = 0; i < activeItems.length; i++) {
                const num = activeItems[i].querySelector('span').textContent.match(/#(\d+)/)?.[1];
                if (String(num) === String(sessionId)) {
                    activeItems[i].style.background = 'rgba(255,255,255,0.08)';
                }
            }
        }, 50);
    }

    try {
        const msgs = await api(`/api/agentic/sessions/${sessionId}/conversations`);
        elAgenticConversation.innerHTML = '';
        if (!msgs || msgs.length === 0) {
            elAgenticConversation.innerHTML = '<div class="sys-msg">Aucun message dans cette session.</div>';
            updateContextMeter(0);
            return;
        }
        for (const m of msgs) {
            addAgenticMessage(m.role, m.content);
        }

        // Fetch saved steps and show graph
        try {
            const session = await api(`/api/agentic/sessions/${sessionId}`);
            const state = session.current_state ? JSON.parse(session.current_state) : {};
            const steps = state.steps || [];
            renderStepsGraph(steps);
        } catch (e) {
            console.warn('Error loading session steps:', e);
        }

        // Context meter: total chars / 20000 limit
        const totalChars = msgs.reduce((sum, m) => sum + (m.content ? m.content.length : 0), 0);
        updateContextMeter(totalChars);
    } catch (e) {
        logToTerminal(`Erreur lors du chargement de la session: ${e.message}`, 'error-msg');
    }
}

// Context usage meter — shows in the agentic header
function updateContextMeter(totalChars) {
    const maxChars = 20000;
    const pct = Math.min(100, Math.round((totalChars / maxChars) * 100));
    let meter = document.getElementById('context-meter');
    if (!meter) {
        meter = document.createElement('div');
        meter.id = 'context-meter';
        meter.style.cssText = 'height:3px;border-radius:2px;background:var(--border-color);flex:1;min-width:60px;margin:0 8px;overflow:hidden;';
        const header = document.querySelector('.agentic-header');
        if (header) header.appendChild(meter);
    }
    const bar = document.createElement('div');
    bar.style.cssText = `height:100%;width:${pct}%;border-radius:2px;transition:width 0.3s;background:${pct > 90 ? 'var(--error)' : pct > 70 ? 'var(--warning)' : 'var(--success)'};`;
    meter.innerHTML = '';
    meter.appendChild(bar);
    meter.title = `Contexte: ${totalChars} / ${maxChars} caractères (${pct}%)`;
}

async function startNewSession() {
    if (!currentProjectId) return;
    try {
        const session = await api(`/api/agentic/projects/${currentProjectId}/sessions/new`, { method: 'POST' });
        logToTerminal(`Nouvelle session #${session.id} démarrée.`, 'sys-msg');
        await loadSessions();
        const activeId = elSettingsSessionSelect.value;
        if (activeId) await selectSession(activeId);
    } catch (e) {
        logToTerminal(`Erreur création session: ${e.message}`, 'error-msg');
    }
}

async function loadAgenticHistory(projectId) {
    try {
        await loadSessions();
        const activeSessionId = elSettingsSessionSelect.value;
        if (activeSessionId) {
            await selectSession(activeSessionId);
        } else {
            elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
        }
    } catch {
        elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
    }
}

async function refreshGitStatus() {
    if (!currentProjectId) {
        elGitBranch.textContent = '⎇ — (aucun projet)';
        gitFileStatus = {};
        elGitChanges.textContent = '';
        elGitRemote.textContent = '';
        if (elGitDebug) elGitDebug.textContent = '';
        return;
    }
    try {
        const st = await api(`/api/git/${currentProjectId}/status`);
        if (elGitDebug) elGitDebug.textContent = st ? JSON.stringify(st) : 'no response';
        if (!st || !st.is_repo) {
            gitFileStatus = {};
            elGitBranch.textContent = '⎇ — (pas de repo)';
            elGitChanges.textContent = '';
            elGitRemote.textContent = '';
            elGitChanges.className = '';
            elGitRemote.className = '';
            return;
        }
        elGitBranch.textContent = `⎇ ${st.branch || 'main'}`;
        // Build file → status map for VFS badges
        gitFileStatus = {};
        for (const f of st.staged || []) gitFileStatus[f] = 'A';
        for (const f of st.modified || []) gitFileStatus[f] = 'M';
        for (const f of st.untracked || []) gitFileStatus[f] = '?';
        for (const f of st.deleted || []) gitFileStatus[f] = 'D';
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

        // Populate Git Sidebar Accordion List
        gitAheadFiles = st.ahead_files || [];
        const gitList = document.getElementById('sidebar-git-list');
        if (gitList) {
            gitList.innerHTML = '';
            const fileStatuses = [
                ...st.staged.map(f => ({ path: f, badge: 'A', color: 'var(--success)' })),
                ...st.modified.map(f => ({ path: f, badge: 'M', color: 'var(--warning)' })),
                ...st.untracked.map(f => ({ path: f, badge: '?', color: 'rgba(255,255,255,0.4)' })),
                ...st.deleted.map(f => ({ path: f, badge: 'D', color: 'var(--error)' }))
            ];
            
            if (fileStatuses.length === 0) {
                gitList.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); font-style: italic; padding: 4px;">Aucun changement</div>';
            } else {
                fileStatuses.forEach(fs => {
                    const item = document.createElement('div');
                    item.className = 'vfs-item';
                    item.style.cssText = 'padding: 4px 8px; border-radius: var(--radius-sm); font-size: 12px; display: flex; justify-content: space-between; align-items: center; cursor: pointer;';
                    item.onclick = () => {
                        showGitDiffModal(false);
                        setTimeout(() => {
                            const dropdown = document.getElementById('diff-files-dropdown');
                            if (dropdown) {
                                dropdown.value = fs.path;
                                dropdown.dispatchEvent(new Event('change'));
                            }
                        }, 100);
                    };
                    
                    item.innerHTML = `
                        <span style="font-family: var(--font-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 170px;" title="${fs.path}">${fs.path.split('/').pop()}</span>
                        <span style="font-size: 10px; font-weight: bold; padding: 1px 4px; border-radius: 2px; background: rgba(0,0,0,0.2); color: ${fs.color}; border: 1px solid ${fs.color}; font-family: var(--font-mono);">${fs.badge}</span>
                    `;
                    gitList.appendChild(item);
                });
            }
        }
    } catch (e) {
        elGitBranch.textContent = '⎇ — (erreur)';
        elGitChanges.textContent = '';
        elGitRemote.textContent = '';
        if (elGitDebug) elGitDebug.textContent = 'error: ' + e.message;
    }
    renderVfsList();  // Update git badges in VFS tree
}

async function loadConversations() {
    if (!elConvList) return;
    if (!currentProjectId) { elConvList.innerHTML = '<div class="sys-msg">Aucun projet sélectionné</div>'; return; }
    try {
        const msgs = await api(`/api/projects/${currentProjectId}/conversations?limit=100`);
        elConvList.innerHTML = '';
        if (!msgs || msgs.length === 0) {
            elConvList.innerHTML = '<div class="sys-msg">Aucune conversation</div>';
            return;
        }
        for (const m of msgs) {
            const div = document.createElement('div');
            div.className = `conv-item ${m.role}`;
            const date = new Date(m.created_at).toLocaleString('fr-FR');
            div.innerHTML = `<div class="conv-role">${m.role} <span class="conv-date">${date}</span></div><div class="conv-content">${escHtml(m.content)}</div>`;
            elConvList.appendChild(div);
        }
    } catch (e) {
        elConvList.innerHTML = '<div class="sys-msg">Erreur chargement: ' + e.message + '</div>';
    }
}

function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
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
    return div;
}

async function ensureProjectForAgentic() {
    if (currentProjectId) return true;
    addAgenticMessage('system', '❌ Sélectionne ou crée un projet d\'abord (menu en haut à gauche).');
    return false;
}

async function sendAgenticMessage() {
    const msg = elAgenticInput.value.trim();
    if (!msg) return;
    elAgenticInput.value = '';
    addAgenticMessage('user', msg);
    if (!await ensureProjectForAgentic()) return;
    const backend = elSettingsBackend.value;

    // Create a placeholder for streaming
    const placeholder = addAgenticMessage('system', '🤖 Agent en cours...');
    placeholder.style.opacity = '0.6';

    try {
        const resp = await fetch('/api/agentic/go-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_id: currentProjectId,
                message: msg,
                backend: backend === 'auto' ? '' : backend,
            }),
        });
        if (!resp.ok) { placeholder.textContent = `Erreur ${resp.status}`; return; }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let answer = '';
        let finalCode = '';
        let finalPath = '';
        let thinkingDots = 0;

        // Create a wrapper for visual node graphing
        const graphWrapper = addAgenticMessage('system', '<strong>Pensée de l\'Agent :</strong><div class="agent-nodes-container"></div>');
        const graphContainer = graphWrapper.querySelector('.agent-nodes-container');

        let thinkingTimer = setInterval(() => {
            thinkingDots = (thinkingDots + 1) % 4;
            const dots = '.'.repeat(thinkingDots);
            if (!placeholder.textContent.includes('✅') && !placeholder.textContent.includes('⚠️')) {
                placeholder.textContent = `🤖 réfléchit${dots}`;
            }
        }, 500);

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            thinkingDots = 0;
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (const part of parts) {
                for (const line of part.split('\n')) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const ev = JSON.parse(line.slice(6));
                        if (ev.type === 'mode') {
                            placeholder.textContent = `🤖 Agent · mode ${ev.mode}`;
                        } else if (ev.type === 'require_confirmation') {
                            placeholder.textContent = `⚠️ Commande en attente d'autorisation`;
                            
                            const confirmDiv = document.createElement('div');
                            confirmDiv.className = 'agentic-message system hitl-confirmation-panel';
                            confirmDiv.style.cssText = 'border: 1px solid var(--warning); background: rgba(245,158,11,0.1); padding: 12px; margin: 8px 0; border-radius: 8px;';
                            confirmDiv.innerHTML = `
                                <strong>🔒 Autorisation requise</strong>
                                <div style="margin: 8px 0; font-family: monospace; font-size: 13px; background: rgba(0,0,0,0.2); padding: 6px; border-radius: 4px; word-break: break-all;">
                                    ${escHtml(ev.command)}
                                </div>
                                <div style="display: flex; gap: 8px; margin-top: 8px;">
                                    <button class="hitl-btn-approve" style="background: var(--success); color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold;">Autoriser ✅</button>
                                    <button class="hitl-btn-reject" style="background: var(--error); color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold;">Refuser ❌</button>
                                </div>
                            `;
                            
                            confirmDiv.querySelector('.hitl-btn-approve').onclick = async () => {
                                confirmDiv.querySelectorAll('button').forEach(b => b.disabled = true);
                                try {
                                    await api(`/api/agentic/sessions/${ev.session_id}/confirm_command`, {
                                        method: 'POST',
                                        body: JSON.stringify({ approved: true })
                                    });
                                    confirmDiv.innerHTML = `<div>✅ Commande autorisée : <code>${escHtml(ev.command)}</code></div>`;
                                } catch (err) {
                                    alert("Erreur d'envoi : " + err.message);
                                }
                            };
                            confirmDiv.querySelector('.hitl-btn-reject').onclick = async () => {
                                confirmDiv.querySelectorAll('button').forEach(b => b.disabled = true);
                                try {
                                    await api(`/api/agentic/sessions/${ev.session_id}/confirm_command`, {
                                        method: 'POST',
                                        body: JSON.stringify({ approved: false })
                                    });
                                    confirmDiv.innerHTML = `<div>❌ Commande refusée : <code>${escHtml(ev.command)}</code></div>`;
                                } catch (err) {
                                    alert("Erreur d'envoi : " + err.message);
                                }
                            };
                            
                            elAgenticConversation.appendChild(confirmDiv);
                            elAgenticConversation.scrollTop = elAgenticConversation.scrollHeight;
                        } else if (ev.type === 'step') {
                            const icons = { read_file: '📖', write_file: '✏️', glob_files: '🔍', grep_files: '🔍', list_dir: '📂', exec_shell: '💻', git_status: '⎇', git_commit: '📝', git_init: '🔧', web_fetch: '🌐', web_search: '🔎', probe_path: '🔎', final_answer: '✅' };
                            const icon = icons[ev.tool] || '➡️';
                            
                            // Find and finalize last running subtask node if exists
                            document.querySelectorAll('.agent-node-status.running').forEach(el => {
                                el.className = 'agent-node-status success';
                                el.textContent = 'Terminé';
                            });

                            if (graphContainer.children.length > 0) {
                                const arrow = document.createElement('div');
                                arrow.className = 'agent-node-arrow';
                                arrow.textContent = '🠗';
                                graphContainer.appendChild(arrow);
                            }

                            const node = document.createElement('div');
                            node.className = 'agent-node active';
                            node.style.cursor = 'pointer';

                            let details = '';
                            if (ev.result) {
                                details = ev.result.replace(/\n/g, ' ').slice(0, 100);
                            }

                            const isErr = ev.result && ev.result.startsWith('ERROR');
                            node.innerHTML = `
                                <span class="agent-node-icon">${icon}</span>
                                <span class="agent-node-title">${ev.tool}</span>
                                <span class="agent-node-details">${escHtml(details)}</span>
                                <span class="agent-node-status ${isErr ? 'error' : 'success'}">${isErr ? 'Erreur' : 'Succès'}</span>
                            `;
                            node.stepData = {
                                tool: ev.tool,
                                icon: icon,
                                args: ev.args,
                                result: ev.result,
                                thinking: ev.thinking || answer || ''
                            };
                            node.onclick = () => openNodeDetailsDrawer(node.stepData);
                            graphContainer.appendChild(node);
                            elAgenticConversation.scrollTop = elAgenticConversation.scrollHeight;
                        } else if (ev.type === 'explanation') {
                            placeholder.textContent = `🤖 ${ev.text.slice(0, 120)}`;
                        } else if (ev.type === 'code') {
                            finalCode = ev.code;
                            finalPath = ev.file_path;
                        } else if (ev.type === 'subtask') {
                            if (graphContainer.children.length > 0) {
                                const arrow = document.createElement('div');
                                arrow.className = 'agent-node-arrow';
                                arrow.textContent = '🠗';
                                graphContainer.appendChild(arrow);
                            }

                            const node = document.createElement('div');
                            node.className = 'agent-node';
                            node.innerHTML = `
                                <span class="agent-node-icon">📋</span>
                                <span class="agent-node-title">Tâche</span>
                                <span class="agent-node-details">${escHtml(ev.subtask)}</span>
                                <span class="agent-node-status running">En cours</span>
                            `;
                            graphContainer.appendChild(node);
                            elAgenticConversation.scrollTop = elAgenticConversation.scrollHeight;
                        } else if (ev.type === 'done') {
                            answer = ev.answer;
                        }
                    } catch (e) { /* skip malformed events */ }
                }
            }
        }

        clearInterval(thinkingTimer);
        placeholder.remove();

        let collabHtml = '';
        const elSessionSelect = document.getElementById('agentic-session-select');
        const activeSessionId = elSessionSelect ? elSessionSelect.value : null;
        if (activeSessionId) {
            try {
                const pendings = await api(`/api/agentic/sessions/${activeSessionId}/pending`);
                if (pendings && pendings.length > 0) {
                    collabHtml += `<div class="collab-diff-container" data-session-id="${activeSessionId}">`;
                    collabHtml += `<h4>Modifications de code proposées :</h4>`;
                    for (const pc of pendings) {
                        collabHtml += `<div class="collab-file-diff">`;
                        collabHtml += `<strong>📄 ${pc.path}</strong>`;
                        
                        const oldLines = pc.old_content ? pc.old_content.split('\n') : [];
                        const newLines = pc.new_content ? pc.new_content.split('\n') : [];
                        
                        let diffLines = [];
                        let i = 0, j = 0;
                        while (i < oldLines.length || j < newLines.length) {
                            if (i < oldLines.length && j < newLines.length && oldLines[i] === newLines[j]) {
                                diffLines.push(`  ${oldLines[i]}`);
                                i++;
                                j++;
                            } else {
                                if (i < oldLines.length) {
                                    diffLines.push(`<span class="diff-removed">- ${oldLines[i]}</span>`);
                                    i++;
                                }
                                if (j < newLines.length) {
                                    diffLines.push(`<span class="diff-added">+ ${newLines[j]}</span>`);
                                    j++;
                                }
                            }
                        }
                        
                        collabHtml += `<pre><code>${diffLines.slice(0, 50).join('\n')}${diffLines.length > 50 ? '\n... (tronqué)' : ''}</code></pre>`;
                        collabHtml += `</div>`;
                    }
                    collabHtml += `<div class="collab-actions">`;
                    collabHtml += `<button class="btn btn-sm btn-primary collab-btn-accept">✅ Valider</button>`;
                    collabHtml += `<button class="btn btn-sm btn-secondary collab-btn-reject">❌ Rejeter et annuler</button>`;
                    collabHtml += `</div>`;
                    collabHtml += `</div>`;
                }
            } catch (err) {
                console.error("Error loading pending changes:", err);
            }
        }

        if (finalCode && finalPath) {
            if (!filesList.includes(finalPath)) filesList.push(finalPath);
            addAgenticMessage('assistant', `✅ **Terminé** — fichiers créés. Consulte l'onglet Fichiers.\n${collabHtml}`);
            if (currentProjectId) await loadProjectFromServer(currentProjectId);
        } else if (answer) {
            addAgenticMessage('assistant', `${answer}\n${collabHtml}`);
            if (currentProjectId) await loadProjectFromServer(currentProjectId);
        } else {
            addAgenticMessage('assistant', `✅ Terminé.\n${collabHtml}`);
            if (currentProjectId) await loadProjectFromServer(currentProjectId);
        }
    } catch (e) {
        addAgenticMessage('system', `Erreur: ${e.message}`);
    }
}

function updateGcaTabVisibility(enabled) {
    if (!elTabBtnGca) return;
    if (enabled) {
        elTabBtnGca.style.display = '';
    } else {
        elTabBtnGca.style.display = 'none';
        const activeTab = document.querySelector('.tab-btn.active');
        if (activeTab && activeTab.dataset.tab === 'tab-gca') {
            switchTab('tab-agentic');
        }
    }
}

function switchSidebarTab(tab) {
    const btnVfs = document.getElementById('tab-btn-vfs');
    const btnSessions = document.getElementById('tab-btn-sessions');
    const btnPackages = document.getElementById('tab-btn-packages');
    const contentVfs = document.getElementById('sidebar-content-vfs');
    const contentSessions = document.getElementById('sidebar-content-sessions');
    const contentPackages = document.getElementById('sidebar-content-packages');
    if (!btnVfs || !btnSessions) return;
    
    [btnVfs, btnSessions, btnPackages].forEach(btn => {
        if (btn) {
            btn.classList.remove('active');
            btn.style.borderBottom = 'none';
            btn.style.color = 'var(--text-muted)';
        }
    });
    [contentVfs, contentSessions, contentPackages].forEach(content => {
        if (content) content.style.display = 'none';
    });

    if (tab === 'vfs') {
        btnVfs.classList.add('active');
        btnVfs.style.borderBottom = '2px solid var(--accent-color)';
        btnVfs.style.color = 'var(--text-primary)';
        if (contentVfs) contentVfs.style.display = 'flex';
    } else if (tab === 'sessions') {
        btnSessions.classList.add('active');
        btnSessions.style.borderBottom = '2px solid var(--accent-color)';
        btnSessions.style.color = 'var(--text-primary)';
        if (contentSessions) contentSessions.style.display = 'flex';
        loadSessions();
    } else if (tab === 'packages') {
        if (btnPackages) {
            btnPackages.classList.add('active');
            btnPackages.style.borderBottom = '2px solid var(--accent-color)';
            btnPackages.style.color = 'var(--text-primary)';
        }
        if (contentPackages) contentPackages.style.display = 'flex';
        refreshPackages();
    }
}

function updateWorkspaceLayout(layout) {
    const container = document.getElementById('editor-results-container');
    const handle = document.getElementById('resize-handle');
    if (!container || !handle) return;
    
    if (layout === 'bottom') {
        container.style.flexDirection = 'column';
        handle.style.height = '6px';
        handle.style.width = '100%';
        handle.style.cursor = 'row-resize';
    } else {
        container.style.flexDirection = 'row';
        handle.style.height = '100%';
        handle.style.width = '6px';
        handle.style.cursor = 'col-resize';
    }
    if (editor) editor.layout();
    if (monacoDiffEditor) monacoDiffEditor.layout();
}

async function main() {
    try {
        const gcaEnabled = localStorage.getItem('pll-enable-gca') === 'true';
        if (elSettingsEnableGca) elSettingsEnableGca.checked = gcaEnabled;
        updateGcaTabVisibility(gcaEnabled);

        // 1. Initialize sidebar tab events
        document.getElementById('tab-btn-vfs')?.addEventListener('click', () => switchSidebarTab('vfs'));
        document.getElementById('tab-btn-sessions')?.addEventListener('click', () => switchSidebarTab('sessions'));
        document.getElementById('tab-btn-packages')?.addEventListener('click', () => switchSidebarTab('packages'));
        document.getElementById('btn-sidebar-new-session')?.addEventListener('click', startNewSession);

        // 2. Initialize layout configuration
        const layoutSelect = document.getElementById('layout-select');
        if (layoutSelect) {
            const savedLayout = localStorage.getItem('pll-layout') || 'right';
            layoutSelect.value = savedLayout;
            updateWorkspaceLayout(savedLayout);
            layoutSelect.addEventListener('change', (e) => {
                const layout = e.target.value;
                localStorage.setItem('pll-layout', layout);
                updateWorkspaceLayout(layout);
            });
        }
        
        // 3. Initialize Left Navigation Items
        const navItems = ['nav-item-vfs', 'nav-item-orchestrator', 'nav-item-db', 'nav-item-settings'];
        navItems.forEach(id => {
            document.getElementById(id)?.addEventListener('click', (e) => {
                navItems.forEach(n => document.getElementById(n)?.classList.remove('active'));
                document.getElementById(id)?.classList.add('active');
                
                const sidebar = document.getElementById('sidebar-files');
                const canvas = document.getElementById('orchestrator-canvas');
                const editorView = document.querySelector('.editor-container');
                
                if (id === 'nav-item-vfs') {
                    sidebar.style.display = 'flex';
                    canvas.style.display = 'none';
                    editorView.style.display = 'block';
                    switchSidebarTab('vfs');
                } else if (id === 'nav-item-orchestrator') {
                    sidebar.style.display = 'none';
                    canvas.style.display = 'block';
                    editorView.style.display = 'none';
                    drawConnection();
                } else if (id === 'nav-item-db') {
                    sidebar.style.display = 'flex';
                    canvas.style.display = 'none';
                    editorView.style.display = 'none';
                    switchSidebarTab('packages');
                } else {
                    sidebar.style.display = 'flex';
                    canvas.style.display = 'none';
                    editorView.style.display = 'none';
                }
                if (editor) editor.layout();
            });
        });

        // 4. Initialize Right Panel tabs
        document.querySelectorAll('.results-pane .tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tabId = btn.getAttribute('data-tab');
                switchTab(tabId);
            });
        });

        // Fullscreen toggle event listener
        document.getElementById('btn-agentic-fullscreen')?.addEventListener('click', () => {
            document.querySelector('.results-pane')?.classList.toggle('fullscreen');
            if (editor) editor.layout();
        });

        // 5. Initialize Canvas Drag and Connections
        initVisualCanvas();

        // 6. Initialize Git Commit from Sidebar
        document.getElementById('git-btn-commit-sidebar')?.addEventListener('click', async () => {
            if (!currentProjectId) return;
            const msgInput = document.getElementById('git-commit-msg-sidebar');
            const commitMsg = msgInput.value.trim();
            const btn = document.getElementById('git-btn-commit-sidebar');
            btn.disabled = true;
            btn.textContent = 'Commit...';
            try {
                const res = await api(`/api/git/${currentProjectId}/commit`, {
                    method: 'POST',
                    body: JSON.stringify({ message: commitMsg, auto_message: commitMsg === "" })
                });
                if (res.ok) {
                    logToTerminal(`Git Commit: ${res.message}`, 'sys-msg');
                    msgInput.value = '';
                    refreshGitStatus();
                } else {
                    logToTerminal(`Erreur Commit: ${res.err || res.out}`, 'error-msg');
                }
            } catch (e) {
                logToTerminal(`Erreur Commit: ${e.message}`, 'error-msg');
            } finally {
                btn.disabled = false;
                btn.textContent = '💾 Commit';
            }
        });

        // 7. Load Monaco Editor with isolated error safety
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
            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, (e) => {
                saveProjectToServer();
            });
        } catch (monacoErr) {
            console.error("Monaco load blocked or failed:", monacoErr);
        }

        // 8. Load Projects and Git states from server
        clearDefaults();
        await loadProjects();
        await refreshPackages();
        // Restore last project
        const lastProjectId = localStorage.getItem('pll-last-project');
        if (lastProjectId) {
            const projectSelect = document.getElementById('project-select');
            if ([...projectSelect.options].some(o => o.value === lastProjectId)) {
                projectSelect.value = lastProjectId;
                currentProjectId = parseInt(lastProjectId);
                try {
                    await loadProjectFromServer(currentProjectId);
                } catch (err) {
                    console.warn("Could not load last project from server:", err);
                }
            }
        }
        if (!currentProjectId) {
            logToTerminal('Bienvenue ! Crée ou sélectionne un projet pour commencer.', 'sys-msg');
            openFiles = ['logic_flow.agent', 'orchestrator.js'];
            activeFile = 'logic_flow.agent';
            set_virtual_file('orchestrator.js', '// PLL Orchestrator runtime logic\nconsole.log("Agent Orchestrator initialized.");');
            renderTabs();
        }
        refreshGitStatus();
    } catch (e) {
        logToTerminal(`Erreur: ${e}`, 'error-msg');
    }
}

function drawConnection() {
    const svg = document.getElementById('canvas-svg');
    const portOut = document.getElementById('port-trigger-out');
    const portIn = document.getElementById('port-agent-in');
    if (!svg || !portOut || !portIn) return;
    
    const rectOut = portOut.getBoundingClientRect();
    const rectIn = portIn.getBoundingClientRect();
    const rectCanvas = svg.getBoundingClientRect();
    
    const x1 = rectOut.left + rectOut.width/2 - rectCanvas.left;
    const y1 = rectOut.top + rectOut.height/2 - rectCanvas.top;
    const x2 = rectIn.left + rectIn.width/2 - rectCanvas.left;
    const y2 = rectIn.top + rectIn.height/2 - rectCanvas.top;
    
    const dx = Math.abs(x2 - x1) * 0.5;
    const pathData = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
    
    let path = svg.querySelector('#connection-line');
    if (!path) {
        path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('id', 'connection-line');
        path.setAttribute('stroke', '#6366f1');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('fill', 'none');
        svg.appendChild(path);
    }
    path.setAttribute('d', pathData);
}

function makeDraggable(el) {
    let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
    const header = el.querySelector('.node-header') || el;
    header.onmousedown = dragMouseDown;
    
    function dragMouseDown(e) {
        e = e || window.event;
        e.preventDefault();
        pos3 = e.clientX;
        pos4 = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementDrag;
    }
    
    function elementDrag(e) {
        e = e || window.event;
        e.preventDefault();
        pos1 = pos3 - e.clientX;
        pos2 = pos4 - e.clientY;
        pos3 = e.clientX;
        pos4 = e.clientY;
        el.style.top = (el.offsetTop - pos2) + "px";
        el.style.left = (el.offsetLeft - pos1) + "px";
        drawConnection();
    }
    
    function closeDragElement() {
        document.onmouseup = null;
        document.onmousemove = null;
    }
}

let zoomScale = 1.0;

function initVisualCanvas() {
    const trigger = document.getElementById('node-trigger');
    const agent = document.getElementById('node-agent');
    if (trigger) makeDraggable(trigger);
    if (agent) makeDraggable(agent);
    
    window.addEventListener('resize', drawConnection);
    setTimeout(drawConnection, 500);

    // Dynamic zoom and fit action handlers
    document.getElementById('ctrl-zoom-in')?.addEventListener('click', () => {
        zoomScale = Math.min(2.0, zoomScale + 0.1);
        document.querySelectorAll('.flow-node').forEach(node => {
            node.style.transform = `scale(${zoomScale})`;
        });
        const svg = document.getElementById('canvas-svg');
        if (svg) svg.style.transform = `scale(${zoomScale})`;
        drawConnection();
    });
    
    document.getElementById('ctrl-zoom-out')?.addEventListener('click', () => {
        zoomScale = Math.max(0.5, zoomScale - 0.1);
        document.querySelectorAll('.flow-node').forEach(node => {
            node.style.transform = `scale(${zoomScale})`;
        });
        const svg = document.getElementById('canvas-svg');
        if (svg) svg.style.transform = `scale(${zoomScale})`;
        drawConnection();
    });
    
    document.getElementById('ctrl-fit')?.addEventListener('click', () => {
        zoomScale = 1.0;
        document.querySelectorAll('.flow-node').forEach(node => {
            node.style.transform = `scale(1.0)`;
        });
        const svg = document.getElementById('canvas-svg');
        if (svg) svg.style.transform = `scale(1.0)`;
        if (trigger) { trigger.style.left = '100px'; trigger.style.top = '150px'; }
        if (agent) { agent.style.left = '350px'; agent.style.top = '250px'; }
        drawConnection();
    });
}

function toggleSidebarSection(sectionName) {
    const sec = document.getElementById(`sec-${sectionName}`);
    const content = document.getElementById(`sec-content-${sectionName}`);
    const caret = sec.querySelector('.sec-caret');
    if (!sec || !content || !caret) return;
    
    const isCollapsed = content.style.display === 'none';
    if (isCollapsed) {
        content.style.display = (sectionName === 'git') ? 'flex' : 'block';
        caret.style.transform = 'rotate(90deg)';
        sec.classList.add('active');
    } else {
        content.style.display = 'none';
        caret.style.transform = 'rotate(0deg)';
        sec.classList.remove('active');
    }
}

function openNodeDetailsDrawer(stepData) {
    const drawer = document.getElementById('agent-details-drawer');
    if (!drawer) return;
    
    document.getElementById('drawer-icon').textContent = stepData.icon || '📖';
    document.getElementById('drawer-tool-name').textContent = stepData.tool || 'Action';
    document.getElementById('drawer-thinking').textContent = stepData.thinking || 'Aucun thought disponible.';
    
    const argsEl = document.querySelector('#drawer-args pre');
    if (argsEl) {
        if (typeof stepData.args === 'object') {
            argsEl.textContent = JSON.stringify(stepData.args, null, 2);
        } else if (typeof stepData.args === 'string') {
            try {
                argsEl.textContent = JSON.stringify(JSON.parse(stepData.args), null, 2);
            } catch {
                argsEl.textContent = stepData.args;
            }
        } else {
            argsEl.textContent = String(stepData.args || '');
        }
    }
    
    document.getElementById('drawer-result').textContent = stepData.result || 'Aucune sortie.';
    drawer.style.right = '0';
}

function renderGraphIntoContainer(containerId, steps) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    
    if (!steps || steps.length === 0) {
        container.innerHTML = '<div class="sys-msg">Aucune étape exécutée.</div>';
        return;
    }
    
    const graphDiv = document.createElement('div');
    graphDiv.className = 'agent-nodes-container';
    
    steps.forEach((step, idx) => {
        const icons = { read_file: '📖', write_file: '✏️', glob_files: '🔍', grep_files: '🔍', list_dir: '📂', exec_shell: '💻', git_status: '⎇', git_commit: '📝', git_init: '🔧', web_fetch: '🌐', web_search: '🔎', probe_path: '🔎', final_answer: '✅' };
        const icon = icons[step.tool] || '➡️';
        
        if (idx > 0) {
            const arrow = document.createElement('div');
            arrow.className = 'agent-node-arrow';
            arrow.textContent = '🠗';
            graphDiv.appendChild(arrow);
        }
        
        const node = document.createElement('div');
        node.className = 'agent-node active';
        node.style.cursor = 'pointer';
        
        let details = '';
        if (step.result) {
            details = step.result.replace(/\n/g, ' ').slice(0, 100);
        }
        
        const isErr = step.result && step.result.startsWith('ERROR');
        node.innerHTML = `
            <span class="agent-node-icon">${icon}</span>
            <span class="agent-node-title">${step.tool}</span>
            <span class="agent-node-details">${escHtml(details)}</span>
            <span class="agent-node-status ${isErr ? 'error' : 'success'}">${isErr ? 'Erreur' : 'Succès'}</span>
        `;
        node.stepData = {
            tool: step.tool,
            icon: icon,
            args: step.args,
            result: step.result,
            thinking: step.thinking || ''
        };
        node.onclick = () => openNodeDetailsDrawer(node.stepData);
        graphDiv.appendChild(node);
    });
    container.appendChild(graphDiv);
}

document.getElementById('btn-drawer-close')?.addEventListener('click', () => {
    const drawer = document.getElementById('agent-details-drawer');
    if (drawer) drawer.style.right = '-400px';
});

async function gcaRefreshStatus() {
    const pid = currentProjectId;
    if (!pid) return;
    try {
        const status = await api(`/api/gca/status/${pid}`);
        const p = status.current_primary, s = status.current_shadow;
        elGcaStatus.innerHTML = `<div class="gca-info" style="display: flex; gap: 20px;">
            <div><strong>Générations:</strong> ${status.total_generations}</div>
            <div><strong>Primaire:</strong> ${p ? `#${p.id} (gen ${p.generation})` : 'Aucun'}</div>
            <div><strong>Ombre:</strong> ${s ? `#${s.id} (gen ${s.generation})` : 'Aucun'}</div>
            <div><strong>Vault:</strong> ${status.vault_entries_count} entrées</div>
        </div>`;
        if (currentProjectId !== pid) return;
        
        // Load and render Primary Session Graph
        if (p) {
            try {
                const pSession = await api(`/api/agentic/sessions/${p.id}`);
                const state = pSession.current_state ? JSON.parse(pSession.current_state) : {};
                renderGraphIntoContainer('gca-primary-graph', state.steps || []);
            } catch (err) { console.warn("Error loading primary session details:", err); }
        } else {
            document.getElementById('gca-primary-graph').innerHTML = '<div class="sys-msg">Aucun graphe d\'agent primaire.</div>';
        }
        
        // Load and render Shadow Session Graph
        if (s) {
            try {
                const sSession = await api(`/api/agentic/sessions/${s.id}`);
                const state = sSession.current_state ? JSON.parse(sSession.current_state) : {};
                renderGraphIntoContainer('gca-shadow-graph', state.steps || []);
            } catch (err) { console.warn("Error loading shadow session details:", err); }
        } else {
            document.getElementById('gca-shadow-graph').innerHTML = '<div class="sys-msg">Aucun graphe d\'agent ombre.</div>';
        }

        const vault = await api(`/api/gca/vault/${pid}`);
        if (currentProjectId !== pid) return;
        elGcaVault.innerHTML = vault.length === 0
            ? '<div class="sys-msg">Vault vide.</div>'
            : vault.slice(-10).map(e =>
                `<div class="vault-entry" style="margin-bottom: 8px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px;"><strong>${e.key}</strong> <span class="sys-msg">(${new Date(e.created_at).toLocaleString()})</span><pre style="margin: 4px 0; max-height: 80px; overflow-y: auto; background: rgba(0,0,0,0.2); padding: 4px; font-size: 11px;">${e.content.slice(0, 200)}</pre><button class="btn btn-sm btn-secondary publish-pkg-btn" data-key="${escHtml(e.key)}" title="Publier comme paquet PLL">📦 Publier</button></div>`
            ).join('');
        document.querySelectorAll('.publish-pkg-btn').forEach(btn => {
            btn.addEventListener('click', () => publishFromVault(btn.dataset.key));
        });
    } catch (e) { console.warn(e.message); }
}

async function publishFromVault(key) {
    if (!currentProjectId) return;
    const name = prompt("Nom du paquet PLL:", key.replace(/[^a-zA-Z0-9_]/g, "_").toLowerCase());
    if (!name) return;
    try {
        const vault = await api(`/api/gca/vault/${currentProjectId}`);
        const entry = vault.find(e => e.key === key);
        const source = entry ? entry.content : "";
        await api('/api/packages', {
            method: 'POST',
            body: JSON.stringify({ name, version: "0.1.0", description: `Published from ${key}`, author: "GCA Agent", source_content: source }),
        });
        logToTerminal(`📦 Package '${name}' publié.`, 'sys-msg');
        await refreshPackages();
        switchTab('tab-packages');
    } catch (e) { logToTerminal(`Erreur publication: ${e.message}`, 'error-msg'); }
}

async function refreshPackages() {
    try {
        const pkgs = await api('/api/packages');
        if (!elPackagesList) return;
        elPackagesList.innerHTML = pkgs.length === 0
            ? '<div class="sys-msg">Aucun paquet.</div>'
            : (Array.isArray(pkgs) ? pkgs.map(p => `<div class="package-item"><strong>${p.name}</strong> v${p.version} <span class="sys-msg">par ${p.author || '?'}</span> <button class="btn btn-sm btn-secondary view-pkg-btn" data-name="${p.name}" title="Voir le code source">📄</button></div>`).join('') : '');
        document.querySelectorAll('.view-pkg-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                try {
                    const pkg = await api(`/api/packages/${encodeURIComponent(btn.dataset.name)}/download`);
                    addAgenticMessage('assistant', `**${pkg.name}** v${pkg.version}\n\`\`\`pll\n${(pkg.source_content || '').slice(0, 2000)}\n\`\`\``);
                    switchTab('tab-agentic');
                } catch (e) { logToTerminal(`Erreur: ${e.message}`, 'error-msg'); }
            });
        });
    } catch {
        if (elPackagesList) elPackagesList.innerHTML = '<div class="sys-msg">Serveur indisponible.</div>';
    }
}

// Terminal: execute command via API
async function execTerminalCommand(cmd) {
    if (!cmd.trim()) return;
    termHistory.push(cmd);
    termHistIdx = termHistory.length;
    // Show command
    const cmdDiv = document.createElement('div');
    cmdDiv.className = 'cmd';
    cmdDiv.textContent = `❯ ${cmd}`;
    elTerminalLog.appendChild(cmdDiv);
    elTerminalLog.scrollTop = elTerminalLog.scrollHeight;
    try {
        const resp = await fetch(`/api/exec/run?command=${encodeURIComponent(cmd)}&timeout=30`, { method: 'POST' });
        const result = await resp.json();
        if (result.stdout) {
            const out = document.createElement('div');
            out.className = 'stdout';
            out.textContent = result.stdout;
            elTerminalLog.appendChild(out);
        }
        if (result.stderr) {
            const err = document.createElement('div');
            err.className = 'stderr';
            err.textContent = result.stderr;
            elTerminalLog.appendChild(err);
        }
        const status = document.createElement('div');
        status.className = result.exit_code === 0 ? 'exit-ok' : 'exit-err';
        status.textContent = `Process exited with code ${result.exit_code}`;
        elTerminalLog.appendChild(status);
    } catch (e) {
        const err = document.createElement('div');
        err.className = 'stderr';
        err.textContent = `Erreur: ${e.message}`;
        elTerminalLog.appendChild(err);
    }
    elTerminalLog.scrollTop = elTerminalLog.scrollHeight;
}

if (elTerminalInput) {
    elTerminalInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const cmd = elTerminalInput.value;
            elTerminalInput.value = '';
            execTerminalCommand(cmd);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (termHistIdx > 0) {
                termHistIdx--;
                elTerminalInput.value = termHistory[termHistIdx];
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (termHistIdx < termHistory.length - 1) {
                termHistIdx++;
                elTerminalInput.value = termHistory[termHistIdx];
            } else {
                termHistIdx = termHistory.length;
                elTerminalInput.value = '';
            }
        }
    });
}

function logToExecutionLogs(msg, className = '') {
    const elExecutionLogs = document.getElementById('execution-logs');
    if (!elExecutionLogs) return;
    const div = document.createElement('div');
    div.className = className;
    div.textContent = msg;
    elExecutionLogs.appendChild(div);
    elExecutionLogs.scrollTop = elExecutionLogs.scrollHeight;
}

async function runPllCode() {
    const code = editor.getValue();
    if (!code) {
        logToExecutionLogs("Erreur : Aucun code à exécuter.", "stderr");
        return;
    }
    switchTab('tab-logs');
    logToExecutionLogs(`❯ pll run ${activeFile || 'main.pll'}`, "cmd");
    try {
        const resp = await fetch('/api/pll/exec', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const result = await resp.json();
        if (result.output) {
            logToExecutionLogs(result.output, "stdout");
        }
        if (result.error) {
            logToExecutionLogs(result.error, "stderr");
        }
        logToExecutionLogs(`Process finished: ${result.ok ? 'SUCCESS' : 'FAILED'}`, result.ok ? 'exit-ok' : 'exit-err');
    } catch (e) {
        logToExecutionLogs(`Erreur lors de l'exécution: ${e.message}`, "stderr");
    }
}

if (elBtnRunCode) {
    elBtnRunCode.onclick = runPllCode;
}

if (elBtnSaveFile) {
    elBtnSaveFile.onclick = saveProjectToServer;
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
        renderTabs();
        renderVfsList();
        elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
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
    selectedTemplate = 'empty';
    document.querySelectorAll('.template-chip').forEach(c => c.classList.remove('active'));
    const defaultChip = document.querySelector('.template-chip[data-tpl="empty"]');
    if (defaultChip) defaultChip.classList.add('active');
    elProjectModal.classList.add('open');
});

elProjectModalCancel.addEventListener('click', () => elProjectModal.classList.remove('open'));
// Template chips for new project
let selectedTemplate = 'empty';
document.addEventListener('click', (e) => {
    const chip = e.target.closest('.template-chip');
    if (!chip) return;
    document.querySelectorAll('.template-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    selectedTemplate = chip.dataset.tpl;
});

function getStarterFiles(tpl) {
    if (tpl === 'flask') return {
        'app.py': 'from flask import Flask, jsonify, request\n\napp = Flask(__name__)\n\n@app.route("/")\ndef home():\n    return jsonify({"message": "Hello PLL!"})\n\nif __name__ == "__main__":\n    app.run(debug=True)',
        'requirements.txt': 'flask\n',
    };
    if (tpl === 'cli') return {
        'main.py': 'import sys\n\ndef main():\n    args = sys.argv[1:]\n    print(f"Hello PLL! Args: {args}")\n\nif __name__ == "__main__":\n    main()',
    };
    if (tpl === 'pll') return {
        'main.pll': 'fn greet(name: str) -> str:\n    return str_concat("Hello, ", name)\n\nrender greet("PLL")',
    };
    return {};
}

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
        // Fill starter files from template
        const starter = getStarterFiles(selectedTemplate);
        for (const [path, content] of Object.entries(starter)) {
            set_virtual_file(path, content);
            filesList.push(path);
        }
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

elAgenticSend?.addEventListener('click', sendAgenticMessage);
elAgenticInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgenticMessage(); }
});
elAgenticClear?.addEventListener('click', () => {
    elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
    agenticConversationHistory = [];
});
document.getElementById('btn-agentic-refresh')?.addEventListener('click', () => {
    elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
    agenticConversationHistory = [];
});

const elBtnTerminalClear = document.getElementById('btn-terminal-clear');
if (elBtnTerminalClear) {
    elBtnTerminalClear.addEventListener('click', () => {
        elTerminalLog.innerHTML = '<div class="sys-msg">Console PLL prête. Tapez une commande ci-dessous.</div>';
    });
}

elBtnRefreshPackages?.addEventListener('click', refreshPackages);

// Git status bar debug (click to toggle)
const gitStatusBar = document.getElementById('git-status-bar');
if (gitStatusBar) {
    gitStatusBar.addEventListener('click', (e) => {
        if (e.target.tagName === 'BUTTON') return; // don't toggle on button clicks
        if (elGitDebug) elGitDebug.style.display = elGitDebug.style.display === 'none' ? 'inline' : 'none';
    });
}

// Monaco Diff Editor Integration
function showMonacoDiff(originalContent, modifiedContent, filePath) {
    const container = document.getElementById('monaco-diff-container');
    const textContent = document.getElementById('diff-content');
    if (!container || !textContent) return;
    
    container.style.display = 'block';
    textContent.style.display = 'none';
    
    if (!monacoDiffEditor) {
        monacoDiffEditor = monaco.editor.createDiffEditor(container, {
            theme: 'vs-dark',
            automaticLayout: true,
            readOnly: true
        });
    }
    
    const lang = detectLanguage(filePath);
    
    const currentModels = monacoDiffEditor.getModel();
    if (currentModels) {
        if (currentModels.original) currentModels.original.dispose();
        if (currentModels.modified) currentModels.modified.dispose();
    }
    
    monacoDiffEditor.setModel({
        original: monaco.editor.createModel(originalContent, lang),
        modified: monaco.editor.createModel(modifiedContent, lang)
    });
}

async function showGitDiffModal(staged = false) {
    const elModal = document.getElementById('diff-modal');
    const elContent = document.getElementById('diff-content');
    const elBadge = document.getElementById('diff-badge');
    const dropdown = document.getElementById('diff-files-dropdown');
    const container = document.getElementById('monaco-diff-container');
    
    elModal.classList.add('open');
    elContent.style.display = 'block';
    container.style.display = 'none';
    dropdown.style.display = 'none';
    elContent.textContent = 'Chargement...';
    elBadge.textContent = '';
    
    try {
        const st = await api(`/api/git/${currentProjectId}/status`);
        elBadge.textContent = `⎇ ${st.branch || 'main'}`;
        
        const files = [];
        if (staged) {
            files.push(...st.staged);
        } else {
            files.push(...st.modified, ...st.untracked, ...st.deleted);
        }
        
        if (files.length === 0) {
            elContent.textContent = staged ? 'Aucun changement stagé.' : 'Aucune modification.';
            return;
        }
        
        dropdown.innerHTML = '';
        files.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f;
            opt.textContent = f;
            dropdown.appendChild(opt);
        });
        dropdown.style.display = 'inline-block';
        
        const firstFile = files[0];
        await loadFileDiff(firstFile);
        
    } catch (e) {
        elContent.style.display = 'block';
        container.style.display = 'none';
        dropdown.style.display = 'none';
        elContent.textContent = `Erreur: ${e.message}`;
    }
}

async function loadFileDiff(filePath) {
    try {
        const origRes = await api(`/api/git/${currentProjectId}/show?path=${encodeURIComponent(filePath)}`);
        const originalContent = origRes.content || "";
        const currentContent = get_virtual_file(filePath) || "";
        showMonacoDiff(originalContent, currentContent, filePath);
    } catch (e) {
        console.warn("Could not load diff for", filePath, e);
    }
}

// Git diff button
const gitDiffBtn = document.getElementById('git-diff-btn');
if (gitDiffBtn) {
    gitDiffBtn.addEventListener('click', () => showGitDiffModal(false));
}

document.getElementById('diff-files-dropdown')?.addEventListener('change', (e) => {
    loadFileDiff(e.target.value);
});

document.getElementById('diff-btn-all')?.addEventListener('click', () => showGitDiffModal(false));
document.getElementById('diff-btn-staged')?.addEventListener('click', () => showGitDiffModal(true));

document.getElementById('diff-btn-close')?.addEventListener('click', () => {
    document.getElementById('diff-modal').classList.remove('open');
});

// Commit Button handler
document.getElementById('git-btn-commit')?.addEventListener('click', async () => {
    if (!currentProjectId) return;
    const msgInput = document.getElementById('git-commit-msg');
    const commitMsg = msgInput.value.trim();
    const btn = document.getElementById('git-btn-commit');
    const elContent = document.getElementById('diff-content');
    btn.disabled = true;
    btn.textContent = 'Commit...';
    try {
        const res = await api(`/api/git/${currentProjectId}/commit`, {
            method: 'POST',
            body: JSON.stringify({ message: commitMsg, auto_message: commitMsg === "" })
        });
        if (res.ok) {
            logToTerminal(`Git Commit: ${res.message}`, 'sys-msg');
            msgInput.value = '';
            elContent.textContent = 'Commit réussi avec succès !';
            refreshGitStatus();
        } else {
            logToTerminal(`Erreur Commit: ${res.err || res.out}`, 'error-msg');
        }
    } catch (e) {
        logToTerminal(`Erreur Commit: ${e.message}`, 'error-msg');
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Commit';
    }
});

// Load conversations on tab switch handled inside switchTab

elBtnRefreshConv?.addEventListener('click', loadConversations);

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => {
        c.classList.remove('active');
        c.style.display = 'none';
    });
    const tab = document.querySelector(`[data-tab="${tabId}"]`);
    if (tab) tab.classList.add('active');
    const content = document.getElementById(tabId);
    if (content) {
        content.classList.add('active');
        content.style.display = (tabId === 'tab-agentic' || tabId === 'tab-shell' || tabId === 'tab-logs') ? 'flex' : 'block';
    }
    if (tabId === 'tab-conversations' || tabId === 'tab-agentic') loadConversations();
}

// Settings Modal bindings
if (elBtnSettings) {
    elBtnSettings.onclick = () => {
        elSettingsModal.classList.add('open');
        loadSessions();
    };
}
if (elBtnSettingsClose) {
    elBtnSettingsClose.onclick = () => {
        elSettingsModal.classList.remove('open');
    };
}
if (elSettingsSessionSelect) {
    elSettingsSessionSelect.onchange = (e) => {
        selectSession(e.target.value);
    };
}
if (elAgenticSessionSelect) {
    elAgenticSessionSelect.onchange = (e) => {
        selectSession(e.target.value);
    };
}
if (elSettingsEnableGca) {
    elSettingsEnableGca.onchange = (e) => {
        const val = e.target.checked;
        localStorage.setItem('pll-enable-gca', val);
        updateGcaTabVisibility(val);
    };
}
if (elBtnNewSession) {
    elBtnNewSession.onclick = () => {
        startNewSession();
    };
}
if (elBtnAgenticNewSession) {
    elBtnAgenticNewSession.onclick = () => {
        startNewSession();
    };
}

// Resize handle for left sidebar/editor panes
if (elResizeHandleLeft) {
    let isDragging = false;
    elResizeHandleLeft.addEventListener('mousedown', (e) => {
        isDragging = true;
        elResizeHandleLeft.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const sidebarPane = document.getElementById('sidebar-files');
        const editorPane = document.querySelector('.editor-pane');
        let newW = e.clientX;
        newW = Math.max(150, Math.min(400, newW));
        sidebarPane.style.width = newW + 'px';
    });
    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            elResizeHandleLeft.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    });
}

// Resize handle for editor/results panes
if (elResizeHandle) {
    let isDragging = false;
    elResizeHandle.addEventListener('mousedown', (e) => {
        isDragging = true;
        elResizeHandle.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const resultsPane = document.querySelector('.results-pane');
        const editorPane = document.querySelector('.editor-pane');
        const sidebarPane = document.getElementById('sidebar-files');
        const layout = localStorage.getItem('pll-layout') || 'right';
        
        if (layout === 'bottom') {
            const workspace = document.querySelector('.workspace');
            const totalH = workspace.offsetHeight - elResizeHandle.offsetHeight;
            const workspaceRect = workspace.getBoundingClientRect();
            let resultsH = workspaceRect.bottom - e.clientY;
            resultsH = Math.max(150, Math.min(totalH - 150, resultsH));
            resultsPane.style.height = resultsH + 'px';
            resultsPane.style.width = '100%';
            resultsPane.style.flex = 'none';
            editorPane.style.flex = '1';
        } else {
            const totalW = document.body.clientWidth - sidebarPane.offsetWidth - elResizeHandleLeft.offsetWidth - elResizeHandle.offsetWidth;
            let resultsW = document.body.clientWidth - e.clientX;
            resultsW = Math.max(250, Math.min(totalW - 250, resultsW));
            resultsPane.style.width = resultsW + 'px';
            resultsPane.style.height = '100%';
            resultsPane.style.flex = 'none';
            editorPane.style.flex = '1';
        }
        if (editor) editor.layout();
        if (monacoDiffEditor) monacoDiffEditor.layout();
    });
    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            elResizeHandle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    });
}

// GCA buttons
document.getElementById('btn-gca-init')?.addEventListener('click', gcaInit);
document.getElementById('btn-gca-checkpoint')?.addEventListener('click', gcaCheckpoint);
document.getElementById('btn-gca-handoff')?.addEventListener('click', gcaHandoff);

async function gcaInit() {
    if (!currentProjectId) { addAgenticMessage('system', 'Créez un projet d\'abord.', 'error-msg'); return; }
    const objective = prompt("Objectif:", "Développer...");
    if (!objective) return;
    try {
        const result = await api(`/api/gca/init/${currentProjectId}?objective=${encodeURIComponent(objective)}`, { method: 'POST' });
        gcaSessionId = result.primary_session.id;
        gcaGeneration = 0;
        addAgenticMessage('system', `Cycle GCA initié. Primaire #${result.primary_session.id}, Ombre #${result.shadow_session.id}`);
        await gcaRefreshStatus();
    } catch (e) { addAgenticMessage('system', `Erreur: ${e.message}`); }
}

async function gcaCheckpoint() {
    if (!currentProjectId || !gcaSessionId) return;
    if (activeFile) set_virtual_file(activeFile, getEditorContent());
    try {
        await api('/api/gca/checkpoint', { method: 'POST',
            body: JSON.stringify({
                project_id: currentProjectId, session_id: gcaSessionId,
                key: `cp_gen${gcaGeneration}_${Date.now()}.md`,
                content: `# Gen ${gcaGeneration}\n\n${getEditorContent()}`,
                current_state: `Active: ${activeFile}`,
            }),
        });
        addAgenticMessage('system', 'Checkpoint sauvegardé.');
        await gcaRefreshStatus();
    } catch (e) { addAgenticMessage('system', `Erreur: ${e.message}`); }
}

async function gcaHandoff() {
    if (!currentProjectId) return;
    try {
        const result = await api(`/api/gca/next-generation/${currentProjectId}`, { method: 'POST' });
        gcaGeneration = result.new_primary.generation;
        gcaSessionId = result.new_primary.id;
        addAgenticMessage('system', `Handoff → Génération ${gcaGeneration}`);
        await gcaRefreshStatus();
    } catch (e) { addAgenticMessage('system', `Erreur: ${e.message}`); }
}

setInterval(() => { if (currentProjectId) gcaRefreshStatus(); }, 10000);
setInterval(refreshGitStatus, 15000);

main();
