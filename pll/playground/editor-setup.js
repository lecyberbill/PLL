const LANG_MAP = {
    '.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.jsx': 'javascript',
    '.tsx': 'typescript', '.rs': 'rust', '.go': 'go', '.java': 'java',
    '.cpp': 'cpp', '.c': 'c', '.h': 'c', '.hpp': 'cpp', '.rb': 'ruby',
    '.php': 'php', '.swift': 'swift', '.kt': 'kotlin', '.scala': 'scala',
    '.pll': 'pll', '.html': 'html', '.css': 'css', '.scss': 'scss',
    '.json': 'json', '.xml': 'xml', '.yaml': 'yaml', '.yml': 'yaml',
    '.md': 'markdown', '.sql': 'sql', '.sh': 'shell', '.bash': 'shell',
    '.r': 'r', '.lua': 'lua', '.dart': 'dart', '.ex': 'elixir',
    '.hs': 'haskell', '.clj': 'clojure', '.zig': 'zig', '.sol': 'solidity',
};

function detectLanguage(filename) {
    const lower = filename.toLowerCase();
    const sorted = Object.keys(LANG_MAP).sort((a, b) => b.length - a.length);
    for (const ext of sorted) {
        if (lower.endsWith(ext)) return LANG_MAP[ext];
    }
    return 'plaintext';
}

async function loadMonaco() {
    const monaco = await import('https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/+esm');
    // Define PLL language
    monaco.languages.register({ id: 'pll' });
    monaco.languages.setMonarchTokensProvider('pll', {
        tokenizer: {
            root: [
                [/#.*$/, 'comment'],
                [/[{}()\[\]]/, '@brackets'],
                [/\bfn\b/, { token: 'keyword', next: '@fn' }],
                [/\b(if|else|while|foreach|return|import)\b/, 'keyword'],
                [/\b(v|render|emit|send)\b/, 'keyword'],
                [/\b(str|num|bool|list|record)\b/, 'type'],
                [/\b(str_concat|str_length|list_new|list_push|read_file|write_file|print)\b/, 'builtin'],
                [/!=[=]?/, 'operator'],
                [/[=+\-*\/<>]/, 'operator'],
                [/\d+\.?\d*/, 'number'],
                [/"[^"]*"/, 'string'],
                [/[a-zA-Z_]\w*/, 'identifier'],
            ],
            fn: [
                [/[a-zA-Z_]\w*/, { token: 'entity.name.function', next: '@pop' }],
                [/\(/, '@brackets', '@pop'],
            ],
        },
    });
    // Define dark theme matching our CSS
    monaco.editor.defineTheme('pll-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '6a9955', fontStyle: 'italic' },
            { token: 'keyword', foreground: 'c586c0' },
            { token: 'type', foreground: 'dcdcaa' },
            { token: 'builtin', foreground: '4fc1ff' },
            { token: 'string', foreground: 'ce9178' },
            { token: 'number', foreground: 'b5cea8' },
            { token: 'operator', foreground: 'd4d4d4' },
            { token: 'identifier', foreground: '9cdcfe' },
            { token: 'function', foreground: 'dcdcaa' },
        ],
        colors: {
            'editor.background': '#0f0f1a',
            'editor.foreground': '#e0e0e0',
            'editor.lineHighlightBackground': '#1a1a2e',
            'editor.selectionBackground': '#7c5cfc44',
            'editorCursor.foreground': '#7c5cfc',
            'editorLineNumber.foreground': '#555',
            'editorLineNumber.activeForeground': '#888',
        },
    });
    return monaco;
}

export { loadMonaco, detectLanguage, LANG_MAP };
