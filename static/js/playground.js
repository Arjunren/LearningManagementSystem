const playgroundLanguages = {
    python: {
        name: "Python",
        editorLanguage: "python",
        executable: true,
        runtime: "pyodide",
        template: `print("Hello, BuildByte Academy!")`
    },
    javascript: {
        name: "JavaScript",
        editorLanguage: "javascript",
        executable: true,
        runtime: "browser",
        template: `console.log("Hello, BuildByte Academy!");`
    },
    html: {
        name: "HTML",
        editorLanguage: "html",
        executable: true,
        runtime: "iframe",
        template: `<!DOCTYPE html>\n<html lang="en">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>My Page</title>\n</head>\n<body>\n    <h1>Hello, BuildByte Academy!</h1>\n</body>\n</html>`
    },
    java: {
        name: "Java",
        editorLanguage: "java",
        executable: false,
        runtime: "none",
        template: `class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, BuildByte Academy!");\n    }\n}`
    },
    cpp: {
        name: "C++",
        editorLanguage: "cpp",
        executable: false,
        runtime: "none",
        template: `#include <iostream>\n\nint main() {\n    std::cout << "Hello, BuildByte Academy!" << std::endl;\n    return 0;\n}`
    }
};

let editor;
let currentLanguage = 'python';
let pyodideWorker;
let isRunning = false;
let autoRunTimeout;

function initMonaco() {
    require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs' }});
    require(['vs/editor/editor.main'], function() {
        let savedCode = localStorage.getItem(`playground_code_${currentLanguage}`);
        let code = savedCode !== null ? savedCode : playgroundLanguages[currentLanguage].template;
        
        editor = monaco.editor.create(document.getElementById('editor-container'), {
            value: code,
            language: playgroundLanguages[currentLanguage].editorLanguage,
            theme: 'vs', // 'vs-dark' could be used based on theme
            minimap: { enabled: false },
            automaticLayout: true,
            fontSize: 14,
            scrollBeyondLastLine: false,
            roundedSelection: false,
        });

        editor.onDidChangeModelContent(() => {
            let code = editor.getValue();
            localStorage.setItem(`playground_code_${currentLanguage}`, code);
            showSaveStatus();
            
            if (document.getElementById('auto-run').checked && playgroundLanguages[currentLanguage].runtime === 'iframe') {
                clearTimeout(autoRunTimeout);
                autoRunTimeout = setTimeout(runCode, 1000);
            }
        });

        // Setup Ctrl+Enter / Cmd+Enter
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, function() {
            runCode();
        });
        
        updateUIForLanguage();
    });
}

function showSaveStatus() {
    const status = document.getElementById('status-indicator');
    status.innerText = 'Saving...';
    setTimeout(() => {
        status.innerText = 'Saved locally';
    }, 500);
}

function changeLanguage(lang) {
    if (currentLanguage === lang) return;
    
    // Save current language first
    if (editor) {
        localStorage.setItem(`playground_code_${currentLanguage}`, editor.getValue());
    }

    currentLanguage = lang;
    document.getElementById('language-selector').value = lang;
    
    let savedCode = localStorage.getItem(`playground_code_${currentLanguage}`);
    let code = savedCode !== null ? savedCode : playgroundLanguages[currentLanguage].template;
    
    if (editor) {
        monaco.editor.setModelLanguage(editor.getModel(), playgroundLanguages[currentLanguage].editorLanguage);
        editor.setValue(code);
    }
    
    updateUIForLanguage();
    
    // Auto initialize pyodide if Python selected
    if (lang === 'python' && !pyodideWorker) {
        initPyodide();
    }
}

function updateUIForLanguage() {
    const langConfig = playgroundLanguages[currentLanguage];
    const runBtn = document.getElementById('run-btn');
    const autoRunContainer = document.getElementById('auto-run-container');
    const status = document.getElementById('status-indicator');
    const langBadge = document.getElementById('language-badge');
    
    langBadge.innerText = langConfig.executable ? `● ${langConfig.name}` : `${langConfig.name} (Syntax Support)`;
    
    runBtn.disabled = false;
    runBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    
    if (langConfig.executable) {
        if (langConfig.runtime === 'iframe') {
            autoRunContainer.classList.remove('hidden');
            switchToPreview();
        } else {
            autoRunContainer.classList.add('hidden');
            switchToConsole();
        }
    } else {
        autoRunContainer.classList.add('hidden');
        switchToConsole();
        document.getElementById('console-output').innerHTML = '';
        appendOutput(`Editor only\nThis language currently supports syntax editing in Playground.`, 'info');
    }
}

function switchToPreview() {
    document.getElementById('console-output').classList.add('hidden');
    document.getElementById('preview-output').classList.remove('hidden');
}

function switchToConsole() {
    document.getElementById('console-output').classList.remove('hidden');
    document.getElementById('preview-output').classList.add('hidden');
}

function appendOutput(text, type='normal') {
    const consoleOutput = document.getElementById('console-output');
    const span = document.createElement('span');
    span.innerText = text + '\\n';
    if (type === 'error') {
        span.classList.add('text-red-500');
    } else if (type === 'info') {
        span.classList.add('text-blue-500');
    } else if (type === 'success') {
        span.classList.add('text-green-500');
    }
    consoleOutput.appendChild(span);
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
}

function clearOutput() {
    document.getElementById('console-output').innerHTML = '';
    const iframe = document.getElementById('preview-iframe');
    iframe.srcdoc = '';
    document.getElementById('status-indicator').innerText = 'Ready';
}

function resetCode() {
    if (confirm("Reset this file to its starter code?")) {
        const langConfig = playgroundLanguages[currentLanguage];
        editor.setValue(langConfig.template);
        localStorage.removeItem(`playground_code_${currentLanguage}`);
    }
}

function copyCode() {
    const code = editor.getValue();
    navigator.clipboard.writeText(code).then(() => {
        const btn = document.getElementById('copy-btn');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="ph ph-check"></i> Copied';
        setTimeout(() => { btn.innerHTML = originalText; }, 2000);
    });
}

function downloadCode() {
    const code = editor.getValue();
    const langConfig = playgroundLanguages[currentLanguage];
    let ext = "txt";
    if (langConfig.editorLanguage === "python") ext = "py";
    else if (langConfig.editorLanguage === "javascript") ext = "js";
    else if (langConfig.editorLanguage === "html") ext = "html";
    else if (langConfig.editorLanguage === "css") ext = "css";
    else ext = langConfig.editorLanguage;
    
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `main.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
}

function toggleFullscreen() {
    const playground = document.getElementById('playground-wrapper');
    if (!document.fullscreenElement) {
        playground.requestFullscreen().catch(err => {
            console.error(`Error attempting to enable fullscreen: ${err.message}`);
        });
    } else {
        document.exitFullscreen();
    }
}

// ==========================================
// Runtimes
// ==========================================

function initPyodide() {
    if (pyodideWorker) return;
    document.getElementById('status-indicator').innerText = 'Loading Python runtime...';
    
    pyodideWorker = new Worker('/static/js/pyodide_worker.js');
    
    pyodideWorker.onmessage = (event) => {
        const msg = event.data;
        if (msg.type === 'init_done') {
            document.getElementById('status-indicator').innerText = 'Ready';
        } else if (msg.type === 'stdout') {
            appendOutput(msg.content);
        } else if (msg.type === 'stderr') {
            appendOutput(msg.content, 'error');
        } else if (msg.type === 'done') {
            document.getElementById('status-indicator').innerText = 'Finished';
            setRunning(false);
        } else if (msg.type === 'error') {
            document.getElementById('status-indicator').innerText = 'Error';
            appendOutput(`\\n✕ Execution Error\\n\\n${msg.error}`, 'error');
            setRunning(false);
        }
    };
    
    pyodideWorker.postMessage({ type: 'init' });
}

function runPython(code) {
    if (!pyodideWorker) {
        initPyodide();
    }
    document.getElementById('console-output').innerHTML = ''; // clear for new run
    setRunning(true);
    pyodideWorker.postMessage({ type: 'run', id: Date.now(), python: code });
}

function stopPython() {
    if (pyodideWorker && isRunning) {
        pyodideWorker.terminate();
        pyodideWorker = null; // force re-init on next run
        setRunning(false);
        appendOutput('\\n■ Stopped', 'error');
        document.getElementById('status-indicator').innerText = 'Stopped';
    }
}

function runJavaScript(code) {
    document.getElementById('console-output').innerHTML = '';
    setRunning(true);
    
    try {
        // Use an iframe to sandbox JS
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        
        // Setup console proxy
        let consoleOutput = [];
        iframe.onload = () => {
            const iframeWindow = iframe.contentWindow;
            
            ['log', 'info', 'warn', 'error'].forEach(method => {
                iframeWindow.console[method] = (...args) => {
                    const strArgs = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ');
                    appendOutput(strArgs, method === 'error' ? 'error' : 'normal');
                };
            });

            try {
                iframeWindow.eval(code);
            } catch (err) {
                appendOutput(`\\n✕ Execution Error\\n\\n${err.name}: ${err.message}`, 'error');
            }
            
            document.body.removeChild(iframe);
            setRunning(false);
        };
        document.body.appendChild(iframe);
        
    } catch (e) {
        appendOutput(`Error: ${e.message}`, 'error');
        setRunning(false);
    }
}

function runPreview(code, type) {
    const iframe = document.getElementById('preview-iframe');
    let srcDoc = '';
    
    if (type === 'html') {
        srcDoc = code;
    } else if (type === 'css') {
        srcDoc = `<!DOCTYPE html><html><head><style>${code}</style></head><body><h1>CSS Preview</h1><p>Change HTML structure in HTML mode.</p></body></html>`;
    }
    
    iframe.srcdoc = srcDoc;
    document.getElementById('status-indicator').innerText = 'Preview Updated';
}

function runCode() {
    if (isRunning) return;
    
    const code = editor.getValue();
    const langConfig = playgroundLanguages[currentLanguage];
    
    if (!langConfig.executable) {
        document.getElementById('console-output').innerHTML = '';
        appendOutput('Execution not supported for this language in browser.', 'error');
        return;
    }
    
    if (langConfig.runtime === 'pyodide') {
        runPython(code);
    } else if (langConfig.runtime === 'browser') {
        runJavaScript(code);
    } else if (langConfig.runtime === 'iframe') {
        runPreview(code, langConfig.editorLanguage);
    }
}

function setRunning(running) {
    isRunning = running;
    const runBtn = document.getElementById('run-btn');
    const stopBtn = document.getElementById('stop-btn');
    
    if (running) {
        runBtn.classList.add('hidden');
        if (playgroundLanguages[currentLanguage].runtime === 'pyodide') {
            stopBtn.classList.remove('hidden');
        }
        document.getElementById('status-indicator').innerText = 'Running...';
    } else {
        runBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
        if (document.getElementById('status-indicator').innerText === 'Running...') {
            document.getElementById('status-indicator').innerText = 'Ready';
        }
    }
}

// Setup Event Listeners when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Populate Language Selector
    const selector = document.getElementById('language-selector');
    Object.keys(playgroundLanguages).forEach(key => {
        const option = document.createElement('option');
        option.value = key;
        option.innerText = playgroundLanguages[key].name;
        selector.appendChild(option);
    });
    
    // Load Monaco Script dynamically
    const script = document.createElement('script');
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs/loader.min.js";
    script.onload = () => {
        initMonaco();
    };
    document.head.appendChild(script);
    
    // Fullscreen support
    document.addEventListener('fullscreenchange', () => {
        const btn = document.getElementById('fullscreen-btn');
        if (document.fullscreenElement) {
            btn.innerHTML = '<i class="ph ph-corners-in"></i> Exit Fullscreen';
        } else {
            btn.innerHTML = '<i class="ph ph-corners-out"></i> Fullscreen';
        }
    });
});
