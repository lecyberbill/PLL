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
            if (sidebarPane) {
                const rect = sidebarPane.getBoundingClientRect();
                let newW = e.clientX - rect.left;
                newW = Math.max(150, Math.min(450, newW));
                sidebarPane.style.width = newW + 'px';
                if (state.editor) state.editor.layout();
                if (state.monacoDiffEditor) state.monacoDiffEditor.layout();
            }
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
                const totalW = document.body.clientWidth - (sidebarPane ? sidebarPane.offsetWidth : 0) - (elResizeHandleLeft ? elResizeHandleLeft.offsetWidth : 0) - elResizeHandle.offsetWidth;
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

export function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.style.cssText = 'position: fixed; bottom: 32px; right: 24px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; pointer-events: none;';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    const colors = {
        info: 'linear-gradient(135deg, #4f46e5, #6366f1)',
        success: 'linear-gradient(135deg, #059669, #10b981)',
        warning: 'linear-gradient(135deg, #d97706, #f59e0b)',
        error: 'linear-gradient(135deg, #dc2626, #ef4444)'
    };
    const icons = { info: 'ℹ️', success: '✅', warning: '⚠️', error: '❌' };
    toast.style.cssText = `background: ${colors[type] || colors.info}; color: #fff; padding: 8px 16px; border-radius: 8px; font-size: 12px; font-weight: 600; box-shadow: 0 8px 24px rgba(0,0,0,0.4); opacity: 0; transform: translateY(10px); transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1); pointer-events: auto; display: flex; align-items: center; gap: 8px; border: 1px solid rgba(255,255,255,0.2); backdrop-filter: blur(8px);`;
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${escHtml(message)}</span>`;
    container.appendChild(toast);
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    });
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 250);
    }, 3000);
}

export function initCanvasControls() {
    const canvas = document.getElementById('orchestrator-canvas');
    if (!canvas) return;

    let zoom = 1;
    let panX = 0;
    let panY = 0;
    let isPanning = false;
    let isPanMode = false;
    let startX = 0, startY = 0;

    const applyTransform = () => {
        const nodes = canvas.querySelectorAll('.flow-node');
        const svg = canvas.querySelector('.canvas-svg-layer');
        nodes.forEach(node => {
            node.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
            node.style.transformOrigin = '0 0';
        });
        if (svg) {
            svg.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
            svg.style.transformOrigin = '0 0';
        }
    };

    const btnZoomIn = document.getElementById('ctrl-zoom-in');
    const btnZoomOut = document.getElementById('ctrl-zoom-out');
    const btnFit = document.getElementById('ctrl-fit');
    const btnPan = document.getElementById('ctrl-pan');
    const btnAdd = document.getElementById('ctrl-add');

    if (btnZoomIn) {
        btnZoomIn.onclick = () => {
            zoom = Math.min(2.0, zoom + 0.15);
            applyTransform();
            showToast(`Zoom: ${Math.round(zoom * 100)}%`, 'info');
        };
    }
    if (btnZoomOut) {
        btnZoomOut.onclick = () => {
            zoom = Math.max(0.4, zoom - 0.15);
            applyTransform();
            showToast(`Zoom: ${Math.round(zoom * 100)}%`, 'info');
        };
    }
    if (btnFit) {
        btnFit.onclick = () => {
            zoom = 1.0;
            panX = 0;
            panY = 0;
            applyTransform();
            showToast('Vue du canevas réinitialisée', 'info');
        };
    }
    if (btnPan) {
        btnPan.onclick = () => {
            isPanMode = !isPanMode;
            btnPan.classList.toggle('active', isPanMode);
            canvas.style.cursor = isPanMode ? 'grab' : 'default';
            showToast(isPanMode ? 'Mode Navigation activé (Cliquer-glisser)' : 'Mode Sélecteur activé', 'info');
        };
    }
    if (btnAdd) {
        btnAdd.onclick = () => {
            const newNodeId = `node-dyn-${Date.now().toString().slice(-4)}`;
            const newNode = document.createElement('div');
            newNode.className = 'flow-node flow-node-agent';
            newNode.id = newNodeId;
            newNode.style.cssText = `left: ${250 + Math.random() * 80}px; top: ${180 + Math.random() * 80}px; cursor: move;`;
            newNode.innerHTML = `
                <div class="node-header">
                    <span class="node-indicator" style="background:#10b981; box-shadow:0 0 6px #10b981;"></span>
                    <span class="node-title">PLL Exec Node #${newNodeId.slice(-4)}</span>
                    <span class="node-menu">⋮⋮</span>
                </div>
                <div class="node-body">
                    <div class="node-field">
                        <label>Agent PLL</label>
                        <div class="field-val">Probabilistic VM Node</div>
                    </div>
                </div>
                <div class="node-port port-input"></div>
                <div class="node-port port-output"></div>
            `;
            canvas.appendChild(newNode);
            makeNodeDraggable(newNode);
            applyTransform();
            showToast('Nouveau nœud d\'orchestration PLL ajouté au canevas !', 'success');
        };
    }

    canvas.querySelectorAll('.flow-node').forEach(node => makeNodeDraggable(node));

    canvas.addEventListener('mousedown', (e) => {
        if (!isPanMode && e.target !== canvas && e.target.id !== 'canvas-svg') return;
        isPanning = true;
        startX = e.clientX - panX;
        startY = e.clientY - panY;
        if (isPanMode) canvas.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isPanning) return;
        panX = e.clientX - startX;
        panY = e.clientY - startY;
        applyTransform();
    });

    document.addEventListener('mouseup', () => {
        if (isPanning) {
            isPanning = false;
            if (isPanMode) canvas.style.cursor = 'grab';
        }
    });
}

export function makeNodeDraggable(node) {
    let isDrag = false;
    let startX = 0, startY = 0;
    let initialLeft = 0, initialTop = 0;

    const header = node.querySelector('.node-header') || node;
    header.addEventListener('mousedown', (e) => {
        isDrag = true;
        startX = e.clientX;
        startY = e.clientY;
        initialLeft = parseInt(node.style.left) || 0;
        initialTop = parseInt(node.style.top) || 0;
        node.style.zIndex = 1000;
        e.stopPropagation();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDrag) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        node.style.left = `${initialLeft + dx}px`;
        node.style.top = `${initialTop + dy}px`;
    });

    document.addEventListener('mouseup', () => {
        if (isDrag) {
            isDrag = false;
            node.style.zIndex = '';
        }
    });
}

export function initSidebarAccordions() {
    const setupAccordion = (headerId, contentId) => {
        const header = document.getElementById(headerId);
        const content = document.getElementById(contentId);
        if (!header || !content) return;
        const caret = header.querySelector('.sec-caret');

        header.onclick = () => {
            const isHidden = content.style.display === 'none';
            content.style.display = isHidden ? (contentId === 'sec-content-git' ? 'flex' : 'block') : 'none';
            if (caret) {
                caret.style.transform = isHidden ? 'rotate(90deg)' : 'rotate(0deg)';
            }
        };
    };

    setupAccordion('sec-header-explorer', 'sec-content-explorer');
    setupAccordion('sec-header-git', 'sec-content-git');
}

export function togglePanelFullscreen() {
    const resultsPane = document.querySelector('.results-pane');
    if (!resultsPane) return;
    const isExpanded = resultsPane.classList.toggle('expanded-fullscreen');
    if (isExpanded) {
        resultsPane.style.width = '70%';
        showToast('Panneau d\'agent étendu', 'info');
    } else {
        resultsPane.style.width = '450px';
        showToast('Panneau d\'agent réduit', 'info');
    }
    if (state.editor) state.editor.layout();
}
