import { state } from './state.js';

const API_BASE = (window.location.port === '1430' || (window.location.hostname !== 'localhost' && window.location.port !== '8080')) ? 'http://127.0.0.1:8080' : '';

export async function api(path, options = {}) {
    if (window.__TAURI__) {
        const invoke = window.__TAURI__.core.invoke;
        const url = new URL(path, window.location.origin);
        const pathname = url.pathname;
        const params = url.searchParams;
        
        // 1. Projects endpoints
        if (pathname === '/api/projects') {
            if (options.method === 'POST') {
                const body = JSON.parse(options.body);
                return await invoke('create_project', { 
                    name: body.name, 
                    description: body.description, 
                    diskPath: body.disk_path 
                });
            } else {
                return await invoke('list_projects');
            }
        }
        
        if (pathname.startsWith('/api/projects/')) {
            const parts = pathname.split('/');
            const projectId = parseInt(parts[3]);
            
            // /api/projects/{id}/files/rename
            if (parts.length === 6 && parts[4] === 'files' && parts[5] === 'rename') {
                const oldPath = params.get('old_path');
                const newPath = params.get('new_path');
                return await invoke('rename_project_file', { projectId, oldPath, newPath });
            }
            
            // /api/projects/{id}/files
            if (parts.length === 5 && parts[4] === 'files') {
                if (options.method === 'POST') {
                    const body = JSON.parse(options.body);
                    return await invoke('write_project_file', { 
                        projectId, 
                        path: body.path, 
                        content: body.content 
                    });
                } else {
                    return await invoke('list_project_files', { projectId });
                }
            }
            
            // /api/projects/{id}/files/{file_path}
            if (parts.length >= 6 && parts[4] === 'files') {
                const rawPath = parts.slice(5).join('/');
                const filePath = decodeURIComponent(rawPath);
                if (options.method === 'DELETE') {
                    return await invoke('delete_project_file', { projectId, path: filePath });
                } else {
                    return await invoke('get_project_file', { projectId, path: filePath });
                }
            }

            if (options.method === 'DELETE') {
                const keep = params.get('keep_files') !== 'false';
                return await invoke('delete_project', { projectId, keepFiles: keep });
            }
            
            return await invoke('get_project', { projectId });
        }
        
        // 2. Git endpoints
        if (pathname.startsWith('/api/git/')) {
            const parts = pathname.split('/');
            const projectId = parseInt(parts[3]);
            const action = parts[4];
            
            if (action === 'status') return await invoke('get_git_status', { projectId });
            if (action === 'commit') {
                const body = JSON.parse(options.body || '{}');
                return await invoke('git_commit', { projectId, message: body.message, autoMessage: body.auto_message });
            }
            if (action === 'init') return await invoke('git_init', { projectId });
            if (action === 'remote') {
                const body = JSON.parse(options.body || '{}');
                return await invoke('git_remote', { projectId, url: body.url });
            }
            if (action === 'push') return await invoke('git_push', { projectId });
            if (action === 'pull') return await invoke('git_pull', { projectId });
            if (action === 'log') return await invoke('git_log', { projectId });
            if (action === 'diff') return await invoke('git_diff', { projectId });
            if (action === 'show') {
                const filePath = params.get('file_path');
                return await invoke('git_show', { projectId, filePath });
            }
        }
        
        // 3. LLM endpoints
        if (pathname === '/api/llm/chat' || pathname === '/api/agentic/chat') {
            const body = JSON.parse(options.body || '{}');
            const res = await invoke('chat_completion', {
                messages: body.messages || [],
                systemPrompt: body.system || null,
                temperature: body.temperature || null,
                maxTokens: body.max_tokens || null,
                backend: body.backend || null,
                noCache: body.no_cache || null
            });
            return { response: res.response, backend: res.backend };
        }

        // 4. PLL code execution
        if (pathname === '/api/pll/exec') {
            const body = JSON.parse(options.body || '{}');
            return await invoke('run_pll_code', { code: body.code });
        }

        // 5. Agentic Sessions and Conversations endpoints
        if (pathname.startsWith('/api/agentic/projects/') && pathname.endsWith('/sessions/new')) {
            const projectId = parseInt(pathname.split('/')[4]);
            return await invoke('create_session', { projectId });
        }
        if (pathname.startsWith('/api/agentic/projects/') && pathname.endsWith('/sessions')) {
            const projectId = parseInt(pathname.split('/')[4]);
            return await invoke('list_sessions', { projectId });
        }
        if (pathname.startsWith('/api/agentic/sessions/') && pathname.endsWith('/conversations')) {
            const sessionId = parseInt(pathname.split('/')[4]);
            return await invoke('get_conversations', { sessionId });
        }
        if (pathname.startsWith('/api/agentic/sessions/') && pathname.endsWith('/archive')) {
            const sessionId = parseInt(pathname.split('/')[4]);
            return await invoke('archive_session', { sessionId });
        }
        if (pathname.startsWith('/api/agentic/sessions/')) {
            const parts = pathname.split('/');
            if (parts.length === 5) {
                const sessionId = parseInt(parts[4]);
                return await invoke('get_session', { sessionId });
            }
        }
        if (pathname === '/api/agentic/conversations' && options.method === 'POST') {
            const body = JSON.parse(options.body || '{}');
            return await invoke('save_message', { 
                projectId: parseInt(body.projectId), 
                sessionId: parseInt(body.sessionId), 
                role: body.role, 
                content: body.content 
            });
        }
        if (pathname === '/api/agentic/run_command' && options.method === 'POST') {
            const body = JSON.parse(options.body || '{}');
            return await invoke('run_project_command', {
                projectId: parseInt(body.projectId),
                command: body.command,
                args: body.args || [],
                cwd: body.cwd || null
            });
        }
    }
    
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`API ${resp.status}: ${text}`);
    }
    if (resp.status === 204) return null;
    const text = await resp.text();
    try {
        return JSON.parse(text);
    } catch {
        return text;
    }
}
