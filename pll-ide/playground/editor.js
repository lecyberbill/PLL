import { state } from './state.js';
import { api } from './api.js';
import { logToTerminal } from './ui.js';
import { set_virtual_file, get_virtual_file } from './pkg/pll_wasm.js';
import { refreshGitStatus } from './git.js';
import { loadConversations, loadAgenticHistory, loadSessions } from './agent.js';

export function getEditorContent() { return state.editor ? state.editor.getValue() : ''; }
export function setEditorContent(value) { if (state.editor) state.editor.setValue(value || ''); }

export function setEditorLanguage(lang) {
    const elLangBadge = document.getElementById('editor-lang-badge');
    if (state.editor) { 
        state.monaco.editor.setModelLanguage(state.editor.getModel(), lang || 'plaintext'); 
    }
    if (elLangBadge) elLangBadge.textContent = lang || 'plaintext';
}

export function detectLanguage(path) {
    const ext = path.split('.').pop().toLowerCase();
    if (ext === 'py') return 'python';
    if (ext === 'pll') return 'pll';
    if (ext === 'js') return 'javascript';
    if (ext === 'ts') return 'typescript';
    if (ext === 'json') return 'json';
    if (ext === 'md') return 'markdown';
    if (ext === 'css') return 'css';
    if (ext === 'html') return 'html';
    return 'plaintext';
}

export function clearEditor() {
    setEditorContent('');
    state.activeFile = null;
    setEditorLanguage('plaintext');
}

export function clearDefaults() {
    state.filesList = [];
    state.openFiles = [];
    state.activeFile = null;
    clearEditor();
}

export function closeFile(path) {
    const target = path || state.activeFile;
    if (!target) return;
    set_virtual_file(target, getEditorContent());
    const tabIdx = state.openFiles.indexOf(target);
    if (tabIdx === -1) return;
    state.openFiles.splice(tabIdx, 1);
    if (target === state.activeFile) {
        if (state.openFiles.length > 0) {
            const next = state.openFiles[Math.min(tabIdx, state.openFiles.length - 1)];
            state.activeFile = next;
            setEditorContent(get_virtual_file(next));
            setEditorLanguage(detectLanguage(next));
        } else {
            clearEditor();
        }
    }
    renderTabs();
    renderVfsList();
}

export function renderTabs() {
    const elEditorTabsBar = document.getElementById('editor-tabs-bar');
    if (!elEditorTabsBar) return;
    elEditorTabsBar.innerHTML = '';
    if (state.openFiles.length === 0) {
        const empty = document.createElement('span');
        empty.className = 'sys-msg';
        empty.style.cssText = 'padding:4px 8px;font-size:12px;color:var(--text-muted)';
        empty.textContent = state.activeFile || '(aucun)';
        elEditorTabsBar.appendChild(empty);
        return;
    }
    const container = elEditorTabsBar;
    for (const path of state.openFiles) {
        const tab = document.createElement('div');
        tab.className = `editor-tab-item ${path === state.activeFile ? 'active' : ''}`;
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

export function renderVfsList() {
    const elVfsList = document.getElementById('vfs-files-list');
    if (!elVfsList) return;
    
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
    for (const fp of state.filesList) {
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
            name.className = `vfs-item-name ${node.path === state.activeFile ? 'active' : ''}`;
            name.dataset.path = node.path;
            name.onclick = () => loadFileToEditor(node.path);

            const badge = state.gitFileStatus[node.path];
            let badgeText = '';
            let statusClass = '';
            let tooltipText = '';
            let textColor = '';
            
            if (badge) {
                badgeText = badge;
                statusClass = badge === '?' ? 'untracked' : badge === 'D' ? 'deleted' : badge === 'M' ? 'modified' : 'staged';
                tooltipText = badge === '?' ? 'Non suivi' : badge === 'D' ? 'Supprimé' : badge === 'M' ? 'Modifié' : 'Indexé';
                textColor = badge === '?' ? '#2dd4bf' : badge === 'D' ? '#f87171' : badge === 'M' ? '#eab308' : '#22c55e';
            } else if (state.gitAheadFiles.includes(node.path)) {
                badgeText = '↑';
                statusClass = 'ahead';
                tooltipText = 'En attente de push';
                textColor = '#60a5fa';
            } else if (state.currentProjectId) {
                badgeText = '✓';
                statusClass = 'synced';
                tooltipText = 'Synchronisé';
                textColor = '#a5b4fc';
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
            btnRename.onclick = () => renameFile(node.path);
            const btnDelete = document.createElement('button');
            btnDelete.className = 'btn btn-sm btn-danger';
            btnDelete.textContent = '✕';
            btnDelete.onclick = () => deleteFile(node.path);
            actions.appendChild(btnRename);
            actions.appendChild(btnDelete);
            item.appendChild(name);
            item.appendChild(actions);
            container.appendChild(item);
        }
    }
}

export async function loadFileToEditor(path) {
    if (!path) return;
    if (path === 'logic_flow.agent') {
        const navOrch = document.getElementById('nav-item-orchestrator');
        if (navOrch && !navOrch.classList.contains('active')) {
            navOrch.click();
        }
        state.activeFile = path;
        renderTabs();
        return;
    }
    const navVfs = document.getElementById('nav-item-vfs');
    if (navVfs && !navVfs.classList.contains('active')) {
        navVfs.click();
    }
    if (state.activeFile && state.activeFile !== 'logic_flow.agent') {
        set_virtual_file(state.activeFile, getEditorContent());
    }
    if (!state.openFiles.includes(path)) state.openFiles.push(path);
    state.activeFile = path;
    let content = get_virtual_file(path);
    if (content === null || content === undefined) {
        if (state.currentProjectId) {
            try {
                const detail = await api(`/api/projects/${state.currentProjectId}/files/${encodeURIComponent(path)}`);
                content = detail.content || '';
                set_virtual_file(path, content);
            } catch { content = ''; }
        } else { content = ''; }
    }
    if (content !== null && content !== undefined) setEditorContent(content);
    setEditorLanguage(detectLanguage(path));
    renderTabs();
    
    // Update active style in VFS list
    document.querySelectorAll('.vfs-item-name.active').forEach(el => el.classList.remove('active'));
    const activeEl = document.querySelector(`.vfs-item-name[data-path="${CSS.escape(path)}"]`);
    if (activeEl) activeEl.classList.add('active');
}

export async function renameFile(path) {
    const newName = prompt('Nouveau nom :', path);
    if (!newName || newName === path) return;
    const content = get_virtual_file(path);
    set_virtual_file(newName, content);
    const idx = state.filesList.indexOf(path);
    state.filesList.splice(idx, 1, newName);
    const tabIdx = state.openFiles.indexOf(path);
    if (tabIdx !== -1) state.openFiles.splice(tabIdx, 1, newName);
    if (state.activeFile === path) {
        state.activeFile = newName;
        setEditorContent(content);
        setEditorLanguage(detectLanguage(newName));
    }
    renderTabs();
    renderVfsList();
    if (state.currentProjectId) {
        try {
            await api(`/api/projects/${state.currentProjectId}/files/rename?old_path=${encodeURIComponent(path)}&new_path=${encodeURIComponent(newName)}`, { method: 'PUT' });
        } catch (e) {
            logToTerminal(`Erreur renommage: ${e.message}`, 'error-msg');
        }
    }
    logToTerminal(`Renommé: ${path} → ${newName}`, 'sys-msg');
}

export async function deleteFileFromServer(path) {
    if (!state.currentProjectId) return;
    await api(`/api/projects/${state.currentProjectId}/files/${encodeURIComponent(path)}`, { method: 'DELETE' });
}

export function deleteFile(path) {
    if (!confirm(`Supprimer "${path}" ?`)) return;
    const idx = state.filesList.indexOf(path);
    if (idx === -1) return;
    state.filesList.splice(idx, 1);
    if (state.activeFile === path) closeFile(path);
    else renderVfsList();
    deleteFileFromServer(path).catch(e => logToTerminal(`Erreur: ${e.message}`, 'error-msg'));
    logToTerminal(`Supprimé: ${path}`, 'sys-msg');
}

export async function loadProjects() {
    const elProjectSelect = document.getElementById('project-select');
    if (!elProjectSelect) return;
    try {
        const projects = await api('/api/projects');
        elProjectSelect.innerHTML = '<option value="">-- Projet local --</option>';
        if (Array.isArray(projects)) {
            projects.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.name;
                if (p.id === state.currentProjectId) opt.selected = true;
                elProjectSelect.appendChild(opt);
            });
        }
    } catch (e) { console.warn('Server not running:', e.message); }
}

export async function saveProjectToServer() {
    const elBtnSaveProject = document.getElementById('btn-save-project');
    const elBtnSaveFile = document.getElementById('btn-save-file');
    
    if (!state.currentProjectId) {
        const name = prompt('Nom du projet :', 'MonProjet');
        if (!name) return;
        const project = await api('/api/projects', {
            method: 'POST',
            body: JSON.stringify({ name, description: 'Créé depuis le playground' }),
        });
        state.currentProjectId = project.id;
    }
    if (state.activeFile) {
        set_virtual_file(state.activeFile, getEditorContent());
        if (!state.filesList.includes(state.activeFile)) state.filesList.push(state.activeFile);
    }
    for (const p of state.openFiles) {
        const c = get_virtual_file(p);
        if (c !== null && c !== undefined && !state.filesList.includes(p)) state.filesList.push(p);
    }
    for (const path of state.filesList) {
        if (path === '.gitkeep') continue;
        const content = get_virtual_file(path);
        if (content !== null && content !== undefined) {
            await api(`/api/projects/${state.currentProjectId}/files`, {
                method: 'POST', body: JSON.stringify({ path, content }),
            });
        }
    }
    await loadProjects();
    logToTerminal(`Projet sauvegardé (ID: ${state.currentProjectId}).`, 'sys-msg');
    
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

export async function loadProjectFromServer(projectId) {
    const elBtnDeleteProject = document.getElementById('btn-delete-project');
    try {
        state.currentProjectId = projectId;
        clearDefaults();
        const files = await api(`/api/projects/${projectId}/files`);
        state.filesList = [];
        if (Array.isArray(files)) {
            for (const filePath of files) {
                try {
                    const res = await api(`/api/projects/${projectId}/files/${encodeURIComponent(filePath)}`);
                    if (res && res.content !== undefined) {
                        set_virtual_file(filePath, res.content);
                    }
                } catch (err) {
                    console.warn(`Could not load file content for ${filePath}:`, err);
                }
                state.filesList.push(filePath);
            }
        }
        state.openFiles = ['logic_flow.agent'];
        state.activeFile = 'logic_flow.agent';
        clearEditor();
        renderTabs();
        renderVfsList();
        logToTerminal(`Projet chargé (${state.filesList.length} fichiers).`, 'sys-msg');
        localStorage.setItem('pll-last-project', projectId.toString());
        if (elBtnDeleteProject) elBtnDeleteProject.style.display = '';
        const navOrch = document.getElementById('nav-item-orchestrator');
        if (navOrch && !navOrch.classList.contains('active')) {
            navOrch.click();
        }
        await loadProjects();
        refreshGitStatus();
        loadConversations();
        await loadAgenticHistory(projectId);
    } catch (e) {
        console.warn(`Could not load project ${projectId} from database:`, e.message);
        localStorage.removeItem('pll-last-project');
        state.currentProjectId = null;
        clearDefaults();
        if (elBtnDeleteProject) elBtnDeleteProject.style.display = 'none';
        await loadProjects();
    }
}
