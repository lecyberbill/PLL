import { state } from './state.js';

export function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

export function logToTerminal(msg, className = '') {
    const elTerminalLog = document.getElementById('terminal-log');
    if (!elTerminalLog) return;
    const div = document.createElement('div');
    div.className = className;
    div.textContent = msg;
    elTerminalLog.appendChild(div);
    elTerminalLog.scrollTop = elTerminalLog.scrollHeight;
}

export function logToExecutionLogs(msg, className = '') {
    const elExecutionLogs = document.getElementById('execution-logs');
    if (!elExecutionLogs) return;
    const div = document.createElement('div');
    div.className = className;
    div.textContent = msg;
    elExecutionLogs.appendChild(div);
    elExecutionLogs.scrollTop = elExecutionLogs.scrollHeight;
}

export function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.id === tabId);
    });
}

export function switchSidebarTab(tabId) {
    document.querySelectorAll('.sidebar-tab-btn').forEach(btn => {
        const isActive = (btn.id === `tab-btn-${tabId}`) || (btn.dataset.tab === tabId);
        btn.classList.toggle('active', isActive);
        if (isActive) {
            btn.style.borderBottom = '2px solid var(--accent-color)';
            btn.style.color = 'var(--text-primary)';
        } else {
            btn.style.borderBottom = 'none';
            btn.style.color = 'var(--text-muted)';
        }
    });
    document.querySelectorAll('.sidebar-content-item').forEach(content => {
        const isActive = (content.id === `sidebar-content-${tabId}`);
        content.style.display = isActive ? 'flex' : 'none';
    });
}

export function initResizeHandles(editor, monacoDiffEditor) {
    const elResizeHandleLeft = document.getElementById('resize-handle-left');
    const elResizeHandle = document.getElementById('resize-handle');

    if (elResizeHandleLeft) {
        let isDragging = false;
        elResizeHandleLeft.addEventListener('mousedown', () => {
            isDragging = true;
            elResizeHandleLeft.classList.add('dragging');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });
        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            const sidebarPane = document.getElementById('sidebar-files');
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

    if (elResizeHandle) {
        let isDragging = false;
        elResizeHandle.addEventListener('mousedown', () => {
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
            if (state.editor) state.editor.layout();
            if (state.monacoDiffEditor) state.monacoDiffEditor.layout();
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
}
