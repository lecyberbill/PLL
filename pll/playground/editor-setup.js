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
    return monaco;
}

export { loadMonaco, detectLanguage, LANG_MAP };
