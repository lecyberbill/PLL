import { state } from './state.js';
import { api } from './api.js';
import { logToTerminal } from './ui.js';
import { renderVfsList } from './editor.js';

export async function refreshGitStatus() {
    const elGitBranch = document.getElementById('git-branch');
    const elGitChanges = document.getElementById('git-changes');
    const elGitRemote = document.getElementById('git-remote');
    const elGitDebug = document.getElementById('git-debug');

    if (!elGitBranch) return;

    if (!state.currentProjectId) {
        elGitBranch.textContent = '⎇ — (aucun projet)';
        state.gitFileStatus = {};
        if (elGitChanges) elGitChanges.textContent = '';
        if (elGitRemote) elGitRemote.textContent = '';
        if (elGitDebug) elGitDebug.textContent = '';
        return;
    }
    try {
        const st = await api(`/api/git/${state.currentProjectId}/status`);
        if (elGitDebug) elGitDebug.textContent = st ? JSON.stringify(st) : 'no response';
        if (!st || !st.is_repo) {
            state.gitFileStatus = {};
            elGitBranch.textContent = '⎇ — (pas de repo)';
            if (elGitChanges) elGitChanges.textContent = '';
            if (elGitRemote) elGitRemote.textContent = '';
            return;
        }
        elGitBranch.textContent = `⎇ ${st.branch || 'main'}`;
        
        // Build file status map for VFS badges
        state.gitFileStatus = {};
        for (const f of st.staged || []) state.gitFileStatus[f] = 'A';
        for (const f of st.modified || []) state.gitFileStatus[f] = 'M';
        for (const f of st.deleted || []) state.gitFileStatus[f] = 'D';
        for (const f of st.untracked || []) state.gitFileStatus[f] = '?';

        // Populate changed counts
        const changes = [];
        if (st.staged.length) changes.push(`${st.staged.length} staged`);
        if (st.modified.length) changes.push(`${st.modified.length} modified`);
        if (st.untracked.length) changes.push(`${st.untracked.length} untracked`);
        if (st.deleted.length) changes.push(`${st.deleted.length} deleted`);
        
        if (elGitChanges) {
            elGitChanges.textContent = changes.length ? `• ${changes.join(', ')}` : '';
            elGitChanges.className = changes.length ? 'changed' : '';
        }
        
        if (elGitRemote) {
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
        }

        // Populate Git Sidebar Accordion List
        state.gitAheadFiles = st.ahead_files || [];
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
        if (elGitBranch) elGitBranch.textContent = '⎇ — (erreur)';
        if (elGitChanges) elGitChanges.textContent = '';
        if (elGitRemote) elGitRemote.textContent = '';
        if (elGitDebug) elGitDebug.textContent = 'error: ' + e.message;
    }
    renderVfsList();  // Update VFS tree badges
}

export function showGitDiffModal(show) {
    const modal = document.getElementById('git-diff-modal');
    if (modal) {
        if (show) modal.classList.add('open');
        else modal.classList.remove('open');
    }
}

window.openAgentDiffReview = function(path) {
    showGitDiffModal(true);
    setTimeout(() => {
        const dropdown = document.getElementById('diff-files-dropdown');
        if (dropdown) {
            dropdown.value = path;
            dropdown.dispatchEvent(new Event('change'));
        }
    }, 150);
};
