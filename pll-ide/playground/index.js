import { state } from './state.js';
import { api } from './api.js';
import { escHtml, logToTerminal, logToExecutionLogs, switchTab, switchSidebarTab, initResizeHandles } from './ui.js';
import { loadMonaco, detectLanguage } from './editor-setup.js';
import { set_virtual_file, get_virtual_file } from './pkg/pll_wasm.js';
import {
    getEditorContent,
    setEditorContent,
    setEditorLanguage,
    clearEditor,
    clearDefaults,
    closeFile,
    renderTabs,
    renderVfsList,
    loadFileToEditor,
    renameFile,
    deleteFile,
    loadProjects,
    saveProjectToServer,
    loadProjectFromServer
} from './editor.js';
import { refreshGitStatus, showGitDiffModal } from './git.js';
import {
    addAgenticMessage,
    ensureProjectForAgentic,
    selectSession,
    startNewSession,
    loadConversations,
    loadAgenticHistory,
    loadSessions,
    runReActLoopClient,
    closeNodeDetailsDrawer,
    saveConversationMessage
} from './agent.js';

// DOM Element bindings
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
const elAgenticInput = document.getElementById('agentic-input');
const elAgenticSend = document.getElementById('btn-agentic-send');
const elAgenticClear = document.getElementById('btn-agentic-clear');
const elAgenticConversation = document.getElementById('agentic-conversation');
const elSettingsBackend = document.getElementById('settings-backend');
const elAgenticSessionSelect = document.getElementById('agentic-session-select');
const elSettingsSessionSelect = document.getElementById('settings-session-select');
const elBtnRunCode = document.getElementById('btn-run-code');
const elBtnSaveFile = document.getElementById('btn-save-file');
const elBtnGcaClear = document.getElementById('btn-gca-clear');

// Main loop trigger
async function sendAgenticMessage() {
    const msg = elAgenticInput.value.trim();
    if (!msg) return;
    if (!await ensureProjectForAgentic()) return;
    
    elAgenticInput.value = '';
    addAgenticMessage('user', msg);
    await saveConversationMessage('user', msg);
    
    const backend = elSettingsBackend.value;

    const placeholder = addAgenticMessage('system', '🤖 Agent en cours...');
    placeholder.style.opacity = '0.6';

    try {
        await runReActLoopClient(msg, backend, placeholder);
    } catch (e) {
        placeholder.textContent = `⚠️ Erreur : ${e.message}`;
    }
}

// Compile & Exec code
async function runPllCode() {
    const code = getEditorContent();
    if (!code) {
        logToExecutionLogs("Erreur : Aucun code à exécuter.", "stderr");
        return;
    }
    switchTab('tab-logs');
    logToExecutionLogs(`❯ pll run ${state.activeFile || 'main.pll'}`, "cmd");
    try {
        const result = await api('/api/pll/exec', {
            method: 'POST',
            body: JSON.stringify({ code })
        });
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

// Global initialization
async function main() {
    // 1. Monaco setup
    try {
        const monacoInstance = await loadMonaco();
        state.monaco = monacoInstance;
        state.editor = monacoInstance.editor.create(elEditorContainer, {
            value: '', language: 'python', theme: 'pll-dark',
            fontSize: 14, fontFamily: "'Fira Code', monospace",
            minimap: { enabled: false }, lineNumbers: 'on',
            automaticLayout: true, tabSize: 4, insertSpaces: true,
            bracketPairColorization: { enabled: true },
            renderLineHighlight: 'line', cursorBlinking: 'smooth',
        });
        state.editor.onDidChangeModelContent(() => {
            if (state.activeFile) set_virtual_file(state.activeFile, state.editor.getValue());
        });
        state.editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyS, (e) => {
            saveProjectToServer();
        });
    } catch (monacoErr) {
        console.error("Monaco load blocked or failed:", monacoErr);
    }
    
    // Bind resize handler
    initResizeHandles();
    
    // Set default file
    state.activeFile = 'logic_flow.agent';
    set_virtual_file('logic_flow.agent', '');
    loadFileToEditor('logic_flow.agent');
    
    // 2. Load projects
    await loadProjects();
    
    // Load last project if saved in cache
    const last = localStorage.getItem('pll-last-project');
    if (last) {
        loadProjectFromServer(parseInt(last));
    }
}

// Event Bindings
if (elBtnRunCode) elBtnRunCode.onclick = runPllCode;
if (elBtnSaveFile) elBtnSaveFile.onclick = saveProjectToServer;

if (elProjectSelect) {
    elProjectSelect.onchange = async () => {
        const val = elProjectSelect.value;
        if (val) await loadProjectFromServer(parseInt(val));
        else clearDefaults();
    };
}

if (elBtnNewProject) {
    elBtnNewProject.onclick = () => {
        elProjectModalTitle.textContent = "Nouveau Projet";
        elModalProjectName.value = "";
        elModalProjectDesc.value = "";
        elModalProjectPath.value = "";
        elProjectModal.classList.add('open');
    };
}

if (elProjectModalCancel) {
    elProjectModalCancel.onclick = () => elProjectModal.classList.remove('open');
}

if (elProjectModalSave) {
    elProjectModalSave.onclick = async () => {
        const name = elModalProjectName.value.trim();
        const desc = elModalProjectDesc.value.trim();
        const ppath = elModalProjectPath.value.trim();
        if (!name) return;
        try {
            const p = await api('/api/projects', {
                method: 'POST',
                body: JSON.stringify({ name, description: desc, disk_path: ppath })
            });
            elProjectModal.classList.remove('open');
            await loadProjectFromServer(p.id);
        } catch (e) {
            alert("Erreur lors de la création : " + e.message);
        }
    };
}

if (elBtnDeleteProject) {
    elBtnDeleteProject.onclick = async () => {
        if (!state.currentProjectId) return;
        if (!confirm("Voulez-vous supprimer ce projet ?\n(Les fichiers sur disque ne seront pas effacés)")) return;
        try {
            await api(`/api/projects/${state.currentProjectId}?keep_files=true`, { method: 'DELETE' });
            clearDefaults();
            state.currentProjectId = null;
            if (elBtnDeleteProject) elBtnDeleteProject.style.display = 'none';
            localStorage.removeItem('pll-last-project');
            await loadProjects();
        } catch (e) {
            alert("Erreur : " + e.message);
        }
    };
}

if (elBtnAddFile) {
    elBtnAddFile.onclick = () => {
        elModalFilePath.value = "";
        elModalFileContent.value = "";
        elVfsModal.classList.add('open');
    };
}

if (elModalCancel) {
    elModalCancel.onclick = () => elVfsModal.classList.remove('open');
}

if (elModalSave) {
    elModalSave.onclick = async () => {
        const path = elModalFilePath.value.trim();
        const content = elModalFileContent.value;
        if (!path) return;
        set_virtual_file(path, content);
        if (!state.filesList.includes(path)) state.filesList.push(path);
        elVfsModal.classList.remove('open');
        renderVfsList();
        await loadFileToEditor(path);
        if (state.currentProjectId) {
            try {
                await api(`/api/projects/${state.currentProjectId}/files`, {
                    method: 'POST',
                    body: JSON.stringify({ path, content })
                });
            } catch (e) {
                logToTerminal(`Erreur synchro fichier: ${e.message}`, 'error-msg');
            }
        }
    };
}

// Tabs
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => switchTab(btn.dataset.tab);
});

document.querySelectorAll('.sidebar-tab-btn').forEach(btn => {
    const tabId = btn.id.replace('tab-btn-', '');
    btn.onclick = () => switchSidebarTab(tabId);
});

// Left Navigation Items
const navItems = ['nav-item-vfs', 'nav-item-orchestrator', 'nav-item-db', 'nav-item-settings', 'nav-item-profile', 'nav-item-global-settings'];
navItems.forEach(id => {
    document.getElementById(id)?.addEventListener('click', () => {
        const sidebar = document.getElementById('sidebar-files');
        const canvas = document.getElementById('orchestrator-canvas');
        const editorView = document.querySelector('.editor-container');
        
        if (id === 'nav-item-settings' || id === 'nav-item-global-settings') {
            document.getElementById('settings-modal')?.classList.add('open');
            return;
        }

        navItems.forEach(n => {
            if (n !== 'nav-item-settings' && n !== 'nav-item-global-settings') {
                document.getElementById(n)?.classList.remove('active');
            }
        });
        document.getElementById(id)?.classList.add('active');

        if (id === 'nav-item-vfs') {
            if (sidebar) sidebar.style.display = 'flex';
            if (canvas) canvas.style.display = 'none';
            if (editorView) editorView.style.display = 'block';
            switchSidebarTab('vfs');
        } else if (id === 'nav-item-orchestrator') {
            if (sidebar) sidebar.style.display = 'none';
            if (canvas) canvas.style.display = 'block';
            if (editorView) editorView.style.display = 'none';
        } else if (id === 'nav-item-db') {
            if (sidebar) sidebar.style.display = 'flex';
            if (canvas) canvas.style.display = 'none';
            if (editorView) editorView.style.display = 'none';
            switchSidebarTab('packages');
        } else if (id === 'nav-item-profile') {
            if (sidebar) sidebar.style.display = 'flex';
            if (canvas) canvas.style.display = 'none';
            if (editorView) editorView.style.display = 'none';
            switchSidebarTab('sessions');
        }
        if (state.editor) state.editor.layout();
    });
});

// Settings Modal
const elBtnSettings = document.getElementById('btn-settings');
const elSettingsModal = document.getElementById('settings-modal');
const elBtnSettingsClose = document.getElementById('btn-settings-close');

if (elBtnSettings) {
    elBtnSettings.onclick = () => {
        if (elSettingsModal) elSettingsModal.classList.add('open');
    };
}
if (elBtnSettingsClose) {
    elBtnSettingsClose.onclick = () => {
        if (elSettingsModal) elSettingsModal.classList.remove('open');
    };
}

// Agent interaction bindings
if (elAgenticSend) elAgenticSend.onclick = sendAgenticMessage;
if (elAgenticInput) {
    elAgenticInput.onkeydown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendAgenticMessage();
        }
    };
}
if (elAgenticClear) elAgenticClear.onclick = startNewSession;
if (elBtnGcaClear) elBtnGcaClear.onclick = startNewSession;

if (elAgenticSessionSelect) {
    elAgenticSessionSelect.onchange = () => {
        const val = elAgenticSessionSelect.value;
        if (val) selectSession(parseInt(val));
    };
}
if (elSettingsSessionSelect) {
    elSettingsSessionSelect.onchange = () => {
        const val = elSettingsSessionSelect.value;
        if (val) selectSession(parseInt(val));
    };
}

// Drawer closing bindings
const elDrawerClose = document.getElementById('btn-close-drawer');
if (elDrawerClose) elDrawerClose.onclick = closeNodeDetailsDrawer;

// Git events bindings
const elBtnCommitSidebar = document.getElementById('git-btn-commit-sidebar');
const elCommitMessageSidebar = document.getElementById('git-commit-msg-sidebar');
if (elBtnCommitSidebar && elCommitMessageSidebar) {
    elBtnCommitSidebar.onclick = async () => {
        if (!state.currentProjectId) return;
        const msg = elCommitMessageSidebar.value.trim();
        if (!msg) { alert("Message de commit requis"); return; }
        try {
            await api(`/api/git/${state.currentProjectId}/commit`, {
                method: 'POST',
                body: JSON.stringify({ message: msg })
            });
            elCommitMessageSidebar.value = '';
            logToTerminal(`Commit réussi: "${msg}"`, 'sys-msg');
            await refreshGitStatus();
        } catch (e) {
            logToTerminal(`Erreur commit: ${e.message}`, 'error-msg');
        }
    };
}

const elBtnGitInit = document.getElementById('git-btn-init');
if (elBtnGitInit) {
    elBtnGitInit.onclick = async () => {
        if (!state.currentProjectId) return;
        try {
            await api(`/api/git/${state.currentProjectId}/init`, { method: 'POST' });
            logToTerminal("Dépôt Git initialisé.", "sys-msg");
            await refreshGitStatus();
        } catch (e) {
            logToTerminal(`Erreur Git init: ${e.message}`, 'error-msg');
        }
    };
}

const elBtnGitPush = document.getElementById('git-btn-push');
if (elBtnGitPush) {
    elBtnGitPush.onclick = async () => {
        if (!state.currentProjectId) return;
        try {
            logToTerminal("Push en cours...", "sys-msg");
            await api(`/api/git/${state.currentProjectId}/push`, { method: 'POST' });
            logToTerminal("Push terminé avec succès.", "sys-msg");
            await refreshGitStatus();
        } catch (e) {
            logToTerminal(`Erreur Git push: ${e.message}`, 'error-msg');
        }
    };
}

const elBtnGitPull = document.getElementById('git-btn-pull');
if (elBtnGitPull) {
    elBtnGitPull.onclick = async () => {
        if (!state.currentProjectId) return;
        try {
            logToTerminal("Pull en cours...", "sys-msg");
            await api(`/api/git/${state.currentProjectId}/pull`, { method: 'POST' });
            logToTerminal("Pull terminé avec succès.", "sys-msg");
            await refreshGitStatus();
        } catch (e) {
            logToTerminal(`Erreur Git pull: ${e.message}`, 'error-msg');
        }
    };
}

// Launch the IDE app
document.addEventListener('DOMContentLoaded', main);
