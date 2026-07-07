// PLL WASM stub — provides VFS functions without compiled WASM
const virtualFiles = {};

function set_virtual_file(path, content) {
    if (content === null || content === undefined) {
        delete virtualFiles[path];
    } else {
        virtualFiles[path] = content;
    }
}

function get_virtual_file(path) {
    return virtualFiles[path] !== undefined ? virtualFiles[path] : null;
}

function compile_and_run(_filename) {
    return "[PLL VM: WASM not loaded — run via agent instead]";
}

function compile_to_bytecode_string(_filename) {
    return "[Bytecode: WASM not loaded]";
}

export { set_virtual_file, get_virtual_file, compile_and_run, compile_to_bytecode_string };
