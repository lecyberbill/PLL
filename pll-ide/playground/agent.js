import { state } from './state.js';
import { api } from './api.js';
import { logToTerminal, escHtml } from './ui.js';
import { loadProjectFromServer, renderVfsList } from './editor.js';
import { set_virtual_file, get_virtual_file } from './pkg/pll_wasm.js';

export function addAgenticMessage(role, content) {
    const elAgenticConversation = document.getElementById('agentic-conversation');
    if (!elAgenticConversation) return null;
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

export async function ensureProjectForAgentic() {
    if (state.currentProjectId) return true;
    addAgenticMessage('system', '❌ Sélectionne ou crée un projet d\'abord (menu en haut à gauche).');
    return false;
}

export async function selectSession(sessionId) {
    const elAgenticConversation = document.getElementById('agentic-conversation');
    const elAgenticSessionSelect = document.getElementById('agentic-session-select');
    const elSettingsSessionSelect = document.getElementById('settings-session-select');
    
    if (!elAgenticConversation) return;
    try {
        if (elAgenticSessionSelect) elAgenticSessionSelect.value = sessionId;
        if (elSettingsSessionSelect) elSettingsSessionSelect.value = sessionId;
        
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
            const sessionState = session.current_state ? JSON.parse(session.current_state) : {};
            const steps = sessionState.steps || [];
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

export function updateContextMeter(totalChars) {
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

export async function startNewSession() {
    if (!state.currentProjectId) return;
    try {
        const session = await api(`/api/agentic/projects/${state.currentProjectId}/sessions/new`, { method: 'POST' });
        logToTerminal(`Nouvelle session #${session.id} démarrée.`, 'sys-msg');
        await loadSessions();
        const elSettingsSessionSelect = document.getElementById('settings-session-select');
        const activeId = elSettingsSessionSelect ? elSettingsSessionSelect.value : null;
        if (activeId) await selectSession(activeId);
    } catch (e) {
        logToTerminal(`Erreur création session: ${e.message}`, 'error-msg');
    }
}

export async function loadConversations() {
    const elConvList = document.getElementById('conv-list');
    if (!elConvList) return;
    if (!state.currentProjectId) { elConvList.innerHTML = '<div class="sys-msg">Aucun projet sélectionné</div>'; return; }
    try {
        const msgs = await api(`/api/projects/${state.currentProjectId}/conversations?limit=100`);
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

export async function loadAgenticHistory(projectId) {
    const elAgenticConversation = document.getElementById('agentic-conversation');
    const elSettingsSessionSelect = document.getElementById('settings-session-select');
    try {
        await loadSessions();
        const activeSessionId = elSettingsSessionSelect ? elSettingsSessionSelect.value : null;
        if (activeSessionId) {
            await selectSession(activeSessionId);
        } else {
            if (elAgenticConversation) elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
        }
    } catch {
        if (elAgenticConversation) elAgenticConversation.innerHTML = '<div class="sys-msg">Posez une question à l\'agent.</div>';
    }
}

export async function loadSessions() {
    if (!state.currentProjectId) return;
    const elSettingsSessionSelect = document.getElementById('settings-session-select');
    const elAgenticSessionSelect = document.getElementById('agentic-session-select');
    if (!elSettingsSessionSelect) return;
    
    try {
        const sessions = await api(`/api/agentic/projects/${state.currentProjectId}/sessions`);
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

export async function getOrCreateActiveSessionId() {
    if (!state.currentProjectId) return null;
    const elAgenticSessionSelect = document.getElementById('agentic-session-select');
    let sessionId = elAgenticSessionSelect ? elAgenticSessionSelect.value : null;
    if (!sessionId || sessionId === "") {
        const session = await api(`/api/agentic/projects/${state.currentProjectId}/sessions/new`, { method: 'POST' });
        sessionId = session.id;
        await loadSessions();
        if (elAgenticSessionSelect) elAgenticSessionSelect.value = sessionId;
    }
    return sessionId;
}

export async function saveConversationMessage(role, content) {
    const sessionId = await getOrCreateActiveSessionId();
    if (state.currentProjectId && sessionId) {
        try {
            await api('/api/agentic/conversations', {
                method: 'POST',
                body: JSON.stringify({
                    projectId: state.currentProjectId,
                    sessionId: sessionId,
                    role: role,
                    content: content
                })
            });
        } catch (e) {
            console.error('Failed to save message:', e);
        }
    }
}

function syncTabs() {
    const tabsContainer = document.getElementById('agentic-tabs');
    const elAgenticSessionSelect = document.getElementById('agentic-session-select');
    if (!tabsContainer || !elAgenticSessionSelect) return;
    tabsContainer.innerHTML = '';
    const activeId = elAgenticSessionSelect.value;
    const allOptions = [...elAgenticSessionSelect.options].filter(o => o.value);
    const activeOptions = allOptions.filter(o => !o.textContent.includes('(archived)'));
    
    const show = activeOptions.slice(-8);
    if (activeOptions.length > 8) {
        const overflow = document.createElement('button');
        overflow.className = 'agentic-tab';
        overflow.textContent = `⋯ +${activeOptions.length - 8}`;
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
        const closeBtn = document.createElement('span');
        closeBtn.textContent = '✕';
        closeBtn.style.cssText = 'margin-left:3px;font-size:9px;opacity:0.5;cursor:pointer;';
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
        tab.onclick = () => { elAgenticSessionSelect.value = opt.value; elAgenticSessionSelect.dispatchEvent(new Event('change')); };
        tab.appendChild(closeBtn);
        tabsContainer.appendChild(tab);
    }
}

function renderStepsGraph(steps) {
    const graphContainer = document.querySelector('.agent-nodes-container');
    if (!graphContainer) return;
    graphContainer.innerHTML = '';
    steps.forEach((step, idx) => {
        if (idx > 0) {
            const arrow = document.createElement('div');
            arrow.className = 'agent-node-arrow';
            arrow.textContent = '🠗';
            graphContainer.appendChild(arrow);
        }
        const node = document.createElement('div');
        node.className = 'agent-node';
        node.style.cursor = 'pointer';
        const icons = { read_file: '📖', write_file: '✏️', delete_file: '✕', list_dir: '📂', final_answer: '✅' };
        const icon = icons[step.tool] || '➡️';
        node.innerHTML = `
            <span class="agent-node-icon">${icon}</span>
            <span class="agent-node-title">${step.tool}</span>
            <span class="agent-node-details">${escHtml(step.args?.path || step.args?.text || '')}</span>
            <span class="agent-node-status success">Terminé</span>
        `;
        node.onclick = () => openNodeDetailsDrawer({
            tool: step.tool,
            icon,
            args: step.args,
            result: step.result,
            thinking: step.thinking || ''
        });
        graphContainer.appendChild(node);
    });
}

export function openNodeDetailsDrawer(stepData) {
    const drawer = document.getElementById('node-details-drawer');
    const title = document.getElementById('drawer-node-title');
    const argsPre = document.getElementById('drawer-args');
    const resultPre = document.getElementById('drawer-result');
    const thinkingPre = document.getElementById('drawer-thinking');
    
    if (!drawer) return;
    title.textContent = `${stepData.icon} ${stepData.tool}`;
    argsPre.textContent = JSON.stringify(stepData.args, null, 2);
    resultPre.textContent = stepData.result || '(aucun résultat)';
    thinkingPre.textContent = stepData.thinking || '(aucune pensée)';
    drawer.classList.add('open');
}

export function closeNodeDetailsDrawer() {
    const drawer = document.getElementById('node-details-drawer');
    if (drawer) drawer.classList.remove('open');
}

const REACT_SYSTEM_PROMPT = `You are an AI coding assistant that thinks and acts in PLL.

PLL is for planning AND action — call tools using function syntax: list_dir(".").
You can also respond with plain text when answering a question.

CRITICAL: Do NOT use XML tags like <tool_call>, <tool_name>, or <parameters>.
Do NOT use JSON or other formats for tool calling. Call tools ONLY using pure inline PLL function syntax, e.g. list_dir(".").

CRITICAL WARNING ON TOOL ARGUMENTS:
Never use literal placeholder values from documentation examples like "path", "relative/path", or "url" as arguments!
Always substitute them with real paths, filenames, or URLs (e.g. list_dir("."), read_file("syracuse.pll"), web_fetch("http://127.0.0.1:8080/api/packages")).

PLL quick reference:
  v x != "text"               - variable
  v x != ?("prompt")          - LLM belief
  list_dir(".")               - tool call
  write_file("main.pll", "...") - write file
  read_file("main.pll")        - read file

## Tools

### write_file(path, content)
Create or overwrite a file with full content. Use triple quotes with actual, literal multi-line linebreaks.
CRITICAL: Do NOT write literal '\\n' characters inside the content string! Write actual newlines directly inside the triple quotes instead.
Example:
write_file("test.txt", '''line1
line2''')

### read_file(path)
Read a file from the project.
read_file("relative/path")

### delete_file(path)
Delete a file.
delete_file("relative/path")

### list_dir(path)
List directory contents.
list_dir(".")

### run_command(command, args)
Execute a shell command inside the project directory and return its stdout/stderr.
args is a JSON list of argument strings.
Example:
run_command("cargo", ["build"])
run_command("cargo", ["run"])

### final_answer(text)
Call this when you have completed your task to output your final response.
final_answer("I have completed the files.")
`;

export async function runReActLoopClient(userMessage, backend, placeholder) {
    const filesListText = state.filesList.length > 0 ? `Files: ${state.filesList.join(', ')}` : 'Files: (empty)';
    let contextStr = `## Project ID: ${state.currentProjectId}\n${filesListText}\n`;
    const elAgenticConversation = document.getElementById('agentic-conversation');
    
    // Extract history messages from the DOM chat bubbles
    const msgDivs = elAgenticConversation.querySelectorAll('.agentic-message');
    const historyMsgs = [];
    msgDivs.forEach(div => {
        const isUser = div.classList.contains('user');
        const isAssistant = div.classList.contains('assistant');
        if (isUser || isAssistant) {
            const textEl = div.querySelector('div');
            const text = textEl ? textEl.innerText : div.innerText;
            historyMsgs.push({
                role: isUser ? 'user' : 'assistant',
                content: text
            });
        }
    });
    
    // Grab the last 5 messages for prompt context
    const recentHistory = historyMsgs.slice(-5);
    if (recentHistory.length > 0) {
        contextStr += "\n\n## Conversation précédente:\n" + recentHistory.map(m => `${m.role === 'user' ? 'Utilisateur' : 'Assistant'}: ${m.content}`).join('\n');
    }

    let messages = [
        { role: 'user', content: userMessage }
    ];
    let maxSteps = 20;
    let answer = '';
    let finalCode = '';
    let finalPath = '';
    
    // Create a wrapper for visual node graphing in client mode
    const graphWrapper = addAgenticMessage('system', '<strong>Pensée de l\'Agent (Client Mode) :</strong><div class="agent-nodes-container"></div>');
    const graphContainer = graphWrapper.querySelector('.agent-nodes-container');
    
    let thinkingDots = 0;
    let thinkingTimer = setInterval(() => {
        thinkingDots = (thinkingDots + 1) % 4;
        const dots = '.'.repeat(thinkingDots);
        placeholder.textContent = `🤖 réfléchit${dots}`;
    }, 500);

    for (let step = 0; step < maxSteps; step++) {
        let res;
        try {
            res = await api('/api/llm/chat', {
                method: 'POST',
                body: JSON.stringify({
                    messages: messages,
                    system: REACT_SYSTEM_PROMPT + "\n\n" + contextStr,
                    temperature: 0.15,
                    max_tokens: 4096,
                    backend: backend === 'auto' ? '' : backend,
                    no_cache: true
                })
            });
        } catch (err) {
            clearInterval(thinkingTimer);
            placeholder.remove();
            addAgenticMessage('assistant', `❌ Erreur d'appel LLM: ${err.message}`);
            return;
        }

        const responseText = res.response;
        messages.push({ role: 'assistant', content: responseText });
        
        // Parse tool calls safely
        const calls = parseToolCallsJS(responseText);
        if (calls.length === 0) {
            clearInterval(thinkingTimer);
            placeholder.remove();
            addAgenticMessage('assistant', responseText);
            if (state.currentProjectId) {
                try {
                    const files = await api(`/api/projects/${state.currentProjectId}/files`);
                    state.filesList = [];
                    if (Array.isArray(files)) {
                        for (const filePath of files) {
                            try {
                                const res = await api(`/api/projects/${state.currentProjectId}/files/${encodeURIComponent(filePath)}`);
                                if (res && res.content !== undefined) {
                                    set_virtual_file(filePath, res.content);
                                }
                            } catch (err) {
                                console.warn(`Could not load file content:`, err);
                            }
                            state.filesList.push(filePath);
                        }
                    }
                    renderVfsList();
                } catch (e) {
                    console.error("Failed to reload VFS after agent final answer:", e);
                }
            }
            return;
        }

        for (const call of calls) {
            thinkingDots = 0;
            const icons = { read_file: '📖', write_file: '✏️', delete_file: '✕', list_dir: '📂', final_answer: '✅', run_command: '💻' };
            const icon = icons[call.tool] || '➡️';
            
            // Finalize previous running node
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
            if (call.tool === 'write_file') {
                details = call.args.path;
                finalCode = call.args.content;
                finalPath = call.args.path;
            } else if (call.tool === 'read_file' || call.tool === 'delete_file') {
                details = call.args.path;
            } else if (call.tool === 'run_command') {
                details = `${call.args.command} ${call.args.args.join(' ')}`;
            } else if (call.tool === 'final_answer') {
                details = call.args.text.slice(0, 100);
                answer = call.args.text;
            }

            node.innerHTML = `
                <span class="agent-node-icon">${icon}</span>
                <span class="agent-node-title">${call.tool}</span>
                <span class="agent-node-details">${escHtml(details)}</span>
                <span class="agent-node-status running">En cours</span>
            `;
            graphContainer.appendChild(node);
            elAgenticConversation.scrollTop = elAgenticConversation.scrollHeight;

            let result = '';
            try {
                result = await executeToolJS(call.tool, call.args);
                node.querySelector('.agent-node-status').className = 'agent-node-status success';
                node.querySelector('.agent-node-status').textContent = 'Succès';
            } catch (err) {
                result = `ERROR: ${err.message}`;
                node.querySelector('.agent-node-status').className = 'agent-node-status error';
                node.querySelector('.agent-node-status').textContent = 'Erreur';
            }

            node.stepData = {
                tool: call.tool,
                icon: icon,
                args: call.args,
                result: result,
                thinking: responseText
            };
            node.onclick = () => openNodeDetailsDrawer(node.stepData);

            messages.push({
                role: 'user',
                content: `TOOL_RESULT [${call.tool}]: ${result}`
            });
        }
    }

    clearInterval(thinkingTimer);
    placeholder.remove();
    
    let responseText = '';
    if (finalCode && finalPath) {
        if (!state.filesList.includes(finalPath)) state.filesList.push(finalPath);
        responseText = `✅ **Terminé** — fichiers créés. Consulte l'onglet Fichiers.`;
    } else if (answer) {
        responseText = answer;
    } else {
        responseText = `✅ Terminé.`;
    }
    addAgenticMessage('assistant', responseText);
    await saveConversationMessage('assistant', responseText);
    if (state.currentProjectId) {
        try {
            const files = await api(`/api/projects/${state.currentProjectId}/files`);
            state.filesList = [];
            if (Array.isArray(files)) {
                for (const filePath of files) {
                    try {
                        const res = await api(`/api/projects/${state.currentProjectId}/files/${encodeURIComponent(filePath)}`);
                        if (res && res.content !== undefined) {
                            set_virtual_file(filePath, res.content);
                        }
                    } catch (err) {
                        console.warn(`Could not load file content:`, err);
                    }
                    state.filesList.push(filePath);
                }
            }
            renderVfsList();
        } catch (e) {
            console.error("Failed to reload VFS after agent loop:", e);
        }
    }
}

export function parseToolCallsJS(text) {
    const calls = [];
    const knownTools = ["write_file", "read_file", "delete_file", "list_dir", "final_answer", "run_command"];
    
    const writePattern = /write_file\s*\(\s*["']([^"']+)["']\s*,\s*(?:'''([\s\S]*?)'''|"""([\s\S]*?)"""|`([\s\S]*?)`|"([\s\S]*?)"|'([\s\S]*?)')\s*\)/g;
    let match;
    while ((match = writePattern.exec(text)) !== null) {
        const path = match[1];
        const content = match[2] || match[3] || match[4] || match[5] || match[6] || "";
        calls.push({
            tool: "write_file",
            args: { path, content }
        });
    }

    const simplePattern = /(read_file|delete_file|list_dir|final_answer)\s*\(\s*(?:'''([\s\S]*?)'''|"""([\s\S]*?)"""|`([\s\S]*?)`|"([\s\S]*?)"|'([\s\S]*?)')\s*\)/g;
    simplePattern.lastIndex = 0;
    while ((match = simplePattern.exec(text)) !== null) {
        const tool = match[1];
        const arg = match[2] || match[3] || match[4] || match[5] || match[6] || "";
        if (tool === 'read_file' || tool === 'delete_file' || tool === 'list_dir') {
            calls.push({ tool, args: { path: arg } });
        } else if (tool === 'final_answer') {
            calls.push({ tool, args: { text: arg } });
        }
    }

    let rcMatch;
    const runCommandPattern = /run_command\s*\(\s*["'`]([^"'`]+)["'`]\s*,\s*\[([\s\S]*?)\]\s*\)/g;
    while ((rcMatch = runCommandPattern.exec(text)) !== null) {
        const cmd = rcMatch[1];
        const rawArgs = rcMatch[2];
        const parsedArgs = rawArgs.split(',')
            .map(s => s.trim().replace(/^["'`]|["'`]$/g, ''))
            .filter(s => s.length > 0);
        calls.push({
            tool: "run_command",
            args: { command: cmd, args: parsedArgs }
        });
    }
    
    return calls;
}

export async function executeToolJS(tool, args) {
    if (tool === 'write_file') {
        await api(`/api/projects/${state.currentProjectId}/files`, {
            method: 'POST',
            body: JSON.stringify({ path: args.path, content: args.content })
        });
        if (!state.filesList.includes(args.path)) {
            state.filesList.push(args.path);
        }
        renderVfsList();
        return `File ${args.path} written successfully.`;
    }
    if (tool === 'read_file') {
        const res = await api(`/api/projects/${state.currentProjectId}/files/${args.path}`);
        return res.content;
    }
    if (tool === 'list_dir') {
        const res = await api(`/api/projects/${state.currentProjectId}/files`);
        return JSON.stringify(res);
    }
    if (tool === 'delete_file') {
        await api(`/api/projects/${state.currentProjectId}/files/${args.path}`, {
            method: 'DELETE'
        });
        const idx = state.filesList.indexOf(args.path);
        if (idx !== -1) {
            state.filesList.splice(idx, 1);
        }
        renderVfsList();
        return `File ${args.path} deleted.`;
    }
    if (tool === 'final_answer') {
        return args.text;
    }
    if (tool === 'run_command') {
        return await api('/api/agentic/run_command', {
            method: 'POST',
            body: JSON.stringify({
                projectId: state.currentProjectId,
                command: args.command,
                args: args.args || []
            })
        });
    }
    throw new Error(`Tool inconnu ${tool}`);
}
