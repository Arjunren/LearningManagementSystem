importScripts("https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js");

let pyodideReadyPromise;

async function loadPyodideAndPackages() {
    self.pyodide = await loadPyodide({
        stdout: (text) => {
            self.postMessage({ type: 'stdout', content: text });
        },
        stderr: (text) => {
            self.postMessage({ type: 'stderr', content: text });
        }
    });
    // Can load packages here if needed: await self.pyodide.loadPackage(["numpy"]);
}

pyodideReadyPromise = loadPyodideAndPackages();

self.onmessage = async (event) => {
    const { id, python, type } = event.data;
    
    if (type === 'init') {
        try {
            await pyodideReadyPromise;
            self.postMessage({ type: 'init_done' });
        } catch (error) {
            self.postMessage({ type: 'error', error: error.message });
        }
        return;
    }

    if (type === 'run') {
        try {
            await pyodideReadyPromise;
            await self.pyodide.loadPackagesFromImports(python);
            const result = await self.pyodide.runPythonAsync(python);
            self.postMessage({ type: 'done', id, result });
        } catch (error) {
            self.postMessage({ type: 'error', id, error: error.message });
        }
    }
};
