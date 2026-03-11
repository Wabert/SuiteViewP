"use strict";
/**
 * SuiteView AI Bridge - VS Code Extension
 *
 * This extension creates a local HTTP server that bridges
 * the VS Code Language Model API to external applications.
 *
 * Features:
 * - Chat completions with streaming support
 * - File read/write operations
 * - Workspace access
 * - Terminal command execution
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const http = __importStar(require("http"));
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
let server = null;
let statusBarItem;
let outputChannel;
function activate(context) {
    outputChannel = vscode.window.createOutputChannel('SuiteView AI Bridge');
    outputChannel.appendLine('SuiteView AI Bridge extension activated');
    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'suiteview-ai-bridge.showStatus';
    context.subscriptions.push(statusBarItem);
    // Register commands
    context.subscriptions.push(vscode.commands.registerCommand('suiteview-ai-bridge.startServer', startServer), vscode.commands.registerCommand('suiteview-ai-bridge.stopServer', stopServer), vscode.commands.registerCommand('suiteview-ai-bridge.showStatus', showStatus));
    // Auto-start if configured
    const config = vscode.workspace.getConfiguration('suiteviewAiBridge');
    if (config.get('autoStart', true)) {
        startServer();
    }
}
function deactivate() {
    stopServer();
}
async function startServer() {
    if (server) {
        vscode.window.showInformationMessage('SuiteView AI Bridge server is already running');
        return;
    }
    const config = vscode.workspace.getConfiguration('suiteviewAiBridge');
    const port = config.get('port', 3000);
    server = http.createServer(async (req, res) => {
        // CORS headers for local development
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');
        if (req.method === 'OPTIONS') {
            res.writeHead(200);
            res.end();
            return;
        }
        // Parse the URL
        const url = new URL(req.url || '/', `http://localhost:${port}`);
        try {
            if (req.method === 'GET' && url.pathname === '/health') {
                // Health check endpoint
                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'ok', version: '1.0.0' }));
            }
            else if (req.method === 'GET' && url.pathname === '/models') {
                // List available models
                await handleListModels(req, res);
            }
            else if (req.method === 'POST' && url.pathname === '/chat') {
                // Chat completion endpoint
                await handleChat(req, res);
            }
            else if (req.method === 'POST' && url.pathname === '/files/read') {
                // Read file endpoint
                await handleReadFile(req, res);
            }
            else if (req.method === 'POST' && url.pathname === '/files/write') {
                // Write file endpoint
                await handleWriteFile(req, res);
            }
            else if (req.method === 'POST' && url.pathname === '/files/list') {
                // List files endpoint
                await handleListFiles(req, res);
            }
            else if (req.method === 'POST' && url.pathname === '/terminal/execute') {
                // Execute terminal command
                await handleTerminalExecute(req, res);
            }
            else if (req.method === 'GET' && url.pathname === '/workspace') {
                // Get workspace info
                await handleWorkspaceInfo(req, res);
            }
            else if (req.method === 'POST' && url.pathname === '/agent/chat') {
                // Agent chat - writes response to shared file
                await handleAgentChat(req, res);
            }
            else if (req.method === 'GET' && url.pathname === '/agent/responses') {
                // Get latest agent responses
                await handleGetAgentResponses(req, res);
            }
            // OpenAI-compatible endpoints
            else if (req.method === 'GET' && url.pathname === '/v1/models') {
                // OpenAI-compatible models list
                await handleOpenAIModels(req, res);
            }
            else if (req.method === 'POST' && url.pathname === '/v1/chat/completions') {
                // OpenAI-compatible chat completions
                await handleOpenAIChatCompletions(req, res);
            }
            else {
                res.writeHead(404, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'Not found' }));
            }
        }
        catch (error) {
            outputChannel.appendLine(`Error handling request: ${error.message}`);
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: error.message }));
        }
    });
    server.listen(port, '127.0.0.1', () => {
        outputChannel.appendLine(`Server started on http://127.0.0.1:${port}`);
        vscode.window.showInformationMessage(`SuiteView AI Bridge server started on port ${port}`);
        updateStatusBar(true, port);
    });
    server.on('error', (err) => {
        outputChannel.appendLine(`Server error: ${err.message}`);
        if (err.code === 'EADDRINUSE') {
            vscode.window.showErrorMessage(`Port ${port} is already in use. Please configure a different port.`);
        }
        server = null;
        updateStatusBar(false);
    });
}
function stopServer() {
    if (server) {
        server.close();
        server = null;
        outputChannel.appendLine('Server stopped');
        vscode.window.showInformationMessage('SuiteView AI Bridge server stopped');
        updateStatusBar(false);
    }
}
function showStatus() {
    const config = vscode.workspace.getConfiguration('suiteviewAiBridge');
    const port = config.get('port', 3000);
    if (server) {
        vscode.window.showInformationMessage(`SuiteView AI Bridge is running on http://127.0.0.1:${port}`, 'Stop Server').then(selection => {
            if (selection === 'Stop Server') {
                stopServer();
            }
        });
    }
    else {
        vscode.window.showInformationMessage('SuiteView AI Bridge server is not running', 'Start Server').then(selection => {
            if (selection === 'Start Server') {
                startServer();
            }
        });
    }
}
function updateStatusBar(running, port) {
    if (running) {
        statusBarItem.text = `$(radio-tower) SuiteView AI: ${port}`;
        statusBarItem.tooltip = `SuiteView AI Bridge running on port ${port}`;
        statusBarItem.backgroundColor = undefined;
    }
    else {
        statusBarItem.text = '$(circle-slash) SuiteView AI: Off';
        statusBarItem.tooltip = 'SuiteView AI Bridge is not running';
    }
    statusBarItem.show();
}
// Helper to parse JSON body
async function parseBody(req) {
    return new Promise((resolve, reject) => {
        let body = '';
        req.on('data', chunk => body += chunk);
        req.on('end', () => {
            try {
                resolve(body ? JSON.parse(body) : {});
            }
            catch (e) {
                reject(new Error('Invalid JSON'));
            }
        });
        req.on('error', reject);
    });
}
// List available language models
async function handleListModels(req, res) {
    try {
        // Get available models from VS Code
        const allModels = await vscode.lm.selectChatModels();
        // Map and sort models - prefer newer/better models
        let modelList = allModels.map(m => ({
            id: m.id,
            name: m.name,
            vendor: m.vendor,
            family: m.family,
            version: m.version,
            maxInputTokens: m.maxInputTokens
        }));
        // Sort by preference: GPT-4 models first, then by family/version
        modelList.sort((a, b) => {
            // Prioritize GPT-4 and Claude-3.5 models
            const aPriority = a.family?.includes('gpt-4') || a.family?.includes('claude-3.5') ? 0 : 1;
            const bPriority = b.family?.includes('gpt-4') || b.family?.includes('claude-3.5') ? 0 : 1;
            if (aPriority !== bPriority)
                return aPriority - bPriority;
            // Then sort by version (descending)
            if (a.version && b.version) {
                return b.version.localeCompare(a.version);
            }
            return 0;
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            models: modelList,
            count: modelList.length,
            recommended: modelList[0]?.id // Return the best model as recommended
        }));
    }
    catch (error) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
    }
}
// Handle chat completion requests
async function handleChat(req, res) {
    const body = await parseBody(req);
    const { messages, model, stream = true } = body;
    if (!messages || !Array.isArray(messages)) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'messages array is required' }));
        return;
    }
    outputChannel.appendLine(`Chat request: ${messages.length} messages, model: ${model || 'default'}, stream: ${stream}`);
    try {
        // Select a model
        let selectedModels = await vscode.lm.selectChatModels();
        outputChannel.appendLine(`=== CHAT REQUEST ===`);
        outputChannel.appendLine(`Requested model: "${model}"`);
        outputChannel.appendLine(`Available models (${selectedModels.length}): ${selectedModels.map(m => m.id).join(', ')}`);
        if (model) {
            // Try exact match first - this should work for IDs like "claude-opus-4.5"
            let filtered = selectedModels.filter(m => m.id === model);
            outputChannel.appendLine(`Exact match for "${model}": ${filtered.length} found`);
            // If no exact match, try case-insensitive
            if (filtered.length === 0) {
                filtered = selectedModels.filter(m => m.id.toLowerCase() === model.toLowerCase());
                outputChannel.appendLine(`Case-insensitive match: ${filtered.length} found`);
            }
            // If still no match, try partial
            if (filtered.length === 0) {
                filtered = selectedModels.filter(m => m.id.toLowerCase().includes(model.toLowerCase()) ||
                    m.family?.toLowerCase().includes(model.toLowerCase()) ||
                    m.name?.toLowerCase().includes(model.toLowerCase()));
                outputChannel.appendLine(`Partial match: ${filtered.length} found`);
            }
            if (filtered.length > 0) {
                selectedModels = filtered;
                outputChannel.appendLine(`>>> USING MODEL: ${selectedModels[0].id} (name: ${selectedModels[0].name})`);
            }
            else {
                outputChannel.appendLine(`>>> NO MATCH! Using default: ${selectedModels[0].id}`);
            }
        }
        else {
            outputChannel.appendLine(`>>> No model specified, using: ${selectedModels[0].id}`);
        }
        if (selectedModels.length === 0) {
            res.writeHead(503, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'No language models available. Make sure GitHub Copilot is enabled.' }));
            return;
        }
        const chatModel = selectedModels[0];
        outputChannel.appendLine(`Using model: ${chatModel.name} (${chatModel.id})`);
        // Convert messages to VS Code format
        const chatMessages = messages.map((m) => {
            if (m.role === 'user') {
                return vscode.LanguageModelChatMessage.User(m.content);
            }
            else if (m.role === 'assistant') {
                return vscode.LanguageModelChatMessage.Assistant(m.content);
            }
            else {
                // System messages are treated as user messages with a prefix
                return vscode.LanguageModelChatMessage.User(`[System]: ${m.content}`);
            }
        });
        // Send request to the model
        const response = await chatModel.sendRequest(chatMessages, {}, new vscode.CancellationTokenSource().token);
        if (stream) {
            // Streaming response with UTF-8 encoding
            res.writeHead(200, {
                'Content-Type': 'text/event-stream; charset=utf-8',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Model-Used': chatModel.id // Include model in header
            });
            // Send model info as first chunk so user knows which model is responding
            const modelInfo = `[Model: ${chatModel.name || chatModel.id}]\n\n`;
            const modelChunk = JSON.stringify({
                choices: [{
                        delta: { content: modelInfo },
                        index: 0
                    }]
            });
            res.write(`data: ${modelChunk}\n\n`);
            for await (const chunk of response.text) {
                const data = JSON.stringify({
                    choices: [{
                            delta: { content: chunk },
                            index: 0
                        }]
                });
                res.write(`data: ${data}\n\n`);
            }
            res.write('data: [DONE]\n\n');
            res.end();
        }
        else {
            // Non-streaming response - collect all chunks
            let fullResponse = '';
            for await (const chunk of response.text) {
                fullResponse += chunk;
            }
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                choices: [{
                        message: { role: 'assistant', content: fullResponse },
                        index: 0
                    }]
            }));
        }
        outputChannel.appendLine('Chat request completed successfully');
    }
    catch (error) {
        outputChannel.appendLine(`Chat error: ${error.message}`);
        // Handle specific errors
        if (error.message.includes('not authenticated') || error.message.includes('sign in')) {
            res.writeHead(401, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                error: 'Not authenticated with GitHub Copilot. Please sign in to VS Code with your GitHub account.',
                code: 'AUTH_REQUIRED'
            }));
        }
        else {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: error.message }));
        }
    }
}
// Read file contents
async function handleReadFile(req, res) {
    const body = await parseBody(req);
    const { path: filePath } = body;
    if (!filePath) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'path is required' }));
        return;
    }
    try {
        // Resolve path relative to workspace if not absolute
        let resolvedPath = filePath;
        if (!path.isAbsolute(filePath)) {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (workspaceFolders && workspaceFolders.length > 0) {
                resolvedPath = path.join(workspaceFolders[0].uri.fsPath, filePath);
            }
        }
        const content = fs.readFileSync(resolvedPath, 'utf-8');
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ content, path: resolvedPath }));
    }
    catch (error) {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: `File not found: ${error.message}` }));
    }
}
// Write file contents
async function handleWriteFile(req, res) {
    const body = await parseBody(req);
    const { path: filePath, content } = body;
    if (!filePath) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'path is required' }));
        return;
    }
    if (content === undefined) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'content is required' }));
        return;
    }
    try {
        // Resolve path relative to workspace if not absolute
        let resolvedPath = filePath;
        if (!path.isAbsolute(filePath)) {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (workspaceFolders && workspaceFolders.length > 0) {
                resolvedPath = path.join(workspaceFolders[0].uri.fsPath, filePath);
            }
        }
        // Ensure directory exists
        const dir = path.dirname(resolvedPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
        fs.writeFileSync(resolvedPath, content, 'utf-8');
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ success: true, path: resolvedPath }));
    }
    catch (error) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
    }
}
// List files in directory
async function handleListFiles(req, res) {
    const body = await parseBody(req);
    const { path: dirPath, pattern } = body;
    try {
        let resolvedPath = dirPath || '';
        // If no path provided, use workspace root
        if (!resolvedPath) {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (workspaceFolders && workspaceFolders.length > 0) {
                resolvedPath = workspaceFolders[0].uri.fsPath;
            }
            else {
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: 'No workspace open' }));
                return;
            }
        }
        else if (!path.isAbsolute(resolvedPath)) {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (workspaceFolders && workspaceFolders.length > 0) {
                resolvedPath = path.join(workspaceFolders[0].uri.fsPath, resolvedPath);
            }
        }
        const entries = fs.readdirSync(resolvedPath, { withFileTypes: true });
        const files = entries.map(entry => ({
            name: entry.name,
            path: path.join(resolvedPath, entry.name),
            isDirectory: entry.isDirectory(),
            isFile: entry.isFile()
        }));
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ files, path: resolvedPath }));
    }
    catch (error) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
    }
}
// Execute terminal command
async function handleTerminalExecute(req, res) {
    const body = await parseBody(req);
    const { command, cwd } = body;
    if (!command) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'command is required' }));
        return;
    }
    try {
        // Use child_process for actual execution
        const { exec } = require('child_process');
        let workingDir = cwd;
        if (!workingDir) {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (workspaceFolders && workspaceFolders.length > 0) {
                workingDir = workspaceFolders[0].uri.fsPath;
            }
        }
        exec(command, { cwd: workingDir, maxBuffer: 1024 * 1024 * 10 }, (error, stdout, stderr) => {
            if (error && !stdout && !stderr) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ error: error.message }));
                return;
            }
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                stdout,
                stderr,
                exitCode: error ? error.code : 0
            }));
        });
    }
    catch (error) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
    }
}
// Get workspace info
async function handleWorkspaceInfo(req, res) {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    const info = {
        workspaceFolders: workspaceFolders?.map(f => ({
            name: f.name,
            path: f.uri.fsPath
        })) || [],
        workspaceFile: vscode.workspace.workspaceFile?.fsPath
    };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(info));
}
// Shared file path for agent responses
function getAgentResponsesFilePath() {
    const homeDir = process.env.USERPROFILE || process.env.HOME || '';
    const suiteViewDir = path.join(homeDir, '.suiteview');
    if (!fs.existsSync(suiteViewDir)) {
        fs.mkdirSync(suiteViewDir, { recursive: true });
    }
    return path.join(suiteViewDir, 'agent_responses.jsonl');
}
// Handle agent chat - writes responses to shared file
async function handleAgentChat(req, res) {
    const body = await parseBody(req);
    const { messages, model, request_id } = body;
    if (!messages || !Array.isArray(messages)) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'messages array is required' }));
        return;
    }
    const reqId = request_id || `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    outputChannel.appendLine(`Agent chat request: ${reqId}, messages: ${messages.length}, model: ${model || 'default'}`);
    try {
        // Select a model
        let selectedModels = await vscode.lm.selectChatModels();
        if (model) {
            let filtered = selectedModels.filter(m => m.id === model);
            if (filtered.length === 0) {
                filtered = selectedModels.filter(m => m.id.toLowerCase() === model.toLowerCase());
            }
            if (filtered.length === 0) {
                filtered = selectedModels.filter(m => m.id.toLowerCase().includes(model.toLowerCase()) ||
                    m.family?.toLowerCase().includes(model.toLowerCase()) ||
                    m.name?.toLowerCase().includes(model.toLowerCase()));
            }
            if (filtered.length > 0) {
                selectedModels = filtered;
            }
        }
        if (selectedModels.length === 0) {
            res.writeHead(503, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: 'No language models available.' }));
            return;
        }
        const chatModel = selectedModels[0];
        outputChannel.appendLine(`Agent using model: ${chatModel.name} (${chatModel.id})`);
        // Convert messages to VS Code format
        const chatMessages = messages.map((m) => {
            if (m.role === 'user') {
                return vscode.LanguageModelChatMessage.User(m.content);
            }
            else if (m.role === 'assistant') {
                return vscode.LanguageModelChatMessage.Assistant(m.content);
            }
            else {
                return vscode.LanguageModelChatMessage.User(`[System]: ${m.content}`);
            }
        });
        // Send request to the model
        const response = await chatModel.sendRequest(chatMessages, {}, new vscode.CancellationTokenSource().token);
        // Collect full response
        let fullResponse = '';
        for await (const chunk of response.text) {
            fullResponse += chunk;
        }
        // Write to shared file
        const responseFilePath = getAgentResponsesFilePath();
        const responseEntry = {
            request_id: reqId,
            timestamp: new Date().toISOString(),
            model: chatModel.id,
            model_name: chatModel.name,
            prompt: messages[messages.length - 1]?.content || '',
            response: fullResponse,
            status: 'complete'
        };
        fs.appendFileSync(responseFilePath, JSON.stringify(responseEntry) + '\n', 'utf-8');
        outputChannel.appendLine(`Agent response written to: ${responseFilePath}`);
        // Also return the response via HTTP
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({
            request_id: reqId,
            model: chatModel.id,
            model_name: chatModel.name,
            response: fullResponse,
            response_file: responseFilePath
        }));
    }
    catch (error) {
        // Write error to shared file too
        const responseFilePath = getAgentResponsesFilePath();
        const errorEntry = {
            request_id: reqId,
            timestamp: new Date().toISOString(),
            model: model || 'unknown',
            prompt: messages[messages.length - 1]?.content || '',
            error: error.message,
            status: 'error'
        };
        fs.appendFileSync(responseFilePath, JSON.stringify(errorEntry) + '\n', 'utf-8');
        outputChannel.appendLine(`Agent chat error: ${error.message}`);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message, request_id: reqId }));
    }
}
// Get agent responses from shared file
async function handleGetAgentResponses(req, res) {
    const url = new URL(req.url || '', `http://${req.headers.host}`);
    const afterTimestamp = url.searchParams.get('after');
    const requestId = url.searchParams.get('request_id');
    const limit = parseInt(url.searchParams.get('limit') || '100', 10);
    try {
        const responseFilePath = getAgentResponsesFilePath();
        if (!fs.existsSync(responseFilePath)) {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ responses: [], file_path: responseFilePath }));
            return;
        }
        const content = fs.readFileSync(responseFilePath, 'utf-8');
        const lines = content.trim().split('\n').filter(line => line);
        let responses = lines.map(line => {
            try {
                return JSON.parse(line);
            }
            catch {
                return null;
            }
        }).filter(r => r !== null);
        // Filter by timestamp if provided
        if (afterTimestamp) {
            responses = responses.filter(r => r.timestamp > afterTimestamp);
        }
        // Filter by request_id if provided
        if (requestId) {
            responses = responses.filter(r => r.request_id === requestId);
        }
        // Limit results
        responses = responses.slice(-limit);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            responses,
            count: responses.length,
            file_path: responseFilePath
        }));
    }
    catch (error) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: error.message }));
    }
}
// ============================================
// OpenAI-Compatible API Endpoints
// ============================================
// OpenAI-compatible /v1/models endpoint
async function handleOpenAIModels(req, res) {
    try {
        const allModels = await vscode.lm.selectChatModels();
        // Convert to OpenAI format
        const openAIModels = allModels.map(m => ({
            id: m.id,
            object: 'model',
            created: Math.floor(Date.now() / 1000),
            owned_by: m.vendor || 'vscode',
            permission: [{
                    id: `modelperm-${m.id}`,
                    object: 'model_permission',
                    created: Math.floor(Date.now() / 1000),
                    allow_create_engine: false,
                    allow_sampling: true,
                    allow_logprobs: false,
                    allow_search_indices: false,
                    allow_view: true,
                    allow_fine_tuning: false,
                    organization: '*',
                    group: null,
                    is_blocking: false
                }],
            root: m.id,
            parent: null,
            // Additional metadata (non-standard but useful)
            _vscode_metadata: {
                name: m.name,
                family: m.family,
                version: m.version,
                maxInputTokens: m.maxInputTokens
            }
        }));
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            object: 'list',
            data: openAIModels
        }));
    }
    catch (error) {
        outputChannel.appendLine(`OpenAI models error: ${error.message}`);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            error: {
                message: error.message,
                type: 'server_error',
                code: 'internal_error'
            }
        }));
    }
}
// OpenAI-compatible /v1/chat/completions endpoint
async function handleOpenAIChatCompletions(req, res) {
    const body = await parseBody(req);
    const { messages, model, stream = false, temperature, max_tokens, top_p, n = 1, stop, presence_penalty, frequency_penalty, user } = body;
    if (!messages || !Array.isArray(messages)) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            error: {
                message: 'messages is required and must be an array',
                type: 'invalid_request_error',
                param: 'messages',
                code: 'invalid_type'
            }
        }));
        return;
    }
    const requestId = `chatcmpl-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    outputChannel.appendLine(`OpenAI Chat request [${requestId}]: ${messages.length} messages, model: ${model || 'default'}, stream: ${stream}`);
    try {
        // Select a model
        let selectedModels = await vscode.lm.selectChatModels();
        outputChannel.appendLine(`=== OPENAI CHAT REQUEST ===`);
        outputChannel.appendLine(`Requested model: "${model}"`);
        outputChannel.appendLine(`Available models (${selectedModels.length}): ${selectedModels.map(m => m.id).join(', ')}`);
        if (model) {
            // Try exact match first
            let filtered = selectedModels.filter(m => m.id === model);
            // If no exact match, try case-insensitive
            if (filtered.length === 0) {
                filtered = selectedModels.filter(m => m.id.toLowerCase() === model.toLowerCase());
            }
            // If still no match, try partial match
            if (filtered.length === 0) {
                filtered = selectedModels.filter(m => m.id.toLowerCase().includes(model.toLowerCase()) ||
                    m.family?.toLowerCase().includes(model.toLowerCase()) ||
                    m.name?.toLowerCase().includes(model.toLowerCase()));
            }
            if (filtered.length > 0) {
                selectedModels = filtered;
                outputChannel.appendLine(`>>> USING MODEL: ${selectedModels[0].id}`);
            }
            else {
                outputChannel.appendLine(`>>> Model "${model}" not found, using default: ${selectedModels[0].id}`);
            }
        }
        if (selectedModels.length === 0) {
            res.writeHead(503, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                error: {
                    message: 'No language models available. Make sure GitHub Copilot is enabled.',
                    type: 'server_error',
                    code: 'model_not_available'
                }
            }));
            return;
        }
        const chatModel = selectedModels[0];
        outputChannel.appendLine(`Using model: ${chatModel.name} (${chatModel.id})`);
        // Convert messages to VS Code format
        const chatMessages = messages.map((m) => {
            if (m.role === 'user') {
                // Handle content that could be string or array (multimodal)
                const content = typeof m.content === 'string'
                    ? m.content
                    : m.content.map((c) => c.type === 'text' ? c.text : '').join('\n');
                return vscode.LanguageModelChatMessage.User(content);
            }
            else if (m.role === 'assistant') {
                const content = typeof m.content === 'string' ? m.content : '';
                return vscode.LanguageModelChatMessage.Assistant(content);
            }
            else if (m.role === 'system') {
                // System messages are prepended as user context
                return vscode.LanguageModelChatMessage.User(`[System]: ${m.content}`);
            }
            else {
                // Function/tool messages - treat as user context
                return vscode.LanguageModelChatMessage.User(`[${m.role}]: ${JSON.stringify(m.content)}`);
            }
        });
        // Send request to the model
        const response = await chatModel.sendRequest(chatMessages, {}, new vscode.CancellationTokenSource().token);
        const created = Math.floor(Date.now() / 1000);
        if (stream) {
            // Streaming response (SSE format)
            res.writeHead(200, {
                'Content-Type': 'text/event-stream; charset=utf-8',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            });
            let totalTokens = 0;
            for await (const chunk of response.text) {
                totalTokens += chunk.length; // Rough estimate
                const streamChunk = {
                    id: requestId,
                    object: 'chat.completion.chunk',
                    created: created,
                    model: chatModel.id,
                    choices: [{
                            index: 0,
                            delta: {
                                content: chunk
                            },
                            finish_reason: null
                        }]
                };
                res.write(`data: ${JSON.stringify(streamChunk)}\n\n`);
            }
            // Send final chunk with finish_reason
            const finalChunk = {
                id: requestId,
                object: 'chat.completion.chunk',
                created: created,
                model: chatModel.id,
                choices: [{
                        index: 0,
                        delta: {},
                        finish_reason: 'stop'
                    }]
            };
            res.write(`data: ${JSON.stringify(finalChunk)}\n\n`);
            res.write('data: [DONE]\n\n');
            res.end();
        }
        else {
            // Non-streaming response - collect all chunks
            let fullResponse = '';
            for await (const chunk of response.text) {
                fullResponse += chunk;
            }
            // Estimate token counts (rough approximation)
            const promptTokens = messages.reduce((acc, m) => {
                const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content);
                return acc + Math.ceil(content.length / 4);
            }, 0);
            const completionTokens = Math.ceil(fullResponse.length / 4);
            const completionResponse = {
                id: requestId,
                object: 'chat.completion',
                created: created,
                model: chatModel.id,
                choices: [{
                        index: 0,
                        message: {
                            role: 'assistant',
                            content: fullResponse
                        },
                        finish_reason: 'stop'
                    }],
                usage: {
                    prompt_tokens: promptTokens,
                    completion_tokens: completionTokens,
                    total_tokens: promptTokens + completionTokens
                }
            };
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(completionResponse));
        }
        outputChannel.appendLine(`OpenAI chat request [${requestId}] completed successfully`);
    }
    catch (error) {
        outputChannel.appendLine(`OpenAI chat error: ${error.message}`);
        // Map errors to OpenAI error format
        let statusCode = 500;
        let errorType = 'server_error';
        let errorCode = 'internal_error';
        if (error.message.includes('not authenticated') || error.message.includes('sign in')) {
            statusCode = 401;
            errorType = 'authentication_error';
            errorCode = 'invalid_api_key';
        }
        else if (error.message.includes('rate limit')) {
            statusCode = 429;
            errorType = 'rate_limit_error';
            errorCode = 'rate_limit_exceeded';
        }
        res.writeHead(statusCode, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            error: {
                message: error.message,
                type: errorType,
                code: errorCode
            }
        }));
    }
}
//# sourceMappingURL=extension.js.map