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
        keywords: [
            'v', 't', 'fn', 'emit', 'render', 'agent', 'on', 'if', 'else', 'while', 'return', 'end'
        ],
        types: [
            'String', 'num', 'bool', 'event', 'List'
        ],
        operators: [
            '!=', '=', '==', '>', '<', '>=', '<=', '+', '-', '*', '/', 'and', 'or', 'not'
        ],
        builtins: [
            'str_concat', 'str_length', 'str_slice', 'str_char_at', 'str_to_num', 'str_from_num',
            'str_starts_with', 'str_is_digit', 'str_is_letter', 'str_to_upper', 'list_length',
            'list_get', 'list_push', 'read_file', 'write_file', 'db_set', 'db_read', 'args',
            'input', 'send', 'recv'
        ],
        tokenizer: {
            root: [
                [/#.*$/, 'comment'],
                [/[{}()\[\]]/, '@brackets'],
                [/\bfn\b/, { token: 'keyword', next: '@fn' }],
                [/[a-zA-Z_]\w*/, {
                    cases: {
                        '@keywords': 'keyword',
                        '@types': 'type',
                        '@builtins': 'builtin',
                        '@operators': 'operator',
                        '@default': 'identifier'
                    }
                }],
                [/!=|[=+\-*\/<>]/, 'operator'],
                [/\d+\.?\d*/, 'number'],
                [/"{3}([\s\S]*?)"{3}/, 'string'],
                [/'{3}([\s\S]*?)'{3}/, 'string'],
                [/"[^"]*"/, 'string'],
                [/'[^']*'/, 'string'],
            ],
            fn: [
                [/[a-zA-Z_]\w*/, { token: 'entity.name.function', next: '@pop' }],
                [/\(/, '@brackets', '@pop'],
            ],
        },
    });

    // Auto-complete provider for PLL
    monaco.languages.registerCompletionItemProvider('pll', {
        provideCompletionItems: (model, position) => {
            const word = model.getWordUntilPosition(position);
            const range = {
                startLineNumber: position.lineNumber,
                endLineNumber: position.lineNumber,
                startColumn: word.startColumn,
                endColumn: word.endColumn
            };
            const suggestions = [
                {
                    label: 'fn',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: 'fn ${1:name}(${2:params}):\n\t${3:body}\nend',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Déclaration de fonction PLL',
                    range: range
                },
                {
                    label: 'if',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: 'if ${1:condition}:\n\t${2:body}\nelse:\n\t${3:alt}\nend',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Structure conditionnelle',
                    range: range
                },
                {
                    label: 'while',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: 'while ${1:condition}:\n\t${2:body}\nend',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Boucle tant que',
                    range: range
                },
                {
                    label: 'v',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: 'v ${1:var_name} != ${2:value}',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Déclaration de variable PLL',
                    range: range
                },
                {
                    label: 't',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: 't ${1:TypeName} [${2:field}: ${3:Type}]',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Déclaration de type record PLL',
                    range: range
                },
                {
                    label: 'agent',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: 'agent "${1:name}" on ${2:Proto}:\n\ton ${3:Msg}:\n\t\t${4:body}\nend',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Déclaration d\'agent PLL',
                    range: range
                },
                {
                    label: 'db_set',
                    kind: monaco.languages.CompletionItemKind.Function,
                    insertText: 'db_set("${1:key}", ${2:value})',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Persistance: stocker une clé/valeur',
                    range: range
                },
                {
                    label: 'db_read',
                    kind: monaco.languages.CompletionItemKind.Function,
                    insertText: 'db_read("${1:key}")',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Persistance: lire une clé',
                    range: range
                },
                {
                    label: 'write_file',
                    kind: monaco.languages.CompletionItemKind.Snippet,
                    insertText: 'write_file("${1:path}", """${2:content}""")',
                    insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
                    documentation: 'Ecrire un fichier avec des guillemets triples',
                    range: range
                }
            ];
            return { suggestions };
        }
    });

    // Define dark theme matching our CSS
    monaco.editor.defineTheme('pll-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'comment', foreground: '6a9955', fontStyle: 'italic' },
            { token: 'keyword', foreground: 'c586c0' },
            { token: 'type', foreground: '4ec9b0' },
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
