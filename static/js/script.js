// Modern Terminal Interface Script
const terminalForm = document.getElementById('terminal-form');
const terminalInput = document.getElementById('terminal-input');
const terminalSubmit = document.getElementById('terminal-submit');
const terminalMessages = document.getElementById('terminal-messages');
const welcomeMessage = document.getElementById('welcome-message');
const menuBtn = document.getElementById('menu-btn');
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('overlay');

// Cluster modal elements
const newClusterBtn = document.getElementById('new-cluster-btn');
const clusterModal = document.getElementById('cluster-modal');
const closeModal = document.getElementById('close-modal');
const cancelCluster = document.getElementById('cancel-cluster');
const clusterForm = document.getElementById('cluster-form');
const clusterError = document.getElementById('cluster-error');
const clusterErrorMessage = document.getElementById('cluster-error-message');

// Current session state
let currentSessionId = null;
let currentClusterName = null;
let currentPath = '~';
let commandHistory = [];
let historyIndex = 0;
let currentCommandAbortController = null;

// Event listeners
terminalForm.addEventListener('submit', handleExecuteCommand);
terminalInput.addEventListener('input', autoResizeTextarea);
terminalInput.addEventListener('keydown', handleKeydown);
newClusterBtn.addEventListener('click', showClusterModal);
closeModal.addEventListener('click', hideClusterModal);
cancelCluster.addEventListener('click', hideClusterModal);
clusterForm.addEventListener('submit', handleCreateCluster);

// Mobile menu
if (menuBtn) {
menuBtn.addEventListener('click', toggleSidebar);
}
if (overlay) {
overlay.addEventListener('click', toggleSidebar);
}

// Cluster session clicks
document.addEventListener('click', (e) => {
    if (e.target.closest('.cluster-session')) {
        e.preventDefault();
        const sessionElement = e.target.closest('.cluster-session');
        const sessionId = sessionElement.dataset.sessionId;
        const clusterName = sessionElement.dataset.clusterName;
        switchToSession(sessionId, clusterName);
    }
});

// Modal click outside to close
clusterModal.addEventListener('click', (e) => {
    if (e.target === clusterModal) {
        hideClusterModal();
    }
});

function handleExecuteCommand(e) {
  e.preventDefault();
    const command = terminalInput.value.trim();
    
    if (!command || !currentSessionId) return;
    
    // Show command in terminal
    appendTerminalMessage('command', command);
    
    // Clear input
    terminalInput.value = '';
  autoResizeTextarea();
    
    // Disable input while processing
    setTerminalInputState(false);
    
    // Add to command history
    if (command.trim() && commandHistory[commandHistory.length - 1] !== command) {
        commandHistory.push(command);
        historyIndex = commandHistory.length;
    }
    
    // Handle special interactive commands first
    console.log('Checking command:', command);
    if (command.startsWith('vim ') || command === 'vim' || command.startsWith('vi ') || command === 'vi') {
        console.log('Handling vim command:', command);
        handleVimCommand(command);
        return;
    }
    
    if (command.startsWith('nano ') || command === 'nano') {
        handleNanoCommand(command);
        return;
    }
    
    // Execute regular command
    executeCommand(command);
}

function handleVimCommand(command) {
    console.log('handleVimCommand called with:', command);
    const parts = command.split(' ');
    const filename = parts.length > 1 ? parts[1] : 'untitled';
    
    // Create vim editor directly (command already shown)
    console.log('Creating vim editor for:', filename);
    createVimEditor(filename);
}

function handleNanoCommand(command) {
    const parts = command.split(' ');
    const filename = parts.length > 1 ? parts[1] : 'untitled';
    
    // Create nano editor directly (command already shown)
    createNanoEditor(filename);
}

function createVimEditor(filename) {
    console.log('createVimEditor called for:', filename);
    
    // First try to read file content (only if file might exist)
    fetch(`/terminal/${currentSessionId}/execute/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ command: `test -f "${filename}" && cat "${filename}" || echo ""` })
    })
    .then(response => response.json())
    .then(data => {
        const content = data.success ? data.output : '';
        console.log('File content loaded, showing vim editor');
        showVimEditor(filename, content);
    })
    .catch((error) => {
        console.log('Error loading file, showing empty vim editor:', error);
        showVimEditor(filename, '');
    });
}

function createNanoEditor(filename) {
    // First try to read file content (handle non-existent files gracefully)
    fetch(`/terminal/${currentSessionId}/execute/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ command: `test -f "${filename}" && cat "${filename}" || echo ""` })
    })
    .then(response => response.json())
    .then(data => {
        const content = data.success ? data.output : '';
        showNanoEditor(filename, content);
    })
    .catch(() => {
        showNanoEditor(filename, '');
    });
}

function showVimEditor(filename, content) {
    console.log('showVimEditor called for:', filename, 'with content length:', content.length);
    
    const editorHTML = `
        <div id="vim-editor" class="fixed inset-0 bg-slate-900 z-50 font-mono text-blue-300">
            <div class="h-full flex flex-col">
                <!-- Vim header -->
                <div class="bg-slate-800 text-blue-300 px-4 py-2 text-sm border-b border-blue-500/30">
                    <div class="flex items-center justify-between">
                        <span>"${filename}" ${content ? `${content.split('\\n').length}L, ${content.length}C` : '[New File]'}</span>
                        <button id="vim-close-btn" class="text-blue-400 hover:text-blue-300 px-2">✕</button>
                    </div>
                </div>
                
                <!-- Editor content -->
                <div class="flex-1 relative">
                    <textarea 
                        id="vim-content" 
                        class="w-full h-full bg-slate-900 text-blue-100 font-mono text-sm p-4 outline-none resize-none border-none"
                        style="line-height: 1.5; caret-color: transparent;"
                        readonly
                    >${content}</textarea>
                </div>
                
                <!-- Vim command line -->
                <div class="bg-slate-800 text-blue-300 px-4 py-2 text-sm border-t border-blue-500/30">
                    <div id="vim-status">
                        <span id="vim-mode" class="text-blue-400 font-semibold">-- NORMAL --</span>
                        <span class="float-right text-slate-400 text-xs">i: Insert | :w: Save | :q: Quit | :wq: Save&Quit | ESC: Exit</span>
                    </div>
                    <div id="vim-command-line" class="hidden">
                        :<input id="vim-command-input" class="bg-slate-800 text-blue-300 outline-none border-none ml-1" style="width: calc(100% - 20px);">
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', editorHTML);
    
    const editor = document.getElementById('vim-content');
    const modeDisplay = document.getElementById('vim-mode');
    const statusDiv = document.getElementById('vim-status');
    const commandLineDiv = document.getElementById('vim-command-line');
    const commandInput = document.getElementById('vim-command-input');
    const closeBtn = document.getElementById('vim-close-btn');
    
    let isInsertMode = false;
    let isCommandMode = false;
    
    // Add close button functionality
    closeBtn.addEventListener('click', () => {
        closeEditor('vim');
    });
    
    editor.focus();
    
    let showLineNumbers = false;
    let searchTerm = '';
    let lastSearchIndex = -1;
    
    editor.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            e.preventDefault();
            if (isCommandMode) {
                // Exit command mode
                isCommandMode = false;
                statusDiv.classList.remove('hidden');
                commandLineDiv.classList.add('hidden');
                editor.focus();
            } else if (isInsertMode) {
                // Exit insert mode
                isInsertMode = false;
                modeDisplay.textContent = '-- NORMAL --';
                modeDisplay.className = 'text-blue-400 font-semibold';
                editor.style.caretColor = 'transparent';
                editor.setAttribute('readonly', true);
            }
        } else if (!isInsertMode && !isCommandMode) {
            // Normal mode commands
            if (e.key === 'i') {
                e.preventDefault();
                isInsertMode = true;
                modeDisplay.textContent = '-- INSERT --';
                modeDisplay.className = 'text-green-400 font-semibold';
                editor.style.caretColor = '#60a5fa';
                editor.removeAttribute('readonly');
            } else if (e.key === ':') {
                e.preventDefault();
                isCommandMode = true;
                statusDiv.classList.add('hidden');
                commandLineDiv.classList.remove('hidden');
                commandInput.value = '';
                commandInput.focus();
            } else if (e.key === '/') {
                e.preventDefault();
                isCommandMode = true;
                statusDiv.classList.add('hidden');
                commandLineDiv.classList.remove('hidden');
                commandInput.value = '/';
                commandInput.focus();
            } else if (e.key === 'n' && searchTerm) {
                e.preventDefault();
                findNextInVim(editor, searchTerm, true);
            } else if (e.key === 'N' && searchTerm) {
                e.preventDefault();
                findNextInVim(editor, searchTerm, false);
            } else if (e.key === 'q') {
                e.preventDefault();
                closeEditor('vim');
            } else if (e.key === 'u') {
                e.preventDefault();
                document.execCommand('undo');
            } else if (e.key === 'dd') {
                e.preventDefault();
                deleteCurrentLine(editor);
            }
        }
    });
    
    // Handle vim command input
    commandInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const command = commandInput.value.trim();
            
            if (command.startsWith('/')) {
                // Search command
                const searchQuery = command.substring(1);
                if (searchQuery) {
                    searchTerm = searchQuery;
                    findNextInVim(editor, searchTerm, true);
                }
                isCommandMode = false;
                statusDiv.classList.remove('hidden');
                commandLineDiv.classList.add('hidden');
                editor.focus();
            } else {
                executeVimCommand(command, filename, editor.value, showLineNumbers);
            }
        } else if (e.key === 'Escape') {
            e.preventDefault();
            isCommandMode = false;
            statusDiv.classList.remove('hidden');
            commandLineDiv.classList.add('hidden');
            editor.focus();
        }
    });
}

function showNanoEditor(filename, content) {
    const editorHTML = `
        <div id="nano-editor" class="fixed inset-0 bg-slate-900 z-50 font-mono text-blue-100">
            <div class="h-full flex flex-col">
                <!-- Nano header -->
                <div class="bg-slate-800 text-blue-300 px-4 py-2 text-sm border-b border-blue-500/30">
                    <div class="flex justify-between items-center">
                        <span>GNU nano 6.2</span>
                        <span>File: ${filename}</span>
                        <span id="nano-modified-status" class="text-yellow-400">Modified</span>
                        <button id="nano-close-btn" class="text-blue-400 hover:text-blue-300 px-2">✕</button>
                    </div>
                </div>
                
                <!-- Editor content -->
                <div class="flex-1 relative">
                    <textarea 
                        id="nano-content" 
                        class="w-full h-full bg-slate-900 text-blue-100 font-mono text-sm p-4 outline-none resize-none border-none"
                        style="line-height: 1.5; caret-color: #60a5fa;"
                    >${content}</textarea>
                </div>
                
                <!-- Nano exit/save prompt (hidden by default) -->
                <div id="nano-exit-prompt" class="hidden bg-slate-700 text-blue-200 px-4 py-2 text-sm border-t border-blue-500/30">
                    <div>Save modified buffer (ANSWERING "No" WILL DESTROY CHANGES) ?</div>
                    <div class="mt-1">
                        <span id="nano-yes-option" class="mr-4 cursor-pointer hover:text-blue-100">Y Yes</span>
                        <span id="nano-no-option" class="mr-4 cursor-pointer hover:text-blue-100">N No</span>
                        <span id="nano-cancel-option" class="cursor-pointer hover:text-blue-100">^C Cancel</span>
                    </div>
                </div>
                
                <!-- Nano shortcuts -->
                <div class="bg-slate-800 text-blue-300 px-4 py-2 text-xs border-t border-blue-500/30">
                    <div class="grid grid-cols-2 gap-4">
                        <div>^G Get Help &nbsp; ^O WriteOut &nbsp; ^R Read File &nbsp; ^Y Prev Pg &nbsp; ^K Cut Text &nbsp; ^C Cur Pos</div>
                        <div>^X Exit &nbsp; ^J Justify &nbsp; ^W Where is &nbsp; ^V Next Pg &nbsp; ^U UnCut Text &nbsp; ^T To Spell</div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', editorHTML);
    
    const editor = document.getElementById('nano-content');
    const closeBtn = document.getElementById('nano-close-btn');
    
    // Store original content for comparison
    editor.originalContent = content;
    
    // Add close button functionality
    closeBtn.addEventListener('click', () => {
        closeEditor('nano');
    });
    
    // Update modified status on content change
    editor.addEventListener('input', () => {
        const modifiedStatus = document.getElementById('nano-modified-status');
        if (editor.value !== editor.originalContent) {
            modifiedStatus.textContent = 'Modified';
        } else {
            modifiedStatus.textContent = '';
        }
    });
    
    editor.focus();
    
    editor.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'x') {
            e.preventDefault();
            // Check if file is modified like real nano
            if (editor.value !== editor.originalContent) {
                showNanoRealExitPrompt(filename, editor.value);
            } else {
                closeEditor('nano');
            }
        } else if (e.ctrlKey && e.key === 'o') {
            e.preventDefault();
            saveNanoFileDirect(filename, editor.value);
        } else if (e.ctrlKey && e.key === 'g') {
            e.preventDefault();
            showNanoHelp();
        } else if (e.ctrlKey && e.key === 'w') {
            e.preventDefault();
            showNanoSearch(editor);
        } else if (e.ctrlKey && e.key === 'k') {
            e.preventDefault();
            cutNanoLine(editor);
        } else if (e.ctrlKey && e.key === 'u') {
            e.preventDefault();
            pasteNanoLine(editor);
        } else if (e.ctrlKey && e.key === 'r') {
            e.preventDefault();
            insertFile(editor);
        } else if (e.ctrlKey && e.key === 'j') {
            e.preventDefault();
            justifyText(editor);
        } else if (e.ctrlKey && e.key === 'y') {
            e.preventDefault();
            pageUp(editor);
        } else if (e.ctrlKey && e.key === 'v') {
            e.preventDefault();
            pageDown(editor);
        } else if (e.ctrlKey && e.key === 'c') {
            e.preventDefault();
            showCursorPosition(editor);
        } else if (e.ctrlKey && e.key === 't') {
            e.preventDefault();
            spellCheck(editor);
        }
    });
}

function executeVimCommand(command, filename, content, showLineNumbers) {
    console.log('Executing vim command:', command);
    const statusDiv = document.getElementById('vim-status');
    const commandLineDiv = document.getElementById('vim-command-line');
    const editor = document.getElementById('vim-content');
    
    // Hide command line
    statusDiv.classList.remove('hidden');
    commandLineDiv.classList.add('hidden');
    
    if (command === 'w' || command === 'write' || command === 'w!') {
        saveFile(filename, content, false);
    } else if (command === 'q' || command === 'quit') {
        closeEditor('vim');
        setTerminalInputState(true);
    } else if (command === 'wq' || command === 'x' || command === 'wq!' || command === 'x!') {
        console.log('Save and quit command detected');
        saveFile(filename, content, true);
    } else if (command === 'q!' || command === 'quit!') {
        console.log('Force quit command detected');
        closeEditor('vim');
        setTerminalInputState(true);
    } else if (command === 'set number' || command === 'set nu') {
        toggleLineNumbers(editor, true);
    } else if (command === 'set nonumber' || command === 'set nonu') {
        toggleLineNumbers(editor, false);
    } else if (command.startsWith('set ')) {
        handleVimSetCommand(command, editor);
    } else if (command.match(/^\d+$/)) {
        // Go to line number
        goToLine(editor, parseInt(command));
    } else {
        console.log('Unknown vim command:', command);
        // Show error like real vim
        const modeDisplay = document.getElementById('vim-mode');
        if (modeDisplay) {
            const originalText = modeDisplay.textContent;
            modeDisplay.textContent = `E492: Not an editor command: ${command}`;
            setTimeout(() => {
                modeDisplay.textContent = originalText;
            }, 2000);
        }
    }
    
    if (editor) {
        editor.focus();
    }
}

function saveFile(filename, content, andQuit = false) {
    // Use a more reliable method to write files
    const escapedContent = content.replace(/'/g, "'\"'\"'");
    
    fetch(`/terminal/${currentSessionId}/execute/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ 
            command: `printf '%s' '${escapedContent}' > "${filename}"` 
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show save confirmation in vim editor status
            const vimMode = document.getElementById('vim-mode');
            if (vimMode) {
                vimMode.textContent = `"${filename}" written`;
  setTimeout(() => {
                    vimMode.textContent = '-- NORMAL --';
                }, 2000);
            }
            
                        if (andQuit) {
                console.log('Saving and quitting editor');
                setTimeout(() => {
                    closeEditor('vim');
                    closeEditor('nano');
                    setTerminalInputState(true);
                    console.log('Editor closed after save');
                }, 100);
            }
        } else {
            const vimMode = document.getElementById('vim-mode');
            if (vimMode) {
                vimMode.textContent = `Error: Could not save "${filename}"`;
                setTimeout(() => {
                    vimMode.textContent = '-- NORMAL --';
                }, 3000);
            }
        }
    })
    .catch(error => {
        console.error('Save error:', error);
        const vimMode = document.getElementById('vim-mode');
        if (vimMode) {
            vimMode.textContent = 'Error: Save failed';
            setTimeout(() => {
                vimMode.textContent = '-- NORMAL --';
            }, 3000);
        }
    });
}

function closeEditor(type) {
    console.log('Closing editor:', type);
    const editor = document.getElementById(`${type}-editor`);
    if (editor) {
        editor.remove();
        console.log('Editor removed');
    }
    
    // Re-enable terminal input and focus
    setTerminalInputState(true);
    console.log('Terminal input state enabled');
    
    // Focus back on terminal input with longer delay
    setTimeout(() => {
        const terminalInput = document.getElementById('terminal-input');
        if (terminalInput) {
            terminalInput.focus();
            console.log('Terminal input focused');
        }
    }, 200);
}

function interruptCurrentCommand() {
    if (currentCommandAbortController) {
        currentCommandAbortController.abort();
        currentCommandAbortController = null;
        appendTerminalMessage('info', '^C');
        setTerminalInputState(true);
    }
}

async function executeCommand(command, silent = false) {
    try {
        // Create abort controller for this command
        currentCommandAbortController = new AbortController();
        
        const response = await fetch(`/terminal/${currentSessionId}/execute/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ command: command }),
            signal: currentCommandAbortController.signal
        });
        
        const data = await response.json();
        
        if (!silent) {
            if (data.success) {
                // Handle clear command
                if (data.clear) {
                    const currentSession = document.getElementById('current-session');
                    if (currentSession) {
                        currentSession.innerHTML = '';
                    } else {
                        terminalMessages.innerHTML = '';
                    }
                } else if (data.output.trim()) {
                    appendTerminalMessage('output', data.output, data.exit_code);
                }
                
                // Update path if it was a cd command
                if (command.startsWith('cd ')) {
                    updateCurrentPath();
                }
            } else {
                appendTerminalMessage('error', data.error || 'Command failed');
            }
        }
        
        return data;
        
    } catch (error) {
        if (error.name === 'AbortError') {
            if (!silent) {
                appendTerminalMessage('info', 'Command interrupted');
            }
            return { success: false, error: 'interrupted' };
        } else if (!silent) {
            appendTerminalMessage('error', `Network error: ${error.message}`);
        }
        return { success: false, error: error.message };
    } finally {
        currentCommandAbortController = null;
        if (!silent) {
            setTerminalInputState(true);
        }
    }
}

function appendTerminalMessage(type, content, exitCode = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'terminal-message mb-4';
    
    let messageHTML = '';
    
    switch (type) {
        case 'command':
            messageHTML = `
                <div class="text-blue-300 font-mono">
                    <span class="text-blue-400">user@k8s-terminal:~$</span> <span class="text-blue-100">${escapeHtml(content)}</span>
                </div>
            `;
            break;
        
        case 'output':
            const exitClass = exitCode === 0 ? 'text-blue-200' : 'text-red-400';
            messageHTML = `
                <div class="${exitClass} font-mono whitespace-pre-wrap">
                    ${escapeHtml(content)}
                </div>
            `;
            break;
        
        case 'error':
            messageHTML = `
                <div class="text-red-400 font-mono whitespace-pre-wrap">
                    ${escapeHtml(content)}
                </div>
            `;
            break;
        

        
        case 'info':
            messageHTML = `
                <div class="text-blue-300 font-mono">
                    ${escapeHtml(content)}
                </div>
            `;
            break;
            
        case 'success':
            messageHTML = `
                <div class="text-emerald-400 font-mono">
                    ${escapeHtml(content)}
                </div>
            `;
            break;
    }
    
    messageDiv.innerHTML = messageHTML;
    
    // Append to current session instead of terminal messages directly
    const currentSession = document.getElementById('current-session');
    if (currentSession) {
        currentSession.appendChild(messageDiv);
    } else {
        terminalMessages.appendChild(messageDiv);
    }
    
    // Auto-scroll to bottom
    autoScrollToBottom();
}

async function updateCurrentPath() {
    try {
        const result = await executeCommand('pwd', true);
        if (result.success && result.output.trim()) {
            currentPath = result.output.trim().replace(/^\/home\/[^\/]*/, '~');
        }
    } catch (error) {
        console.error('Failed to update path:', error);
    }
}

async function switchToSession(sessionId, clusterName) {
    currentSessionId = sessionId;
    currentClusterName = clusterName;
    currentPath = '~';
    
    // Update UI
    welcomeMessage.style.display = 'none';
    const terminalContainer = document.getElementById('terminal-container');
    if (terminalContainer) {
        terminalContainer.classList.remove('hidden');
    }
    // Clear current session but preserve old history
    const currentSession = document.getElementById('current-session');
    if (currentSession) {
        currentSession.innerHTML = '';
    } else {
        terminalMessages.innerHTML = '';
    }
    
    // Enable terminal input
    setTerminalInputState(true);
    
    // Initialize scroll button now that terminal is visible
    initializeScrollToBottom();
    
    // Update active session in sidebar
    document.querySelectorAll('.cluster-session').forEach(session => {
        session.classList.remove('bg-white/5');
    });
    document.querySelector(`[data-session-id="${sessionId}"]`).classList.add('bg-white/5');
    
    // Load command history first (this will populate old history and show toggle button)
    await loadCommandHistory(sessionId);
    
    // Show welcome message in current session
    appendTerminalMessage('info', `Connected to ${clusterName}. Terminal ready.`);
    appendTerminalMessage('info', `Type 'help' for available commands.`);
    
    // Focus on input
    terminalInput.focus();
}

async function loadCommandHistory(sessionId) {
    try {
        const response = await fetch(`/terminal/${sessionId}/history/`);
        const data = await response.json();
        
        if (data.success && data.history.length > 0) {
            // Load previous commands into old history (hidden by default)
            const oldHistory = document.getElementById('old-history');
            const historyToggleBtn = document.getElementById('history-toggle-btn');
            
            if (oldHistory && data.history.length > 0) {
                // Add separator
                const separatorDiv = document.createElement('div');
                separatorDiv.className = 'text-blue-500 text-xs border-b border-blue-800/30 pb-2 mb-4';
                separatorDiv.textContent = '--- Previous Session ---';
                oldHistory.appendChild(separatorDiv);
                
                // Add previous commands to old history (last 10)
                data.history.slice(-10).forEach(cmd => {
                    // Create command message
                    const cmdDiv = document.createElement('div');
                    cmdDiv.className = 'terminal-message mb-4';
                    cmdDiv.innerHTML = `
                        <div class="text-blue-300 font-mono">
                            <span class="text-blue-400">user@k8s-terminal:~$</span> <span class="text-blue-100">${escapeHtml(cmd.command)}</span>
                        </div>
                    `;
                    oldHistory.appendChild(cmdDiv);
                    
                    // Add output if exists
                    if (cmd.output.trim()) {
                        const outputDiv = document.createElement('div');
                        outputDiv.className = 'terminal-message mb-4';
                        const exitClass = cmd.exit_code === 0 ? 'text-blue-200' : 'text-red-400';
                        outputDiv.innerHTML = `
                            <div class="${exitClass} font-mono whitespace-pre-wrap">
                                ${escapeHtml(cmd.output)}
                            </div>
                        `;
                        oldHistory.appendChild(outputDiv);
                    }
                });
                
                // Show history toggle button
                if (historyToggleBtn) {
                    historyToggleBtn.classList.remove('hidden');
                }
                
                // Make sure old history starts hidden
                oldHistory.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Failed to load command history:', error);
    }
}

function setTerminalInputState(enabled) {
    console.log('Setting terminal input state:', enabled);
    const terminalInput = document.getElementById('terminal-input');
    const terminalSubmit = document.getElementById('terminal-submit');
    
    if (terminalInput) {
        terminalInput.disabled = !enabled;
    }
    if (terminalSubmit) {
        terminalSubmit.disabled = !enabled;
    }
    
    if (enabled && terminalInput) {
        terminalInput.placeholder = '';
        setTimeout(() => {
            terminalInput.focus();
            console.log('Terminal input focused and ready');
        }, 100);
    } else if (terminalInput) {
        terminalInput.placeholder = 'Processing...';
    }
}

// Cluster modal functions
function showClusterModal() {
    clusterModal.classList.remove('hidden');
    hideClusterError();
    document.getElementById('cluster-name').focus();
}

function hideClusterModal() {
    clusterModal.classList.add('hidden');
    clusterForm.reset();
    hideClusterError();
    setClusterFormState(true);
}

function showClusterError(message) {
    clusterErrorMessage.textContent = message;
    clusterError.classList.remove('hidden');
}

function hideClusterError() {
    clusterError.classList.add('hidden');
}

function setClusterFormState(enabled) {
    const inputs = clusterForm.querySelectorAll('input, textarea, button');
    inputs.forEach(input => {
        input.disabled = !enabled;
    });
    
    const createClusterText = document.getElementById('create-cluster-text');
    const createClusterLoading = document.getElementById('create-cluster-loading');
    
    if (enabled) {
        createClusterText.classList.remove('hidden');
        createClusterLoading.classList.add('hidden');
    } else {
        createClusterText.classList.add('hidden');
        createClusterLoading.classList.remove('hidden');
    }
}

async function handleCreateCluster(e) {
    e.preventDefault();
    
    const formData = new FormData(clusterForm);
    const clusterData = {
        name: formData.get('name'),
        kubeconfig: formData.get('kubeconfig')
    };
    
    setClusterFormState(false);
    hideClusterError();
    
    try {
        const response = await fetch('/clusters/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(clusterData)
        });
        
        const data = await response.json();
        
        if (data.success) {
            hideClusterModal();
            window.location.reload();
        } else {
            showClusterError(data.error || 'Failed to create cluster');
        }
        
    } catch (error) {
        showClusterError(`Network error: ${error.message}`);
    } finally {
        setClusterFormState(true);
    }
}

// Utility functions
function autoResizeTextarea() {
    terminalInput.style.height = 'auto';
    terminalInput.style.height = terminalInput.scrollHeight + 'px';
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
        terminalForm.dispatchEvent(new Event('submit'));
    } else if (e.ctrlKey && e.key === 'c') {
        e.preventDefault();
        // Send interrupt signal
        interruptCurrentCommand();
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (historyIndex > 0) {
            historyIndex--;
            terminalInput.value = commandHistory[historyIndex] || '';
        }
    } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (historyIndex < commandHistory.length - 1) {
            historyIndex++;
            terminalInput.value = commandHistory[historyIndex] || '';
  } else {
            historyIndex = commandHistory.length;
            terminalInput.value = '';
  }
}
}

function toggleSidebar() {
  sidebar.classList.toggle('-translate-x-full');
  overlay.classList.toggle('hidden');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

// Nano-specific functions
let nanoCutBuffer = '';

// Vim helper functions
function findNextInVim(editor, searchTerm, forward = true) {
    const content = editor.value;
    const currentPos = editor.selectionStart;
    
    let index;
    if (forward) {
        index = content.toLowerCase().indexOf(searchTerm.toLowerCase(), currentPos + 1);
        if (index === -1) {
            // Wrap around
            index = content.toLowerCase().indexOf(searchTerm.toLowerCase(), 0);
        }
    } else {
        const beforeCursor = content.substring(0, currentPos);
        index = beforeCursor.toLowerCase().lastIndexOf(searchTerm.toLowerCase());
        if (index === -1) {
            // Wrap around
            index = content.toLowerCase().lastIndexOf(searchTerm.toLowerCase());
        }
    }
    
    if (index !== -1) {
        editor.setSelectionRange(index, index + searchTerm.length);
        editor.focus();
        
        // Show search result in status
        const modeDisplay = document.getElementById('vim-mode');
        if (modeDisplay) {
            const originalText = modeDisplay.textContent;
            modeDisplay.textContent = `Found: ${searchTerm}`;
            setTimeout(() => {
                modeDisplay.textContent = originalText;
            }, 1500);
        }
    } else {
        // Show not found message
        const modeDisplay = document.getElementById('vim-mode');
        if (modeDisplay) {
            const originalText = modeDisplay.textContent;
            modeDisplay.textContent = `E486: Pattern not found: ${searchTerm}`;
            setTimeout(() => {
                modeDisplay.textContent = originalText;
            }, 2000);
        }
    }
}

function toggleLineNumbers(editor, show) {
    const lines = editor.value.split('\n');
    
    if (show) {
        // Add line numbers
        const numberedLines = lines.map((line, index) => {
            const lineNum = (index + 1).toString().padStart(4, ' ');
            return `${lineNum} ${line}`;
        });
        editor.value = numberedLines.join('\n');
    } else {
        // Remove line numbers
        const unnumberedLines = lines.map(line => {
            return line.replace(/^\s*\d+\s/, '');
        });
        editor.value = unnumberedLines.join('\n');
    }
}

function handleVimSetCommand(command, editor) {
    const parts = command.split(' ');
    if (parts.length >= 2) {
        const setting = parts[1];
        const modeDisplay = document.getElementById('vim-mode');
        
        switch (setting) {
            case 'number':
            case 'nu':
                toggleLineNumbers(editor, true);
                break;
            case 'nonumber':
            case 'nonu':
                toggleLineNumbers(editor, false);
                break;
            case 'hlsearch':
                // Highlight search - already implemented with selection
                break;
            case 'nohlsearch':
                // Turn off highlight search
                break;
            default:
                if (modeDisplay) {
                    const originalText = modeDisplay.textContent;
                    modeDisplay.textContent = `E518: Unknown option: ${setting}`;
                    setTimeout(() => {
                        modeDisplay.textContent = originalText;
                    }, 2000);
                }
        }
    }
}

function goToLine(editor, lineNumber) {
    const lines = editor.value.split('\n');
    if (lineNumber > 0 && lineNumber <= lines.length) {
        const position = lines.slice(0, lineNumber - 1).join('\n').length + (lineNumber > 1 ? 1 : 0);
        editor.setSelectionRange(position, position);
        editor.focus();
    }
}

function deleteCurrentLine(editor) {
    const start = editor.selectionStart;
    const value = editor.value;
    
    // Find current line boundaries
    let lineStart = value.lastIndexOf('\n', start - 1) + 1;
    let lineEnd = value.indexOf('\n', start);
    if (lineEnd === -1) lineEnd = value.length;
    
    // Delete the line
    const newValue = value.substring(0, lineStart) + value.substring(lineEnd + 1);
    editor.value = newValue;
    editor.setSelectionRange(lineStart, lineStart);
}

function saveNanoFileDirect(filename, content, shouldExit = false) {
    const lines = content.split('\n').length;
    const escapedContent = content.replace(/'/g, "'\"'\"'");
    
    fetch(`/terminal/${currentSessionId}/execute/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ 
            command: `printf '%s' '${escapedContent}' > "${filename}"` 
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update original content
            const editor = document.getElementById('nano-content');
            if (editor) {
                editor.originalContent = content;
            }
            
            // Update modified status
            const modifiedStatus = document.getElementById('nano-modified-status');
            if (modifiedStatus) {
                modifiedStatus.textContent = '';
            }
            
            if (shouldExit) {
                setTimeout(() => {
                    closeEditor('nano');
                }, 500);
            } else {
                // Continue editing
                document.getElementById('nano-content').focus();
            }
        } else {
            // Handle save error
            alert('Error: Could not save file');
            if (!shouldExit) {
                document.getElementById('nano-content').focus();
            }
        }
    })
    .catch(error => {
        console.error('Save error:', error);
        alert('Error: Save failed');
        if (!shouldExit) {
            document.getElementById('nano-content').focus();
        }
    });
}

function showNanoRealExitPrompt(filename, content) {
    const exitPrompt = document.getElementById('nano-exit-prompt');
    const yesOption = document.getElementById('nano-yes-option');
    const noOption = document.getElementById('nano-no-option');
    const cancelOption = document.getElementById('nano-cancel-option');
    
    exitPrompt.classList.remove('hidden');
    
    // Handle keyboard input
    const handleKeyResponse = (e) => {
        if (e.key.toLowerCase() === 'y') {
            e.preventDefault();
            hideNanoExitPrompt();
            saveNanoFileDirect(filename, content, true);
            document.removeEventListener('keydown', handleKeyResponse);
        } else if (e.key.toLowerCase() === 'n') {
            e.preventDefault();
            hideNanoExitPrompt();
            closeEditor('nano');
            document.removeEventListener('keydown', handleKeyResponse);
        } else if (e.ctrlKey && e.key === 'c') {
            e.preventDefault();
            hideNanoExitPrompt();
            document.getElementById('nano-content').focus();
            document.removeEventListener('keydown', handleKeyResponse);
        }
    };
    
    // Handle clicks
    yesOption.onclick = () => {
        hideNanoExitPrompt();
        saveNanoFileDirect(filename, content, true);
        document.removeEventListener('keydown', handleKeyResponse);
    };
    
    noOption.onclick = () => {
        hideNanoExitPrompt();
        closeEditor('nano');
        document.removeEventListener('keydown', handleKeyResponse);
    };
    
    cancelOption.onclick = () => {
        hideNanoExitPrompt();
        document.getElementById('nano-content').focus();
        document.removeEventListener('keydown', handleKeyResponse);
    };
    
    document.addEventListener('keydown', handleKeyResponse);
}

function hideNanoExitPrompt() {
    const exitPrompt = document.getElementById('nano-exit-prompt');
    exitPrompt.classList.add('hidden');
}



function showNanoHelp() {
    const helpText = `GNU nano 6.2 Help Text

The nano editor is designed to emulate the functionality and ease-of-use of the UW Pico text editor.

Main Commands:
^G  (F1)     Display this help text
^X  (F2)     Close the current file buffer / Exit from nano
^O  (F3)     Write the current file to disk
^R  (F5)     Insert another file into the current one
^W  (F6)     Search for text
^Y  (F7)     Move to the previous screen
^V  (F8)     Move to the next screen
^K  (F9)     Cut the current line and store it in the cutbuffer
^U  (F10)    Uncut from the cutbuffer into the current line
^T  (F12)    Invoke the spell checker, if available

For more info, type 'man nano' in your terminal.`;
    
    alert(helpText);
}

function showNanoSearch(editor) {
    const searchTerm = prompt('Search:');
    if (searchTerm) {
        const content = editor.value;
        const currentPos = editor.selectionStart;
        let index = content.toLowerCase().indexOf(searchTerm.toLowerCase(), currentPos);
        
        if (index === -1) {
            // Search from beginning
            index = content.toLowerCase().indexOf(searchTerm.toLowerCase());
        }
        
        if (index !== -1) {
            editor.setSelectionRange(index, index + searchTerm.length);
            editor.focus();
            
            // Store search term for continued searching
            editor.lastSearchTerm = searchTerm;
        } else {
            alert(`"${searchTerm}" not found`);
        }
    }
}

// Additional nano functions
function insertFile(editor) {
    const filename = prompt('File to insert:');
    if (filename) {
        // In a real implementation, this would read the file
        alert('Insert file functionality would read and insert the specified file here');
    }
}

function justifyText(editor) {
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    
    if (start !== end) {
        const selectedText = editor.value.substring(start, end);
        const justified = selectedText.replace(/\s+/g, ' ').trim();
        
        const newValue = editor.value.substring(0, start) + justified + editor.value.substring(end);
        editor.value = newValue;
        editor.setSelectionRange(start, start + justified.length);
    }
}

function pageUp(editor) {
    const lines = editor.value.split('\n');
    const currentPos = editor.selectionStart;
    const currentLine = editor.value.substring(0, currentPos).split('\n').length - 1;
    
    const newLine = Math.max(0, currentLine - 10);
    const newPos = lines.slice(0, newLine).join('\n').length + (newLine > 0 ? 1 : 0);
    
    editor.setSelectionRange(newPos, newPos);
    editor.scrollTop = Math.max(0, editor.scrollTop - 200);
}

function pageDown(editor) {
    const lines = editor.value.split('\n');
    const currentPos = editor.selectionStart;
    const currentLine = editor.value.substring(0, currentPos).split('\n').length - 1;
    
    const newLine = Math.min(lines.length - 1, currentLine + 10);
    const newPos = lines.slice(0, newLine).join('\n').length + (newLine > 0 ? 1 : 0);
    
    editor.setSelectionRange(newPos, newPos);
    editor.scrollTop = editor.scrollTop + 200;
}

function showCursorPosition(editor) {
    const pos = editor.selectionStart;
    const lines = editor.value.substring(0, pos).split('\n');
    const line = lines.length;
    const col = lines[lines.length - 1].length + 1;
    const totalLines = editor.value.split('\n').length;
    const totalChars = editor.value.length;
    
    alert(`line ${line}/${totalLines} (${Math.round(line/totalLines*100)}%), col ${col}, char ${pos}/${totalChars} (${Math.round(pos/totalChars*100)}%)`);
}

function spellCheck(editor) {
    alert('Spell checker would be invoked here (requires external spell checking service)');
}

function cutNanoLine(editor) {
    const start = editor.selectionStart;
    const value = editor.value;
    
    // Find the start and end of the current line
    let lineStart = value.lastIndexOf('\n', start - 1) + 1;
    let lineEnd = value.indexOf('\n', start);
    if (lineEnd === -1) lineEnd = value.length;
    
    // Cut the line (including newline if not last line)
    const lineContent = value.substring(lineStart, lineEnd + (lineEnd < value.length ? 1 : 0));
    nanoCutBuffer = lineContent;
    
    // Remove the line from editor
    const newValue = value.substring(0, lineStart) + value.substring(lineEnd + (lineEnd < value.length ? 1 : 0));
    editor.value = newValue;
    editor.setSelectionRange(lineStart, lineStart);
}

function pasteNanoLine(editor) {
    if (nanoCutBuffer) {
        const start = editor.selectionStart;
        const value = editor.value;
        
        const newValue = value.substring(0, start) + nanoCutBuffer + value.substring(start);
        editor.value = newValue;
        editor.setSelectionRange(start + nanoCutBuffer.length, start + nanoCutBuffer.length);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (currentSessionId) {
        terminalInput.focus();
    }
    
    // Initialize history handling
    initializeHistoryHandling();
    
    // Don't initialize scroll button until terminal is shown
});

// Initialize history handling
function initializeHistoryHandling() {
    const historyToggleBtn = document.getElementById('history-toggle-btn');
    const historyText = document.getElementById('history-text');
    const historyIcon = document.getElementById('history-icon');
    const oldHistory = document.getElementById('old-history');
    const terminalMessages = document.getElementById('terminal-messages');
    
    if (!historyToggleBtn || !historyText || !historyIcon || !oldHistory) return;
    
    // History toggle functionality
    let historyVisible = false;
    historyToggleBtn.addEventListener('click', () => {
        historyVisible = !historyVisible;
        if (historyVisible) {
            oldHistory.classList.remove('hidden');
            historyText.textContent = 'Hide History';
            historyIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />';
        } else {
            oldHistory.classList.add('hidden');
            historyText.textContent = 'Show History';
            historyIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />';
        }
        
        // Scroll to bottom after toggle
        setTimeout(() => {
            if (terminalMessages) {
                terminalMessages.scrollTop = terminalMessages.scrollHeight;
            }
        }, 100);
    });
}

// Initialize scroll to bottom functionality
function initializeScrollToBottom() {
    const terminalMessages = document.getElementById('terminal-messages');
    const scrollButton = document.getElementById('scroll-to-bottom');
    
    if (!terminalMessages || !scrollButton) {
        return;
    }
    
    // Make sure we don't initialize twice
    if (window.scrollButtonInitialized) {
        return;
    }
    window.scrollButtonInitialized = true;
    
    let userScrolledUp = false;
    
    // Simple function to check if at bottom
    function isAtBottom() {
        const scrollTop = terminalMessages.scrollTop;
        const scrollHeight = terminalMessages.scrollHeight;
        const clientHeight = terminalMessages.clientHeight;
        return (scrollHeight - scrollTop - clientHeight) < 20;
    }
    
    // Simple function to check if has scrollable content
    function hasScrollableContent() {
        return terminalMessages.scrollHeight > terminalMessages.clientHeight + 10;
    }
    
    // Update button visibility
    function updateButtonVisibility() {
        const hasContent = hasScrollableContent();
        const atBottom = isAtBottom();
        
        if (hasContent && !atBottom) {
            scrollButton.classList.remove('hidden');
        } else {
            scrollButton.classList.add('hidden');
        }
    }
    
    // Handle scroll events
    terminalMessages.addEventListener('scroll', () => {
        updateButtonVisibility();
        
        // Track if user manually scrolled up
        if (!isAtBottom()) {
            userScrolledUp = true;
        } else {
            userScrolledUp = false;
        }
    });
    
    // Click handler for scroll button
    scrollButton.addEventListener('click', () => {
        terminalMessages.scrollTop = terminalMessages.scrollHeight;
        userScrolledUp = false;
        updateButtonVisibility();
    });
    
    // Update button when content changes
    const observer = new MutationObserver(() => {
        // Small delay to let content render
        setTimeout(() => {
            updateButtonVisibility();
        }, 50);
    });
    
    observer.observe(terminalMessages, {
        childList: true,
        subtree: true
    });
    
    // Store state for auto-scroll
    window.terminalScrollState = {
        isUserScrolledUp: () => userScrolledUp,
        resetScrollState: () => {
            userScrolledUp = false;
        }
    };
}

// Smooth scroll to bottom function
function smoothScrollToBottom() {
    const terminalMessages = document.getElementById('terminal-messages');
    if (terminalMessages) {
        terminalMessages.scrollTo({
            top: terminalMessages.scrollHeight,
            behavior: 'smooth'
        });
        
        // Reset user scroll state
        if (window.terminalScrollState) {
            window.terminalScrollState.resetScrollState();
        }
    }
}

// Auto-scroll to bottom (only if user hasn't manually scrolled up)
function autoScrollToBottom() {
    const terminalMessages = document.getElementById('terminal-messages');
    if (!terminalMessages) return;
    
    // Only auto-scroll if user hasn't manually scrolled up
    const userScrolledUp = window.terminalScrollState && window.terminalScrollState.isUserScrolledUp();
    
    if (!userScrolledUp) {
        // Instant scroll for better UX
        terminalMessages.scrollTop = terminalMessages.scrollHeight;
    }
}
