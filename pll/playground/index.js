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
                if (nameEl) expanded.add(nameEl.textContent);
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
    renderTree(elVfsList, tree, 0, expanded);
}

function renderTree(container, tree, depth, expanded = new Set()) {
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
            const isExpanded = expanded.has(key);
            toggle.textContent = isExpanded ? '▾' : '▸';
            toggle.style.cursor = 'pointer';
            toggle.style.marginRight = '4px';
            item.appendChild(toggle);
            const name = document.createElement('span');
            name.className = 'vfs-item-name';
            name.textContent = `${isExpanded ? '📂' : '📁'} ${key}`;
            item.appendChild(name);
            const childContainer = document.createElement('div');
            childContainer.style.display = isExpanded ? '' : 'none';
            renderTree(childContainer, node.children, depth + 1, expanded);
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
            const badge = gitFileStatus[node.path];
            if (badge) {
                const badgeEl = document.createElement('span');
                badgeEl.className = `vfs-git-badge ${badge === '?' ? 'untracked' : badge === 'D' ? 'deleted' : badge === 'M' ? 'modified' : 'staged'}`;
                badgeEl.textContent = badge;
                name.prepend(badgeEl);
            }
            name.appendChild(document.createTextNode(`📄 ${key}`));
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
    openFiles = [];  // Don't open files by default — user clicks to open
    activeFile = null;
    clearEditor();
    renderTabs();
    renderVfsList();
    logToTerminal(`Projet chargé (${filesList.length} fichiers).`, 'sys-msg');
    localStorage.setItem('pll-last-project', projectId.toString());
    elBtnDeleteProject.style.display = '';
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
        sessions.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = `Session #${s.id} (${s.status}) - ${new Date(s.created_at).toLocaleTimeString('fr-FR')}`;
            if (s.status === 'active') opt.selected = true;
            elSettingsSessionSelect.appendChild(opt);
        });
    } catch (e) {
        console.warn('Error loading sessions:', e.message);
    }
}

async function selectSession(sessionId) {
    if (!sessionId) return;
    try {
        const msgs = await api(`/api/agentic/sessions/${sessionId}/conversations`);
        elAgenticConversation.innerHTML = '';
        if (!msgs || msgs.length === 0) {
            elAgenticConversation.innerHTML = '<div class="sys-msg">Aucun message dans cette session.</div>';
            return;
        }
        for (const m of msgs) {
            addAgenticMessage(m.role, m.content);
        }
    } catch (e) {
        logToTerminal(`Erreur lors du chargement de la session: ${e.message}`, 'error-msg');
    }
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
        elGitDebug.textContent = '';
        return;
    }
    try {
        const st = await api(`/api/git/${currentProjectId}/status`);
        elGitDebug.textContent = st ? JSON.stringify(st) : 'no response';
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
    } catch (e) {
        elGitBranch.textContent = '⎇ — (erreur)';
        elGitChanges.textContent = '';
        elGitRemote.textContent = '';
        elGitDebug.textContent = 'error: ' + e.message;
    }
    renderVfsList();  // Update git badges in VFS tree
}

async function loadConversations() {
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
        let stepsHtml = '';
        let answer = '';
        let finalCode = '';
        let finalPath = '';
        let subtaskResults = [];
        let thinkingDots = 0;
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
                        } else if (ev.type === 'step') {
                            const icons = { read_file: '📖', write_file: '✏️', glob_files: '🔍', grep_files: '🔍', list_dir: '📂', exec_shell: '💻', git_status: '⎇', git_commit: '📝', git_init: '🔧', web_fetch: '🌐', web_search: '🔎', probe_path: '🔎', final_answer: '✅' };
                            const icon = icons[ev.tool] || '➡️';
                            let labelLine = `${icon} **${ev.tool}**`;
                            if (ev.result) {
                                if (ev.result.startsWith('ERROR')) {
                                    labelLine += ` ⚠️ ${ev.result.slice(0, 200)}`;
                                } else {
                                    labelLine += `\n\`\`\`\n${ev.result.slice(0, 800)}\n\`\`\``;
                                }
                            }
                            stepsHtml += labelLine + '\n';
                        } else if (ev.type === 'explanation') {
                            placeholder.textContent = `🤖 ${ev.text.slice(0, 120)}`;
                        } else if (ev.type === 'code') {
                            finalCode = ev.code;
                            finalPath = ev.file_path;
                        } else if (ev.type === 'subtask') {
                            subtaskResults.push(`📋 ${ev.subtask}`);
                            stepsHtml += `📋 **${ev.subtask}**\n`;
                        } else if (ev.type === 'done') {
                            answer = ev.answer;
                        }
                    } catch (e) { /* skip malformed events */ }
                }
            }
        }

        clearInterval(thinkingTimer);
        placeholder.remove();

        if (finalCode && finalPath) {
            if (!filesList.includes(finalPath)) filesList.push(finalPath);
            addAgenticMessage('assistant', `${stepsHtml}\n\n✅ **Terminé** — fichiers créés. Consulte l'onglet Fichiers.`);
            if (currentProjectId) await loadProjectFromServer(currentProjectId);
        } else if (answer) {
            addAgenticMessage('assistant', stepsHtml ? `${stepsHtml}\n\n${answer}` : answer);
            if (currentProjectId) await loadProjectFromServer(currentProjectId);
        } else {
            addAgenticMessage('assistant', stepsHtml || '✅ Terminé.');
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

async function main() {
    try {
        const gcaEnabled = localStorage.getItem('pll-enable-gca') === 'true';
        if (elSettingsEnableGca) elSettingsEnableGca.checked = gcaEnabled;
        updateGcaTabVisibility(gcaEnabled);
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
                await loadProjectFromServer(currentProjectId);
            }
        }
        if (!currentProjectId) {
            logToTerminal('Bienvenue ! Crée ou sélectionne un projet pour commencer.', 'sys-msg');
        }
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
                `<div class="vault-entry"><strong>${e.key}</strong> <span class="sys-msg">(${new Date(e.created_at).toLocaleString()})</span><pre>${e.content.slice(0, 200)}</pre><button class="btn btn-sm btn-secondary publish-pkg-btn" data-key="${escHtml(e.key)}" title="Publier comme paquet PLL">📦 Publier</button></div>`
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
        elPackagesList.innerHTML = pkgs.length === 0
            ? '<div class="sys-msg">Aucun paquet.</div>'
            : pkgs.map(p => `<div class="package-item"><strong>${p.name}</strong> v${p.version} <span class="sys-msg">par ${p.author || '?'}</span> <button class="btn btn-sm btn-secondary view-pkg-btn" data-name="${p.name}" title="Voir le code source">📄</button></div>`).join('');
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
        elPackagesList.innerHTML = '<div class="sys-msg">Serveur indisponible.</div>';
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
    });
}

async function runPllCode() {
    const code = editor.getValue();
    if (!code) {
        logToTerminal("Erreur : Aucun code à exécuter.", "stderr");
        return;
    }
    switchTab('tab-terminal');
    logToTerminal(`❯ pll run ${activeFile || 'main.pll'}`, "cmd");
    try {
        const resp = await fetch('/api/pll/exec', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const result = await resp.json();
        if (result.output) {
            logToTerminal(result.output, "stdout");
        }
        if (result.error) {
            logToTerminal(result.error, "stderr");
        }
        logToTerminal(`Process finished: ${result.ok ? 'SUCCESS' : 'FAILED'}`, result.ok ? 'exit-ok' : 'exit-err');
    } catch (e) {
        logToTerminal(`Erreur lors de l'exécution: ${e.message}`, "stderr");
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

elAgenticSend.addEventListener('click', sendAgenticMessage);
elAgenticInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgenticMessage(); }
});
elAgenticClear.addEventListener('click', () => {
    elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
    agenticConversationHistory = [];
});

elBtnRefreshPackages.addEventListener('click', refreshPackages);

// Git status bar debug (click to toggle)
document.getElementById('git-status-bar').addEventListener('click', () => {
    elGitDebug.style.display = elGitDebug.style.display === 'none' ? 'inline' : 'none';
});

// Load conversations on tab switch
const origSwitchTab = switchTab;
switchTab = function(tabId) {
    origSwitchTab(tabId);
    if (tabId === 'tab-conversations') loadConversations();
};

elBtnRefreshConv.addEventListener('click', loadConversations);

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const tab = document.querySelector(`[data-tab="${tabId}"]`);
    if (tab) tab.classList.add('active');
    const content = document.getElementById(tabId);
    if (content) content.classList.add('active');
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
        const totalW = document.body.clientWidth - sidebarPane.offsetWidth - elResizeHandleLeft.offsetWidth - elResizeHandle.offsetWidth;
        let resultsW = document.body.clientWidth - e.clientX;
        resultsW = Math.max(250, Math.min(totalW - 250, resultsW));
        resultsPane.style.width = resultsW + 'px';
        resultsPane.style.flex = 'none';
        editorPane.style.flex = '1';
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
