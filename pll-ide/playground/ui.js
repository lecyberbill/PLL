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
    const cleanId = tabId.replace(/^tab-btn-|^sidebar-content-/, '');
    document.querySelectorAll('.sidebar-tab-btn').forEach(btn => {
        const btnClean = btn.id.replace(/^tab-btn-/, '');
        const isActive = (btnClean === cleanId) || (btn.dataset.tab === cleanId);
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
        const contentClean = content.id.replace(/^sidebar-content-/, '');
        const isActive = (contentClean === cleanId);
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

    loadCanvasState();

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
        renderCanvasConnections();
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

    // Interactive cable wiring logic
    let isWiring = false;
    let wiringFromNodeId = null;
    let tempWirePath = null;

    canvas.addEventListener('mousedown', (e) => {
        const portOut = e.target.closest('.port-output');
        if (portOut) {
            const node = portOut.closest('.flow-node');
            if (node) {
                isWiring = true;
                wiringFromNodeId = node.id;
                const svg = document.getElementById('canvas-svg');
                if (svg) {
                    tempWirePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    tempWirePath.setAttribute('stroke', '#10b981');
                    tempWirePath.setAttribute('stroke-width', '2.5');
                    tempWirePath.setAttribute('stroke-dasharray', '5 5');
                    tempWirePath.setAttribute('fill', 'none');
                    svg.appendChild(tempWirePath);
                }
                e.stopPropagation();
                return;
            }
        }

        if (!isPanMode && e.target !== canvas && e.target.id !== 'canvas-svg') return;
        isPanning = true;
        startX = e.clientX - panX;
        startY = e.clientY - panY;
        if (isPanMode) canvas.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
        if (isWiring && tempWirePath && wiringFromNodeId) {
            const fromEl = document.getElementById(wiringFromNodeId);
            if (fromEl) {
                const fromPort = fromEl.querySelector('.port-output') || fromEl;
                const canvasRect = canvas.getBoundingClientRect();
                const fromRect = fromPort.getBoundingClientRect();
                const x1 = fromRect.left + fromRect.width / 2 - canvasRect.left;
                const y1 = fromRect.top + fromRect.height / 2 - canvasRect.top;
                const x2 = e.clientX - canvasRect.left;
                const y2 = e.clientY - canvasRect.top;
                const dx = Math.max(30, Math.abs(x2 - x1) * 0.5);
                tempWirePath.setAttribute('d', `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`);
            }
            return;
        }

        if (!isPanning) return;
        panX = e.clientX - startX;
        panY = e.clientY - startY;
        applyTransform();
    });

    document.addEventListener('mouseup', (e) => {
        if (isWiring) {
            isWiring = false;
            if (tempWirePath) {
                tempWirePath.remove();
                tempWirePath = null;
            }
            const portIn = e.target.closest('.port-input');
            if (portIn) {
                const toNode = portIn.closest('.flow-node');
                if (toNode && wiringFromNodeId && toNode.id !== wiringFromNodeId) {
                    connectNodes(wiringFromNodeId, toNode.id);
                }
            }
            wiringFromNodeId = null;
            return;
        }

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

    // Add delete button if not present
    const header = node.querySelector('.node-header') || node;
    if (!node.querySelector('.node-delete-btn') && node.id !== 'node-trigger') {
        const delBtn = document.createElement('span');
        delBtn.className = 'node-delete-btn';
        delBtn.textContent = '✕';
        delBtn.style.cssText = 'margin-left: auto; cursor: pointer; color: var(--text-muted); font-size: 11px; padding: 0 4px; transition: color 0.15s;';
        delBtn.title = 'Supprimer le nœud';
        delBtn.onmouseover = () => delBtn.style.color = '#ef4444';
        delBtn.onmouseout = () => delBtn.style.color = 'var(--text-muted)';
        delBtn.onclick = (e) => {
            e.stopPropagation();
            removeNodeConnections(node.id);
            node.remove();
            saveCanvasState();
            renderCanvasConnections();
            showToast('Nœud supprimé du canevas', 'info');
        };
        header.appendChild(delBtn);
    }

    header.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('node-delete-btn')) return;
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
        renderCanvasConnections();
    });

    document.addEventListener('mouseup', () => {
        if (isDrag) {
            isDrag = false;
            node.style.zIndex = '';
            saveCanvasState();
            renderCanvasConnections();
        }
    });
}

export function connectNodes(fromId, toId) {
    const projId = state.currentProjectId || 'default';
    const raw = localStorage.getItem(`pll-canvas-links-${projId}`);
    let links = [];
    if (raw) {
        try { links = JSON.parse(raw); } catch (e) {}
    }
    if (!links.some(l => l.from === fromId && l.to === toId)) {
        links.push({ from: fromId, to: toId });
        localStorage.setItem(`pll-canvas-links-${projId}`, JSON.stringify(links));
        renderCanvasConnections();
        showToast('Nœuds reliés avec succès', 'success');
    }
}

export function removeNodeConnections(nodeId) {
    const projId = state.currentProjectId || 'default';
    const raw = localStorage.getItem(`pll-canvas-links-${projId}`);
    if (!raw) return;
    try {
        let links = JSON.parse(raw);
        links = links.filter(l => l.from !== nodeId && l.to !== nodeId);
        localStorage.setItem(`pll-canvas-links-${projId}`, JSON.stringify(links));
    } catch (e) {}
}

export function renderCanvasConnections() {
    const svg = document.getElementById('canvas-svg');
    const canvas = document.getElementById('orchestrator-canvas');
    if (!svg || !canvas) return;
    svg.innerHTML = '';

    const projId = state.currentProjectId || 'default';
    const rawLinks = localStorage.getItem(`pll-canvas-links-${projId}`);
    
    // Default connection if no links saved yet
    let links = [
        { from: 'node-trigger', to: 'node-agent' }
    ];
    if (rawLinks) {
        try {
            const parsed = JSON.parse(rawLinks);
            if (Array.isArray(parsed) && parsed.length > 0) links = parsed;
        } catch (e) {}
    }

    const canvasRect = canvas.getBoundingClientRect();

    links.forEach(link => {
        const fromEl = document.getElementById(link.from);
        const toEl = document.getElementById(link.to);
        if (!fromEl || !toEl) return;

        const fromPort = fromEl.querySelector('.port-output') || fromEl;
        const toPort = toEl.querySelector('.port-input') || toEl;

        const fromRect = fromPort.getBoundingClientRect();
        const toRect = toPort.getBoundingClientRect();

        const x1 = fromRect.left + fromRect.width / 2 - canvasRect.left;
        const y1 = fromRect.top + fromRect.height / 2 - canvasRect.top;
        const x2 = toRect.left + toRect.width / 2 - canvasRect.left;
        const y2 = toRect.top + toRect.height / 2 - canvasRect.top;

        const dx = Math.max(30, Math.abs(x2 - x1) * 0.5);
        const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', d);
        path.setAttribute('stroke', 'var(--accent-color)');
        path.setAttribute('stroke-width', '2.5');
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke-linecap', 'round');
        svg.appendChild(path);
    });
}

export function saveCanvasState() {
    const canvas = document.getElementById('orchestrator-canvas');
    if (!canvas) return;
    const projId = state.currentProjectId || 'default';
    const nodes = [];
    canvas.querySelectorAll('.flow-node').forEach(node => {
        const id = node.id;
        const left = node.style.left;
        const top = node.style.top;
        const title = node.querySelector('.node-title')?.textContent || '';
        const fieldVal = node.querySelector('.field-val')?.textContent || '';
        const nodeTypeLabel = node.querySelector('.node-field label')?.textContent || '';
        const isDefault = (id === 'node-trigger' || id === 'node-agent');
        nodes.push({ id, left, top, title, fieldVal, nodeTypeLabel, isDefault, className: node.className });
    });
    localStorage.setItem(`pll-canvas-nodes-${projId}`, JSON.stringify(nodes));
}

export function loadCanvasState() {
    const canvas = document.getElementById('orchestrator-canvas');
    if (!canvas) return;
    const projId = state.currentProjectId || 'default';
    const raw = localStorage.getItem(`pll-canvas-nodes-${projId}`);
    if (!raw) return;
    try {
        const nodes = JSON.parse(raw);
        if (!Array.isArray(nodes) || nodes.length === 0) return;
        
        canvas.querySelectorAll('.flow-node').forEach(node => {
            if (node.id !== 'node-trigger' && node.id !== 'node-agent') {
                node.remove();
            }
        });

        nodes.forEach(n => {
            if (n.isDefault) {
                const el = document.getElementById(n.id);
                if (el) {
                    if (n.left) el.style.left = n.left;
                    if (n.top) el.style.top = n.top;
                }
            } else {
                const newNode = document.createElement('div');
                newNode.className = n.className || 'flow-node flow-node-agent';
                newNode.id = n.id;
                newNode.style.cssText = `left: ${n.left || '200px'}; top: ${n.top || '150px'}; cursor: move;`;
                newNode.innerHTML = `
                    <div class="node-header">
                        <span class="node-indicator" style="background:#6366f1; box-shadow:0 0 6px #6366f1;"></span>
                        <span class="node-title">${escHtml(n.title)}</span>
                        <span class="node-menu">⋮⋮</span>
                    </div>
                    <div class="node-body">
                        <div class="node-field">
                            <label>${escHtml(n.nodeTypeLabel || 'Agent')}</label>
                            <div class="field-val">${escHtml(n.fieldVal || '')}</div>
                        </div>
                    </div>
                    <div class="node-port port-input"></div>
                    <div class="node-port port-output"></div>
                `;
                canvas.appendChild(newNode);
                makeNodeDraggable(newNode);
            }
        });
    } catch (e) {
        console.error("Failed to restore canvas nodes state:", e);
    }
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

export function performGlobalSearch() {
    const input = document.getElementById('global-search-input');
    const resultsContainer = document.getElementById('global-search-results');
    if (!input || !resultsContainer) return;
    const query = input.value.trim().toLowerCase();
    if (!query) {
        resultsContainer.innerHTML = '<div class="sys-msg" style="font-size: 11px; color: var(--text-muted); padding: 8px;">Entrez une expression pour rechercher.</div>';
        return;
    }

    resultsContainer.innerHTML = '<div class="sys-msg" style="font-size: 11px; color: var(--accent-color); padding: 8px;">Recherche en cours...</div>';

    let matches = [];
    const files = state.filesList || [];
    files.forEach(file => {
        const content = get_virtual_file(file.path) || file.content || '';
        const lines = content.split('\n');
        lines.forEach((line, idx) => {
            if (line.toLowerCase().includes(query)) {
                matches.push({ path: file.path, lineNum: idx + 1, lineContent: line.trim() });
            }
        });
    });

    if (matches.length === 0) {
        resultsContainer.innerHTML = `<div class="sys-msg" style="font-size: 11px; color: var(--text-muted); padding: 8px;">Aucun résultat pour "${escHtml(query)}".</div>`;
        return;
    }

    resultsContainer.innerHTML = '';
    matches.forEach(m => {
        const item = document.createElement('div');
        item.style.cssText = 'padding: 6px 8px; background: rgba(255,255,255,0.03); border-radius: var(--radius-sm); border-left: 2px solid var(--accent-color); cursor: pointer; font-size: 11px; margin-bottom: 4px; transition: background 0.15s;';
        item.onmouseover = () => item.style.background = 'rgba(99, 102, 241, 0.1)';
        item.onmouseout = () => item.style.background = 'rgba(255,255,255,0.03)';
        item.innerHTML = `
            <div style="font-weight: bold; color: var(--accent-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escHtml(m.path)} : Ligne ${m.lineNum}</div>
            <div style="color: var(--text-muted); font-family: var(--font-mono); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 2px;">${escHtml(m.lineContent)}</div>
        `;
        item.onclick = async () => {
            if (window.loadFileToEditor) await window.loadFileToEditor(m.path);
            if (state.editor) {
                state.editor.revealLineInCenter(m.lineNum);
                state.editor.setPosition({ lineNumber: m.lineNum, column: 1 });
                state.editor.focus();
            }
        };
        resultsContainer.appendChild(item);
    });
}

export function highlightExecutingNode(nodeId, isExecuting) {
    const el = document.getElementById(nodeId);
    if (!el) return;
    const indicator = el.querySelector('.node-indicator');
    if (indicator) {
        indicator.classList.toggle('glowing', isExecuting);
    }
}
