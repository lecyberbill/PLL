export const state = {
    currentProjectId: null,
    activeFile: 'logic_flow.agent',
    openFiles: ['logic_flow.agent'],
    filesList: [],
    gitFileStatus: {}, // { "path": "M"|"A"|"?"|"D" }
    gitAheadFiles: [],
    gcaSessionId: null,
    gcaGeneration: 0,
    agenticConversationHistory: [],
    selectedTemplate: 'empty',
    monaco: null,
    editor: null,
    monacoDiffEditor: null,
    termHistory: [],
    termHistIdx: -1,
    
    // Constant defaults
    DEFAULT_FILES: {
        'main.py': 'def hello():\n    print("Hello, PLL!")\n\nhello()',
        'helpers.pll': 'fn greet(name: str) -> str:\n    return str_concat("Hello, ", name)\n\nrender greet("PLL")',
    }
};
