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
let currentClusterId = null;
let currentPath = '~';
let commandHistory = [];
let historyIndex = 0;
let currentCommandAbortController = null;
let connectionCheckInterval = null;

// IMMEDIATE HOMEPAGE CHECK - Hide scroll button if no textbox
function hideScrollButtonOnHomepage() {
    const textbox = document.getElementById('terminal-input');
    const container = document.querySelector('.scroll-button-container');
    const scrollButton = document.getElementById('smart-scroll-btn');
    const historyToggleBtn = document.getElementById('history-toggle-btn');
    
    // Always hide history button on page load until verified
    if (historyToggleBtn) {
        historyToggleBtn.classList.add('hidden');
        historyToggleBtn.style.setProperty('display', 'none', 'important');
        console.log('🚫 PAGE LOAD: History button hidden until verified');
    }
    
    if (!textbox && container) {
        // Homepage detected - force hide everything
        container.style.setProperty('display', 'none', 'important');
        if (scrollButton) {
            scrollButton.classList.add('hidden');
            scrollButton.style.display = 'none';
        }
        console.log('🚫 HOMEPAGE: Scroll button hidden immediately');
        return true;
    }
    return false;
}

// Run immediately
hideScrollButtonOnHomepage();

// IMMEDIATE HISTORY BUTTON HIDE - CEO GPU Discount Mode
(function forceHideHistoryImmediately() {
    const histBtn = document.getElementById('history-toggle-btn');
    if (histBtn) {
        histBtn.classList.add('hidden');
        histBtn.style.setProperty('display', 'none', 'important');
        console.log('🎯 CEO MODE: History button force hidden on load');
    }
})();

// Run again when DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    hideScrollButtonOnHomepage();
    // Double-check history button hiding
    const histBtn = document.getElementById('history-toggle-btn');
    if (histBtn) {
        histBtn.classList.add('hidden');
        histBtn.style.setProperty('display', 'none', 'important');
        console.log('🎯 DOM LOADED: History button force hidden');
    }
});

// Notification system
function showNotification(message, type = 'error', duration = 4000) {
    // Create notification container if it doesn't exist
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.className = 'fixed top-4 right-4 z-[100] space-y-2';
        document.body.appendChild(container);
    }
    
    // Create notification element
    const notification = document.createElement('div');
    const id = 'notif-' + Date.now();
    notification.id = id;
    
    const typeStyles = {
        error: 'bg-red-900/95 border-red-500/50 text-red-100',
        success: 'bg-green-900/95 border-green-500/50 text-green-100',
        warning: 'bg-yellow-900/95 border-yellow-500/50 text-yellow-100',
        info: 'bg-blue-900/95 border-blue-500/50 text-blue-100'
    };
    
    const icons = {
        error: '⚠️',
        success: '✅',
        warning: '⚠️',
        info: 'ℹ️'
    };
    
    notification.className = `flex items-center gap-3 p-4 rounded-lg border backdrop-blur-sm shadow-2xl transform translate-x-full transition-transform duration-300 ease-out max-w-md ${typeStyles[type]}`;
    
    notification.innerHTML = `
        <span class="text-lg">${icons[type]}</span>
        <span class="flex-1 text-sm font-medium">${message}</span>
        <button class="text-white/70 hover:text-white transition-colors ml-2" onclick="closeNotification('${id}')">
            <svg class="w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </button>
    `;
    
    container.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.transform = 'translateX(0)';
    }, 10);
    
    // Auto dismiss
    setTimeout(() => {
        closeNotification(id);
    }, duration);
}

// Make closeNotification globally available
window.closeNotification = function(id) {
    const notification = document.getElementById(id);
    if (notification) {
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            notification.remove();
        }, 300);
    }
}

function showErrorMessage(message) {
    showNotification(message, 'error');
}

function showSuccessMessage(message) {
    showNotification(message, 'success');
}

function showWarningMessage(message) {
    showNotification(message, 'warning');
}

function showInfoMessage(message) {
    showNotification(message, 'info');
}

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

// Cluster session clicks and menu handling
document.addEventListener('click', (e) => {
    // Handle cluster session clicks (but not when clicking menu button)
    if (e.target.closest('.cluster-session') && !e.target.closest('.cluster-menu-btn')) {
        e.preventDefault();
        const sessionElement = e.target.closest('.cluster-session');
        const sessionId = sessionElement.dataset.sessionId;
        const clusterName = sessionElement.dataset.clusterName;
        const clusterId = sessionElement.dataset.clusterId;
        switchToSession(sessionId, clusterName, clusterId);
    }
    
    // Handle dropdown menu button clicks
    if (e.target.closest('.cluster-menu-btn')) {
        e.preventDefault();
        e.stopPropagation();
        const menuBtn = e.target.closest('.cluster-menu-btn');
        const dropdown = menuBtn.closest('.group').querySelector('.cluster-dropdown');
        
        // Close all other dropdowns
        document.querySelectorAll('.cluster-dropdown').forEach(d => {
            if (d !== dropdown) d.classList.add('hidden');
        });
        
        // Toggle current dropdown
        dropdown.classList.toggle('hidden');
        
        // Store current session data on dropdown for later use
        dropdown.dataset.sessionId = menuBtn.dataset.sessionId;
        dropdown.dataset.clusterName = menuBtn.dataset.clusterName;
        dropdown.dataset.clusterId = menuBtn.dataset.clusterId;
    }
    
    // Close dropdowns when clicking outside
    if (!e.target.closest('.cluster-dropdown') && !e.target.closest('.cluster-menu-btn')) {
        document.querySelectorAll('.cluster-dropdown').forEach(d => d.classList.add('hidden'));
    }
});

// Modal click outside to close
clusterModal.addEventListener('click', (e) => {
    if (e.target === clusterModal) {
        hideClusterModal();
    }
});

// Management modal elements
const renameModal = document.getElementById('rename-modal');
const clearHistoryModal = document.getElementById('clear-history-modal');
const kubeconfigModal = document.getElementById('kubeconfig-modal');
const deleteModal = document.getElementById('delete-modal');

// Current action context
let currentActionContext = {};

// Dropdown menu action handlers
document.addEventListener('click', (e) => {
    const dropdown = e.target.closest('.cluster-dropdown');
    if (!dropdown) return;
    
    // Get context from dropdown
    currentActionContext = {
        sessionId: dropdown.dataset.sessionId,
        clusterName: dropdown.dataset.clusterName,
        clusterId: dropdown.dataset.clusterId
    };
    
    // Handle different actions
    if (e.target.closest('.rename-cluster')) {
        showRenameModal();
        dropdown.classList.add('hidden');
    } else if (e.target.closest('.clear-history')) {
        showClearHistoryModal();
        dropdown.classList.add('hidden');
    } else if (e.target.closest('.edit-kubeconfig')) {
        showKubeconfigModal();
        dropdown.classList.add('hidden');
    } else if (e.target.closest('.delete-cluster')) {
        showDeleteModal();
        dropdown.classList.add('hidden');
    }
});

// Rename modal functionality
function showRenameModal() {
    const newChatNameInput = document.getElementById('new-chat-name');
    newChatNameInput.value = currentActionContext.clusterName;
    renameModal.classList.remove('hidden');
    newChatNameInput.focus();
    newChatNameInput.select();
}

function hideRenameModal() {
    renameModal.classList.add('hidden');
    document.getElementById('rename-form').reset();
}

document.getElementById('close-rename-modal').addEventListener('click', hideRenameModal);
document.getElementById('cancel-rename').addEventListener('click', hideRenameModal);

document.getElementById('rename-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const newName = document.getElementById('new-chat-name').value.trim();
    
    if (!newName) return;
    
    try {
        // API call to rename chat (replace with actual endpoint)
        const response = await fetch(`/clusters/${currentActionContext.clusterId}/rename/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ name: newName })
        });
        
        if (response.ok) {
            // Update UI
            const sessionElement = document.querySelector(`[data-session-id="${currentActionContext.sessionId}"]`);
            if (sessionElement) {
                sessionElement.querySelector('span').textContent = newName;
                sessionElement.dataset.clusterName = newName;
            }
            hideRenameModal();
            showSuccessMessage('Chat renamed successfully!');
        } else {
            showErrorMessage('Failed to rename chat. Please try again.');
        }
    } catch (error) {
        console.error('Rename error:', error);
        showErrorMessage('Failed to rename chat. Please try again.');
    }
});

// Clear history modal functionality
function showClearHistoryModal() {
    clearHistoryModal.classList.remove('hidden');
}

function hideClearHistoryModal() {
    clearHistoryModal.classList.add('hidden');
}

document.getElementById('close-clear-modal').addEventListener('click', hideClearHistoryModal);
document.getElementById('cancel-clear').addEventListener('click', hideClearHistoryModal);

document.getElementById('confirm-clear').addEventListener('click', async () => {
    try {
        // API call to clear history (replace with actual endpoint)
        const response = await fetch(`/terminal/${currentActionContext.sessionId}/clear-history/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        if (response.ok) {
            // Clear terminal UI
            const terminalMessages = document.getElementById('terminal-messages');
            const oldHistory = document.getElementById('old-history');
            const currentSession = document.getElementById('current-session');
            
            if (oldHistory) oldHistory.innerHTML = '';
            if (currentSession) currentSession.innerHTML = '';
            
            // Hide history toggle button
            const historyToggleBtn = document.getElementById('history-toggle-btn');
            if (historyToggleBtn) historyToggleBtn.classList.add('hidden');
            
            hideClearHistoryModal();
            showSuccessMessage('Chat history cleared successfully.');
        } else {
            showErrorMessage('Failed to clear history. Please try again.');
        }
    } catch (error) {
        console.error('Clear history error:', error);
        showErrorMessage('Failed to clear history. Please try again.');
    }
});

// Kubeconfig modal functionality
function showKubeconfigModal() {
    // Load current kubeconfig (replace with actual endpoint)
    loadCurrentKubeconfig();
    kubeconfigModal.classList.remove('hidden');
}

function hideKubeconfigModal() {
    kubeconfigModal.classList.add('hidden');
    document.getElementById('kubeconfig-form').reset();
}

async function loadCurrentKubeconfig() {
    try {
        const response = await fetch(`/clusters/${currentActionContext.clusterId}/kubeconfig/`);
        if (response.ok) {
            const data = await response.json();
            document.getElementById('edit-kubeconfig').value = data.kubeconfig || '';
        }
    } catch (error) {
        console.error('Failed to load kubeconfig:', error);
    }
}

document.getElementById('close-kubeconfig-modal').addEventListener('click', hideKubeconfigModal);
document.getElementById('cancel-kubeconfig').addEventListener('click', hideKubeconfigModal);

document.getElementById('kubeconfig-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const kubeconfig = document.getElementById('edit-kubeconfig').value.trim();
    
    if (!kubeconfig) return;
    
    try {
        // API call to update kubeconfig (replace with actual endpoint)
        const response = await fetch(`/clusters/${currentActionContext.clusterId}/update-kubeconfig/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ kubeconfig: kubeconfig })
        });
        
        if (response.ok) {
            hideKubeconfigModal();
            showSuccessMessage('Kubeconfig updated successfully.');
            
            // Check connection status after kubeconfig update
            setTimeout(() => {
                checkConnectionStatus();
            }, 1000); // Small delay to allow server to process
        } else {
            const data = await response.json();
            showErrorMessage(`Failed to update kubeconfig: ${data.error || 'Unknown error'}`);
        }
    } catch (error) {
        console.error('Update kubeconfig error:', error);
        showErrorMessage('Failed to update kubeconfig. Please try again.');
    }
});

// Delete modal functionality
function showDeleteModal() {
    deleteModal.classList.remove('hidden');
}

function hideDeleteModal() {
    deleteModal.classList.add('hidden');
}

document.getElementById('close-delete-modal').addEventListener('click', hideDeleteModal);
document.getElementById('cancel-delete').addEventListener('click', hideDeleteModal);

document.getElementById('confirm-delete').addEventListener('click', async () => {
    try {
        // API call to delete chat (replace with actual endpoint)
        const response = await fetch(`/clusters/${currentActionContext.clusterId}/delete/`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        if (response.ok) {
            // Remove from UI
            const sessionElement = document.querySelector(`[data-session-id="${currentActionContext.sessionId}"]`);
            if (sessionElement) {
                sessionElement.closest('.group').remove();
            }
            
            // If this was the current session, show welcome message
            if (currentSessionId === currentActionContext.sessionId) {
                currentSessionId = null;
                const welcomeMessage = document.getElementById('welcome-message');
                const terminalContainer = document.getElementById('terminal-container');
                if (welcomeMessage && terminalContainer) {
                    welcomeMessage.style.display = 'block';
                    terminalContainer.classList.add('hidden');
                }
            }
            
            hideDeleteModal();
            showSuccessMessage('Chat deleted successfully.');
        } else {
            showErrorMessage('Failed to delete chat. Please try again.');
        }
    } catch (error) {
        console.error('Delete error:', error);
        showErrorMessage('Failed to delete chat. Please try again.');
    }
});

// Close modals when clicking outside
[renameModal, clearHistoryModal, kubeconfigModal, deleteModal].forEach(modal => {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });
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
    } else {
        // Even if no command is running, show the interrupt signal
        appendTerminalMessage('info', '^C');
        // Clear any processing state
        const terminalInput = document.getElementById('terminal-input');
        if (terminalInput && terminalInput.placeholder === 'Processing...') {
        setTerminalInputState(true);
        }
    }
}

async function executeCommand(command, silent = false) {
    try {
        // Create abort controller for this command
        currentCommandAbortController = new AbortController();
        console.log('Executing command:', command, 'Silent:', silent);
        
        const response = await fetch(`/terminal/${currentSessionId}/execute/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
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
                    // Update history button after clearing (history may still exist)
                    updateHistoryButtonVisibility();
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
    
    // Immediately check scroll button after new content (force hide if not needed)
    if (window.smartScrollChecker) {
        window.smartScrollChecker();
    }
    
    // Only update history button if this is actual command content, not system messages
    if (type === 'command' || (type === 'output' && content.trim() && !content.includes('Connected to') && !content.includes('Terminal ready'))) {
        updateHistoryButtonVisibility();
    }
    
    // Double-check after DOM updates
    setTimeout(() => {
        if (window.smartScrollChecker) {
            window.smartScrollChecker();
        }
        // Only update history button for actual commands
        if (type === 'command' || (type === 'output' && content.trim() && !content.includes('Connected to') && !content.includes('Terminal ready'))) {
            updateHistoryButtonVisibility();
        }
    }, 50);
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

async function switchToSession(sessionId, clusterName, clusterId) {
    // Stop previous connection monitoring
    stopConnectionMonitoring();
    
    currentSessionId = sessionId;
    currentClusterName = clusterName;
    currentClusterId = clusterId;
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
    
    // Hide history button initially (will be shown by loadCommandHistory if needed)
    const sessionHistoryBtn = document.getElementById('history-toggle-btn');
    const oldHistory = document.getElementById('old-history');
    
    if (sessionHistoryBtn) {
        sessionHistoryBtn.classList.add('hidden');
        sessionHistoryBtn.style.setProperty('display', 'none', 'important');
        console.log('🚫 Session start - hiding History button until verified');
    }
    
    // Clear and hide any existing history content
    if (oldHistory) {
        oldHistory.innerHTML = '';
        oldHistory.classList.add('hidden');
    }
    
    // Initialize scroll button now that terminal is visible
    initializeSmartScroll();
    
        // Initialize direct positioning for new session  
    setTimeout(() => {
        console.log('🎯 Setting up textbox-top positioning');
        
        // Check if textbox exists on this page
        const textbox = document.getElementById('terminal-input');
        if (!textbox) {
            // No textbox (homepage) - hide everything
            const container = document.querySelector('.scroll-button-container');
            const scrollButton = document.getElementById('smart-scroll-btn');
            if (container) container.style.display = 'none';
            if (scrollButton) scrollButton.classList.add('hidden');
            console.log('🚫 Homepage detected - scroll button hidden');
            return;
        }
        
        // Apply initial positioning
        if (window.fixButtonPosition) {
            window.fixButtonPosition();
            console.log('✅ Initial positioning applied - button at textbox top');
        }
        
        console.log('✅ Direct positioning ready - button at textbox top edge');
        console.log('📝 Resize your browser window to test');
    }, 300);
    
    // Update active session in sidebar
    document.querySelectorAll('.cluster-session').forEach(session => {
        session.classList.remove('bg-terminal-card/50');
    });
    const activeSession = document.querySelector(`[data-session-id="${sessionId}"]`);
    if (activeSession) {
        activeSession.classList.add('bg-terminal-card/50');
    }
    
    // Start connection monitoring for the new session
    startConnectionMonitoring();
    
            // Load command history first (this will populate old history and show toggle button)
        await loadCommandHistory(sessionId);
        
        // FORCE HIDE: Ensure button is hidden unless there's actual user commands
        const forceHideBtn = document.getElementById('history-toggle-btn');
        if (forceHideBtn) {
            forceHideBtn.classList.add('hidden');
            forceHideBtn.style.setProperty('display', 'none', 'important');
        }
        
        // Update history button visibility after loading (strict check)
        updateHistoryButtonVisibility();
    
    // Show welcome message in current session
    appendTerminalMessage('info', `Connected to ${clusterName}. Terminal ready.`);
    appendTerminalMessage('info', `Type 'help' for available commands.`);
    
    // Focus on input
    terminalInput.focus();
    
    // Force initial connection status update
    setTimeout(() => {
        console.log('Forcing initial connection status check');
        updateConnectionStatus('connecting', false);
    }, 100);
}

// Function to check and update history button visibility
function updateHistoryButtonVisibility() {
    const historyToggleBtn = document.getElementById('history-toggle-btn');
    const oldHistory = document.getElementById('old-history');
    
    if (!historyToggleBtn) return;
    
    // SUPER STRICT CHECK: Only show button if there's ACTUAL user command history
    let hasActualUserCommands = false;
    
    if (oldHistory && oldHistory.children.length > 0) {
        // Look for actual user commands (not system messages)
        for (let i = 0; i < oldHistory.children.length; i++) {
            const child = oldHistory.children[i];
            const text = child.textContent || '';
            
            // Must be a terminal-message with user command prompt AND actual command
            if (child.classList.contains('terminal-message') && 
                text.includes('user@k8s-terminal:~$') &&
                !text.includes('Connected to') &&
                !text.includes('Terminal ready') &&
                !text.includes('Type \'help\'') &&
                !text.includes('--- Previous Session ---')) {
                
                // Extract command part after the prompt
                const commandPart = text.split('user@k8s-terminal:~$')[1];
                if (commandPart && commandPart.trim() && 
                    commandPart.trim() !== '' &&
                    commandPart.trim() !== 'clear' &&
                    commandPart.trim() !== 'history') {
                    hasActualUserCommands = true;
                    break;
                }
            }
        }
    }
    
    // FORCE HIDE: Always hide unless we have verified user commands
    if (hasActualUserCommands) {
        historyToggleBtn.classList.remove('hidden');
        historyToggleBtn.style.setProperty('display', 'flex', 'important');
        console.log('✅ Actual user commands found - showing History button');
    } else {
        historyToggleBtn.classList.add('hidden');
        historyToggleBtn.style.setProperty('display', 'none', 'important');
        console.log('🚫 NO USER COMMANDS - History button HIDDEN');
    }
}

async function loadCommandHistory(sessionId) {
    const historyToggleBtn = document.getElementById('history-toggle-btn');
    const oldHistory = document.getElementById('old-history');
    
    // Always start with button hidden
    if (historyToggleBtn) {
        historyToggleBtn.classList.add('hidden');
        historyToggleBtn.style.setProperty('display', 'none', 'important');
    }
    
    // Clear any existing history content
    if (oldHistory) {
        oldHistory.innerHTML = '';
        oldHistory.classList.add('hidden');
    }
    
    try {
        const response = await fetch(`/terminal/${sessionId}/history/`);
        const data = await response.json();
        
        if (data.success && data.history.length > 0) {
            // Load previous commands into old history (hidden by default)
            const oldHistory = document.getElementById('old-history');
            
            if (oldHistory && data.history.length > 0) {
                // Clear any existing content first
                oldHistory.innerHTML = '';
                
                // Add separator
                const separatorDiv = document.createElement('div');
                separatorDiv.className = 'text-blue-500 text-xs border-b border-blue-800/30 pb-2 mb-4';
                separatorDiv.textContent = '--- Previous Session ---';
                oldHistory.appendChild(separatorDiv);
                
                // Filter out empty or invalid commands
                const validHistory = data.history.filter(cmd => 
                    cmd.command && cmd.command.trim() !== '' && 
                    cmd.command.trim() !== 'clear' && 
                    cmd.command.trim() !== 'history'
                );
                
                if (validHistory.length > 0) {
                // Add previous commands to old history (last 10)
                    validHistory.slice(-10).forEach(cmd => {
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
                        if (cmd.output && cmd.output.trim()) {
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
                }
                
                // Make sure old history starts hidden
                oldHistory.classList.add('hidden');
            }
        }
        
        // Update button visibility based on actual content
        updateHistoryButtonVisibility();
        
    } catch (error) {
        console.error('Failed to load command history:', error);
        // Hide button on error
        if (historyToggleBtn) {
            historyToggleBtn.classList.add('hidden');
            historyToggleBtn.style.setProperty('display', 'none', 'important');
        }
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
    } else if (e.ctrlKey && (e.key === 'c' || e.key === 'C')) {
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
  
  // Prevent body scroll when sidebar is open on mobile
  if (sidebar.classList.contains('-translate-x-full')) {
    document.body.classList.remove('overflow-hidden');
  } else {
    document.body.classList.add('overflow-hidden');
  }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getCsrfToken() {
    // Try meta tag first
    const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (metaToken) return metaToken;
    
    // Fallback to Django's csrf token from form
    const formToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (formToken) return formToken;
    
    // Last resort - get from cookie
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];
    
    return cookieValue || '';
}

// Connection status management
function updateConnectionStatus(status, isConnected) {
    console.log('Updating connection status:', status, 'isConnected:', isConnected);
    
    const connectionIndicator = document.getElementById('connection-indicator');
    const connectionPing = document.getElementById('connection-ping');
    const connectionText = document.getElementById('connection-text');
    
    console.log('UI elements found:', {
        indicator: !!connectionIndicator,
        ping: !!connectionPing,
        text: !!connectionText
    });
    
    if (!connectionIndicator || !connectionText) {
        console.error('Missing connection UI elements');
        return;
    }
    
    // Update UI elements
    if (isConnected) {
        connectionIndicator.className = 'w-3 h-3 bg-terminal-success rounded-full shadow-lg';
        if (connectionPing) connectionPing.className = 'absolute inset-0 w-3 h-3 bg-terminal-success rounded-full animate-ping opacity-75';
        connectionText.className = 'text-terminal-success font-medium';
        connectionText.textContent = 'Connected';
    } else if (status === 'error') {
        connectionIndicator.className = 'w-3 h-3 bg-terminal-error rounded-full shadow-lg';
        if (connectionPing) connectionPing.className = 'absolute inset-0 w-3 h-3 bg-terminal-error rounded-full animate-ping opacity-75';
        connectionText.className = 'text-terminal-error font-medium';
        connectionText.textContent = 'Error';
    } else {
        connectionIndicator.className = 'w-3 h-3 bg-terminal-warning rounded-full shadow-lg';
        if (connectionPing) connectionPing.className = 'absolute inset-0 w-3 h-3 bg-terminal-warning rounded-full animate-ping opacity-75';
        connectionText.className = 'text-terminal-warning font-medium';
        connectionText.textContent = 'Connecting...';
    }
    
    // Update sidebar status
    const sessionElement = document.querySelector(`[data-session-id="${currentSessionId}"]`);
    console.log('Session element found:', !!sessionElement, 'Session ID:', currentSessionId);
    
    if (sessionElement) {
        const statusIndicator = sessionElement.querySelector('[class*="w-2.5"]');
        const statusText = sessionElement.querySelector('.text-xs');
        
        console.log('Sidebar elements found:', {
            indicator: !!statusIndicator,
            text: !!statusText
        });
        
        if (statusIndicator) {
            if (isConnected) {
                statusIndicator.className = 'w-2.5 h-2.5 rounded-full bg-terminal-success shadow-sm';
            } else if (status === 'error') {
                statusIndicator.className = 'w-2.5 h-2.5 rounded-full bg-terminal-error shadow-sm';
            } else {
                statusIndicator.className = 'w-2.5 h-2.5 rounded-full bg-terminal-warning shadow-sm';
            }
        }
        
        if (statusText) {
            statusText.textContent = isConnected ? 'Connected' : (status === 'error' ? 'Error' : 'Connecting');
        }
    }
}

async function checkConnectionStatus() {
    if (!currentClusterId) {
        console.log('No current cluster ID for connection check');
        return;
    }
    
    console.log('Checking connection status for cluster:', currentClusterId);
    
    try {
        const response = await fetch(`/clusters/${currentClusterId}/status/`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        console.log('Connection status response:', data);
        
        if (data.success) {
            updateConnectionStatus(data.status, data.status === 'connected');
        } else {
            console.error('Connection check returned error:', data.error);
            updateConnectionStatus('error', false);
        }
    } catch (error) {
        console.error('Connection check failed:', error);
        updateConnectionStatus('error', false);
    }
}

function startConnectionMonitoring() {
    // Clear any existing interval
    if (connectionCheckInterval) {
        clearInterval(connectionCheckInterval);
    }
    
    console.log('Starting connection monitoring for cluster:', currentClusterId);
    
    // Check immediately
    checkConnectionStatus();
    
    // Check every 2 minutes (120000 ms)
    connectionCheckInterval = setInterval(checkConnectionStatus, 120000);
    console.log('Connection monitoring started - checking every 2 minutes');
}

function stopConnectionMonitoring() {
    if (connectionCheckInterval) {
        clearInterval(connectionCheckInterval);
        connectionCheckInterval = null;
    }
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
            showErrorMessage('Error: Could not save file');
            if (!shouldExit) {
                document.getElementById('nano-content').focus();
            }
        }
    })
    .catch(error => {
        console.error('Save error:', error);
        showErrorMessage('Error: Save failed');
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
    showInfoMessage('Nano help: Use Ctrl+X to exit, Ctrl+O to save, Ctrl+W to search. See terminal shortcuts bar for more commands.');
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
            showInfoMessage(`"${searchTerm}" not found`);
        }
    }
}

// Additional nano functions
function insertFile(editor) {
    const filename = prompt('File to insert:');
    if (filename) {
        // In a real implementation, this would read the file
        showInfoMessage('Insert file functionality not implemented yet');
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
    
    showInfoMessage(`Line ${line}/${totalLines} (${Math.round(line/totalLines*100)}%), Col ${col}, Char ${pos}/${totalChars} (${Math.round(pos/totalChars*100)}%)`);
}

function spellCheck(editor) {
    showInfoMessage('Spell checker not implemented yet');
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
        // If there's already a session, initialize scroll button
        setTimeout(() => {
            const terminalContainer = document.getElementById('terminal-container');
            if (terminalContainer && !terminalContainer.classList.contains('hidden')) {
                initializeSmartScroll();
            }
        }, 500);
    }
    
    // Initialize history handling
    initializeHistoryHandling();
    
    // Global keyboard handler for Ctrl+C
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && (e.key === 'c' || e.key === 'C')) {
            // Only interrupt if we're in the terminal area
            const terminalContainer = document.getElementById('terminal-container');
            if (terminalContainer && !terminalContainer.classList.contains('hidden')) {
                e.preventDefault();
                interruptCurrentCommand();
            }
        }
    });
    
    // Don't initialize smart scroll button until terminal is shown
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopConnectionMonitoring();
});

// Debug functions for manual testing
window.testConnectionCheck = function() {
    console.log('Manual connection check triggered');
    if (!currentClusterId) {
        console.error('No cluster ID set');
        showErrorMessage('No active cluster session');
        return;
    }
    
    // Show loading state
    updateConnectionStatus('connecting', false);
    
    // Trigger check
    checkConnectionStatus();
};

    window.getCurrentConnectionInfo = function() {
        console.log('Current connection info:', {
            sessionId: currentSessionId,
            clusterName: currentClusterName,
            clusterId: currentClusterId,
            monitoringActive: !!connectionCheckInterval
        });
        return {
            sessionId: currentSessionId,
            clusterName: currentClusterName,
            clusterId: currentClusterId,
            monitoringActive: !!connectionCheckInterval
        };
    };
    
    // SIMPLE VISUAL TEST - Show exactly where button is
    window.showButtonPosition = function() {
        const button = document.getElementById('smart-scroll-btn');
        const terminalMessages = document.getElementById('terminal-messages');
        const terminalContainer = document.getElementById('terminal-container');
        
        if (!button || (!terminalMessages && !terminalContainer)) {
            console.log('❌ Button or chat area not found');
            return;
        }
        
        const buttonRect = button.getBoundingClientRect();
        const chatRect = terminalMessages ? terminalMessages.getBoundingClientRect() : terminalContainer.getBoundingClientRect();
        const chatCenter = chatRect.left + (chatRect.width / 2);
        const buttonCenter = buttonRect.left + (buttonRect.width / 2);
        
        console.log('📍 VISUAL BUTTON POSITION:', {
            buttonLeft: buttonRect.left,
            buttonWidth: buttonRect.width,
            buttonCenter: buttonCenter,
            chatCenter: chatCenter,
            chatLeft: chatRect.left,
            chatWidth: chatRect.width,
            difference: Math.abs(chatCenter - buttonCenter).toFixed(2) + 'px',
            usingElement: terminalMessages ? 'terminal-messages' : 'terminal-container',
            visuallyAppears: buttonCenter < chatCenter * 0.9 ? 'LEFT OF CHAT' : 
                           buttonCenter > chatCenter * 1.1 ? 'RIGHT OF CHAT' : 'CHAT CENTER',
            isActuallyCentered: Math.abs(chatCenter - buttonCenter) < 5 ? '✅ YES' : '❌ NO'
        });
        
        // Show chat center line for 3 seconds
        const centerLine = document.createElement('div');
        centerLine.style.cssText = `
            position: fixed;
            left: ${chatCenter}px;
            top: 0;
            width: 2px;
            height: 100vh;
            background: red;
            z-index: 999;
            transform: translateX(-50%);
            pointer-events: none;
        `;
        document.body.appendChild(centerLine);
        
        setTimeout(() => centerLine.remove(), 3000);
        console.log('🔴 Red line shows true CHAT center for 3 seconds');
    };
    
    // FORCE CHAT CENTER - Center button on chat area
    window.forceChatCenter = function() {
        console.log('🎯 FORCING SIMPLE CHAT CENTER...');
        
        const container = window.scrollButtonContainer || document.querySelector('.scroll-button-container');
        const terminalInput = document.getElementById('terminal-input');
        const terminalContainer = document.getElementById('terminal-container');
        
        if (!container || !terminalInput || !terminalContainer) {
            console.error('❌ Elements not found');
            return;
        }
        
        const inputRect = terminalInput.getBoundingClientRect();
        const terminalRect = terminalContainer.getBoundingClientRect();
        const chatCenter = terminalRect.left + (terminalRect.width / 2);
        const buttonY = inputRect.top - 50;
        
        // Apply chat-centered positioning
        container.style.cssText = `
            position: fixed !important;
            left: ${chatCenter}px !important;
            top: ${buttonY}px !important;
            transform: translateX(-50%) !important;
            z-index: 50 !important;
            pointer-events: none !important;
        `;
        
        console.log('✅ Applied chat center positioning');
        
        // Test immediately
        setTimeout(() => {
            window.showButtonPosition();
        }, 100);
    };
    
         // TEST RESIZE BEHAVIOR - Verify button stays chat-centered on resize
     window.testResizeStability = function() {
         console.log('🔄 TESTING AUTOMATIC RESIZE STABILITY...');
         
         // Record initial position using terminal-messages
         const terminalMessages = document.getElementById('terminal-messages');
         const button = document.getElementById('smart-scroll-btn');
         
         if (!terminalMessages || !button) {
             console.error('❌ Required elements not found');
             return;
         }
         
         const initialMessagesRect = terminalMessages.getBoundingClientRect();
         const initialButtonRect = button.getBoundingClientRect();
         const initialChatCenter = initialMessagesRect.left + (initialMessagesRect.width / 2);
         const initialButtonCenter = initialButtonRect.left + (initialButtonRect.width / 2);
         
         console.log('📐 INITIAL POSITION (terminal-messages):', {
             chatCenter: initialChatCenter,
             buttonCenter: initialButtonCenter,
             difference: Math.abs(initialChatCenter - initialButtonCenter).toFixed(2) + 'px'
         });
         
         // Trigger resize event
         console.log('🔄 Simulating resize event...');
         window.dispatchEvent(new Event('resize'));
         
         // Check position after auto-resize handling
         setTimeout(() => {
             const newMessagesRect = terminalMessages.getBoundingClientRect();
             const newButtonRect = button.getBoundingClientRect();
             const newChatCenter = newMessagesRect.left + (newMessagesRect.width / 2);
             const newButtonCenter = newButtonRect.left + (newButtonRect.width / 2);
             const finalDifference = Math.abs(newChatCenter - newButtonCenter);
             
             console.log('✅ POST-RESIZE POSITION:', {
                 chatCenter: newChatCenter,
                 buttonCenter: newButtonCenter,
                 difference: finalDifference.toFixed(2) + 'px',
                 autoResizeWorking: finalDifference < 2 ? '✅ YES - Auto-centering works perfectly!' : '❌ NO - Something is wrong',
                 status: finalDifference < 2 ? 'No manual intervention needed!' : 'Check positionScrollButton() logic'
             });
         }, 300);
     };
     
     // DEBUG CHAT CONTAINER - Find out what's wrong with positioning
     window.debugChatContainer = function() {
         console.log('🔍 DEBUGGING CHAT CONTAINER...');
         
         const terminalContainer = document.getElementById('terminal-container');
         const terminalMessages = document.getElementById('terminal-messages');
         const terminalInput = document.getElementById('terminal-input');
         const button = document.getElementById('smart-scroll-btn');
         
         console.log('📊 ELEMENT ANALYSIS:', {
             terminalContainer: terminalContainer ? {
                 exists: true,
                 rect: terminalContainer.getBoundingClientRect(),
                 classes: terminalContainer.className,
                 visible: !terminalContainer.classList.contains('hidden')
             } : 'NOT FOUND',
             
             terminalMessages: terminalMessages ? {
                 exists: true,
                 rect: terminalMessages.getBoundingClientRect(),
                 classes: terminalMessages.className
             } : 'NOT FOUND',
             
             terminalInput: terminalInput ? {
                 exists: true,
                 rect: terminalInput.getBoundingClientRect(),
                 classes: terminalInput.className
             } : 'NOT FOUND',
             
             button: button ? {
                 exists: true,
                 rect: button.getBoundingClientRect(),
                 container: button.parentElement ? button.parentElement.getBoundingClientRect() : 'NO PARENT'
             } : 'NOT FOUND'
         });
         
         // Try to find the actual chat area
         const possibleChatAreas = [
             document.querySelector('.terminal-container'),
             document.querySelector('[class*="terminal"]'),
             document.querySelector('[class*="chat"]'),
             document.querySelector('main'),
             document.querySelector('.main-content'),
             terminalMessages?.parentElement,
             terminalInput?.parentElement
         ].filter(el => el !== null);
         
         console.log('🎯 POSSIBLE CHAT AREAS FOUND:', possibleChatAreas.map(el => ({
             element: el.tagName + (el.id ? '#' + el.id : '') + (el.className ? '.' + el.className.split(' ')[0] : ''),
             rect: el.getBoundingClientRect(),
             isVisible: el.offsetWidth > 0 && el.offsetHeight > 0
         })));
     };
     
     // FORCE CORRECT CHAT CENTER - Use terminal messages area instead
     window.forceCorrectChatCenter = function() {
         console.log('🎯 FORCING CORRECT CHAT CENTER...');
         
         const container = window.scrollButtonContainer || document.querySelector('.scroll-button-container');
         const terminalInput = document.getElementById('terminal-input');
         const terminalMessages = document.getElementById('terminal-messages');
         
         if (!container || !terminalInput || !terminalMessages) {
             console.error('❌ Elements not found');
             return;
         }
         
         // Use terminal messages area as the true chat area
         const messagesRect = terminalMessages.getBoundingClientRect();
         const inputRect = terminalInput.getBoundingClientRect();
         
         // Calculate center of the messages area (the actual chat)
         const trueChatCenter = messagesRect.left + (messagesRect.width / 2);
         const buttonY = inputRect.top - 50;
         
         console.log('📐 TRUE CHAT CENTER CALCULATION:', {
             messagesArea: {
                 left: messagesRect.left,
                 width: messagesRect.width,
                 center: trueChatCenter
             },
             inputTop: inputRect.top,
             buttonY: buttonY
         });
         
         // Apply true chat-centered positioning
         container.style.cssText = `
             position: fixed !important;
             left: ${trueChatCenter}px !important;
             top: ${buttonY}px !important;
             transform: translateX(-50%) !important;
             z-index: 50 !important;
             pointer-events: none !important;
         `;
         
         console.log('✅ Applied TRUE chat center positioning');
         
         // Test immediately
         setTimeout(() => {
             window.showButtonPosition();
         }, 100);
     };
     

     
     // BULLETPROOF SYSTEM RESET - Complete reset and test
     window.resetPositioning = function() {
         console.log('🔄 RESETTING BULLETPROOF POSITIONING SYSTEM...');
         
         const currentScrollButton = document.getElementById('smart-scroll-btn');
         if (currentScrollButton && !currentScrollButton.classList.contains('hidden')) {
             // Apply bulletproof positioning
             if (window.forceButtonCenter) {
                 window.forceButtonCenter();
             } else {
                 positionScrollButton();
             }
             console.log('✅ Bulletproof positioning reset');
             
             // Reinstall resize handler
             if (window.installResizeHandler) {
                 window.installResizeHandler();
                 console.log('✅ Bulletproof resize handler reset');
             }
             
             // Comprehensive test
             setTimeout(() => {
                 console.log('🧪 TESTING RESET SYSTEM...');
                 window.testQuickResize();
             }, 400);
         } else {
             console.log('❌ No scroll button to reset');
         }
     };
     
     // FORCE BUTTON REFRESH - Apply bulletproof positioning
     window.refreshButtonPosition = function() {
         console.log('🔄 FORCING BUTTON POSITION REFRESH...');
         
         const currentScrollButton = document.getElementById('smart-scroll-btn');
         if (currentScrollButton && !currentScrollButton.classList.contains('hidden')) {
             // Use the bulletproof positioning system
             if (window.forceButtonCenter) {
                 const success = window.forceButtonCenter();
                 if (success) {
                     console.log('✅ Position refreshed with bulletproof system');
                     // Quick verification
                     setTimeout(() => {
                         window.checkButtonStatus();
                     }, 200);
                 } else {
                     console.warn('⚠️ Bulletproof positioning failed, using fallback');
                     positionScrollButton();
                 }
             } else {
                 console.warn('⚠️ Bulletproof system not available, using fallback');
                 positionScrollButton();
             }
         } else {
             console.log('❌ No scroll button to reposition');
         }
     };
     

     


 window.forceConnectionRefresh = function() {
    console.log('Forcing connection refresh...');
    stopConnectionMonitoring();
    if (currentClusterId) {
        startConnectionMonitoring();
        showInfoMessage('Connection status refreshed');
    } else {
        showErrorMessage('No active cluster session');
    }
};

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
        const currentScrollTop = terminalMessages.scrollTop; // Save current scroll position
        
        historyVisible = !historyVisible;
        if (historyVisible) {
            oldHistory.classList.remove('hidden');
            historyText.textContent = 'Hide History';
            historyIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />';
            
            // When showing history, scroll to top to see the history
            setTimeout(() => {
                if (terminalMessages) {
                    terminalMessages.scrollTop = 0;
                }
            }, 100);
        } else {
            oldHistory.classList.add('hidden');
            historyText.textContent = 'Show History';
            historyIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />';
        
            // When hiding history, simply scroll to bottom and let smart logic handle button
        setTimeout(() => {
            if (terminalMessages) {
                terminalMessages.scrollTop = terminalMessages.scrollHeight;
            }
        }, 100);
        }
        
        // Update scroll button after toggle
        setTimeout(() => {
            if (window.smartScrollChecker) {
                window.smartScrollChecker();
            }
        }, 200);
    });
}

// Initialize smart scroll functionality (bidirectional)
    function initializeSmartScroll() {
    const terminalMessages = document.getElementById('terminal-messages');
        const scrollButton = document.getElementById('smart-scroll-btn');
        const scrollIcon = document.getElementById('scroll-icon');
        const scrollIndicatorText = document.getElementById('scroll-indicator-text');
        const scrollButtonContainer = document.querySelector('.scroll-button-container');
          
        if (!terminalMessages || !scrollButton || !scrollIcon || !scrollButtonContainer) {
        return;
    }
    
        // Set up global reference for positioning
        window.scrollButtonContainer = scrollButtonContainer;
        
        console.log('🎯 INITIALIZING SCROLL BUTTON WITH CHAT CENTER POSITIONING');
    
    let currentScrollDirection = 'down'; // 'up' or 'down'
    
    // Update button appearance based on scroll direction
    function updateButtonAppearance(direction) {
        if (direction === 'down') {
            // Scroll down arrow
            scrollIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" />';
            scrollIcon.style.transform = 'rotate(0deg)';
            if (scrollIndicatorText) scrollIndicatorText.textContent = 'Jump to latest messages';
        } else {
            // Scroll up arrow
            scrollIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18" />';
            scrollIcon.style.transform = 'rotate(0deg)';
            if (scrollIndicatorText) scrollIndicatorText.textContent = 'Jump to older messages';
        }
        currentScrollDirection = direction;
    }
    
    // Intelligent scroll button - only appears when content actually needs scrolling
    function checkScrollPosition() {
        // Check if we're on a page with textbox (chat page)
        const textbox = document.getElementById('terminal-input');
        
        // ALWAYS HIDE BUTTON FIRST - then decide if we should show it
        scrollButton.classList.add('hidden');
        scrollButton.style.display = 'none';
        
        if (!textbox) {
            // No textbox (homepage) - hide container and return
            const container = document.querySelector('.scroll-button-container');
            if (container) container.style.display = 'none';
            console.log('🚫 No textbox - hiding scroll button (homepage)');
            return;
        }
        
        // Force reflow to get accurate measurements after DOM changes
        terminalMessages.offsetHeight;
        
        // Get fresh scroll measurements
        const scrollHeight = terminalMessages.scrollHeight;
        const clientHeight = terminalMessages.clientHeight;
        const scrollTop = terminalMessages.scrollTop;
        
        // FUNDAMENTAL CHECK: Does content actually require scrolling?
        const needsScrolling = scrollHeight > clientHeight + 20; // 20px buffer
        
        if (!needsScrolling) {
            // Content fits perfectly - no scrolling needed, keep button hidden
            return;
        }
        
        // Content is long enough to require scrolling - determine position
        const maxScroll = scrollHeight - clientHeight;
        const scrollPercent = maxScroll > 0 ? scrollTop / maxScroll : 0;
        const distanceFromBottom = maxScroll - scrollTop;
        
        // Position thresholds (more forgiving)
        const isAtVeryTop = scrollTop <= 30;
        const isAtVeryBottom = distanceFromBottom <= 30;
        
        if (isAtVeryTop) {
            // At top of scrollable content - show down arrow (go to latest)
            updateButtonAppearance('down');
            showScrollButton();
        } else if (isAtVeryBottom) {
            // At bottom of scrollable content - show up arrow (go to older content)
            updateButtonAppearance('up');
            showScrollButton();
        } else {
            // In middle of scrollable content - intelligent direction
            if (scrollPercent < 0.4) {
                // Upper portion - suggest going to latest content
                updateButtonAppearance('down');
            } else {
                // Lower portion - suggest going to older content
                updateButtonAppearance('up');
            }
            showScrollButton();
        }
    }
    
    function showScrollButton() {
        // Don't reposition if scroll is in progress
        if (window.scrollInProgress) {
            return;
        }
        
        // Check if we're on a page with textbox (chat page)
        const textbox = document.getElementById('terminal-input');
        if (!textbox) {
            // No textbox (homepage) - hide button completely
            scrollButton.classList.add('hidden');
            scrollButton.style.display = 'none';
            const container = document.querySelector('.scroll-button-container');
            if (container) container.style.display = 'none';
            console.log('🚫 No textbox - hiding scroll button (homepage)');
            return;
        }
        
        // Double-check that content actually needs scrolling before showing
        const scrollHeight = terminalMessages.scrollHeight;
        const clientHeight = terminalMessages.clientHeight;
        const needsScrolling = scrollHeight > clientHeight + 20;
        
        if (!needsScrolling) {
            // Content doesn't need scrolling - force hide and return
            scrollButton.classList.add('hidden');
            scrollButton.style.display = 'none';
            return;
        }
        
        // Position the button intelligently relative to the terminal
        positionScrollButton();
        
        // Content needs scrolling - safe to show button with animation
        scrollButton.classList.remove('hidden');
        scrollButton.style.display = 'block';
        
        // Trigger slide-down animation
        scrollButton.classList.remove('scroll-button-show');
        setTimeout(() => {
            scrollButton.classList.add('scroll-button-show');
        }, 10);
    }
    
    function positionScrollButton() {
        // Don't reposition if scroll is in progress
        if (window.scrollInProgress) {
            console.log('⏸️ Skipping repositioning - scroll in progress');
            return;
        }
        
        // Use the direct positioning system
        if (window.fixButtonPosition) {
            console.log('🎯 Using direct positioning system');
            window.fixButtonPosition();
            return true;
        }
        
        console.warn('⚠️ Direct positioning system not available');
        return false;
    }
    
    // Button click handler
    scrollButton.addEventListener('click', function() {
        if (currentScrollDirection === 'down') {
            // Scroll to bottom
            terminalMessages.scrollTo({
                top: terminalMessages.scrollHeight,
                behavior: 'smooth'
            });
        } else {
            // Scroll to top
            terminalMessages.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        }
    });
    
    // Check position on scroll (but not during programmatic scrolling)
    terminalMessages.addEventListener('scroll', () => {
        if (!window.scrollInProgress) {
            checkScrollPosition();
        }
    });
    
    // Check position when content changes
    const observer = new MutationObserver(() => {
        if (!window.scrollInProgress) {
            checkScrollPosition();
            // Ensure button stays centered when content changes
            setTimeout(() => {
                if (!window.buttonPositionLocked) {
                    positionScrollButton();
                }
            }, 100);
        }
    });
    observer.observe(terminalMessages, { childList: true, subtree: true });
    
         // DIRECT CHAT BUTTON CENTERING - POSITIONED AT TEXTBOX TOP
     function positionButtonInChatCenter() {
         const container = document.querySelector('.scroll-button-container');
         const chat = document.getElementById('terminal-messages');
         const textbox = document.getElementById('terminal-input');
         const scrollButton = document.getElementById('smart-scroll-btn');
         
         if (!container) return;
         
         // If no textbox exists (like on homepage), hide the button completely
         if (!textbox || !chat) {
             if (scrollButton) {
                 scrollButton.classList.add('hidden');
                 console.log('🚫 No textbox found - hiding scroll button');
             }
             container.style.display = 'none';
             return;
         }
         
         // Textbox exists - show container and position button
         container.style.display = 'block';
         container.style.setProperty('display', 'block', 'important');
         
         const chatRect = chat.getBoundingClientRect();
         const textboxRect = textbox.getBoundingClientRect();
         
         // Horizontal: Center of chat area
         const centerX = chatRect.left + (chatRect.width / 2);
         
         // Vertical: Top edge of textbox minus button height (32px) minus small gap (8px)
         const topY = textboxRect.top - 40;
         
         // Direct positioning
         container.style.left = (centerX - 16) + 'px'; // Center horizontally
         container.style.top = topY + 'px'; // Position at textbox top
         container.style.bottom = 'auto'; // Remove bottom positioning
         
         console.log('✅ Button positioned - X:', centerX, 'Y:', topY);
     }
     
     // Check immediately if textbox exists and hide button if not
     const textbox = document.getElementById('terminal-input');
     if (!textbox) {
         const container = document.querySelector('.scroll-button-container');
         const scrollButton = document.getElementById('smart-scroll-btn');
         if (container) container.style.display = 'none';
         if (scrollButton) scrollButton.classList.add('hidden');
         console.log('🚫 No textbox - hiding scroll button immediately');
     } else {
         // Position immediately and on resize
         positionButtonInChatCenter();
     }
     
     window.addEventListener('resize', () => {
         setTimeout(positionButtonInChatCenter, 50);
     });
     
     // Global function for manual testing
     window.fixButtonPosition = positionButtonInChatCenter;
     
     console.log('✅ Direct positioning active - button will stay centered');
    
         // Monitor terminal container and input changes
     const terminalContainer = document.getElementById('terminal-container');
     const terminalInput = document.getElementById('terminal-input');
     
     if (terminalContainer) {
         const terminalObserver = new MutationObserver(() => {
             // Only reposition if not scrolling
             if (window.scrollInProgress) return;
             
             const currentScrollButton = document.getElementById('smart-scroll-btn');
             if (currentScrollButton && !currentScrollButton.classList.contains('hidden')) {
                 setTimeout(() => {
                     console.log('🔄 Terminal changed - repositioning button');
                     if (window.fixButtonPosition) {
                         window.fixButtonPosition();
                     }
                 }, 50);
             }
         });
         terminalObserver.observe(terminalContainer, { 
             attributes: true, 
             attributeFilter: ['class', 'style'] 
         });
     }
     
     // Also monitor textbox for position changes
     if (terminalInput) {
         const inputObserver = new ResizeObserver(() => {
             if (window.scrollInProgress) return;
             
             const currentScrollButton = document.getElementById('smart-scroll-btn');
             if (currentScrollButton && !currentScrollButton.classList.contains('hidden')) {
                 setTimeout(() => {
                     console.log('🔄 Textbox resized - repositioning button');
                     if (window.fixButtonPosition) {
                         window.fixButtonPosition();
                     }
                 }, 50);
             }
         });
         inputObserver.observe(terminalInput);
     }
    
    // Expose checker function globally for manual triggers
    window.smartScrollChecker = checkScrollPosition;
    
    // Keep debug functions for troubleshooting (can be removed in production)
    window.forceShowScrollButton = function() {
        updateButtonAppearance('down');
        showScrollButton();
    };
    
    window.debugScrollButton = function() {
        console.log('Button element exists:', !!scrollButton);
        console.log('Terminal scroll info:', {
            scrollHeight: terminalMessages?.scrollHeight,
            clientHeight: terminalMessages?.clientHeight,
            scrollTop: terminalMessages?.scrollTop
        });
    checkScrollPosition();
    };
    
    window.forceHideScrollButton = function() {
    console.log('Force hiding scroll button');
    scrollButton.classList.add('hidden');
};

window.updateHistoryButton = function() {
    console.log('Manually updating history button visibility');
    updateHistoryButtonVisibility();
};

window.forceHideHistoryButton = function() {
    console.log('Force hiding history button');
    const historyToggleBtn = document.getElementById('history-toggle-btn');
    if (historyToggleBtn) {
        historyToggleBtn.classList.add('hidden');
        historyToggleBtn.style.setProperty('display', 'none', 'important');
        console.log('✅ History button force hidden');
    }
};

window.checkHistoryContent = function() {
    const oldHistory = document.getElementById('old-history');
    const historyToggleBtn = document.getElementById('history-toggle-btn');
    
    console.log('📚 HISTORY DEBUG INFO:');
    console.log('Old history element exists:', !!oldHistory);
    console.log('History button exists:', !!historyToggleBtn);
    
    if (oldHistory) {
        console.log('History children count:', oldHistory.children.length);
        console.log('History content:', oldHistory.innerHTML.substring(0, 200) + '...');
        
        let commandCount = 0;
        for (let i = 0; i < oldHistory.children.length; i++) {
            const child = oldHistory.children[i];
            if (child.classList.contains('terminal-message') && 
                child.textContent.includes('user@k8s-terminal:~$')) {
                commandCount++;
            }
        }
        console.log('Actual command count:', commandCount);
    }
    
    if (historyToggleBtn) {
        console.log('History button hidden:', historyToggleBtn.classList.contains('hidden'));
    }
};
    
    window.checkScrollState = function() {
        const scrollHeight = terminalMessages.scrollHeight;
        const clientHeight = terminalMessages.clientHeight;
        const scrollTop = terminalMessages.scrollTop;
        const needsScrolling = scrollHeight > clientHeight + 20;
        const maxScroll = scrollHeight - clientHeight;
        const distanceFromBottom = maxScroll - scrollTop;
        const distanceFromTop = scrollTop;
        const isAtTop = distanceFromTop <= 30;
        const isAtBottom = distanceFromBottom <= 30;
        
        console.log('Smart scroll analysis:', {
            scrollHeight,
            clientHeight,
            scrollTop,
            needsScrolling,
            distanceFromTop,
            distanceFromBottom,
            isAtTop,
            isAtBottom,
            buttonVisible: !scrollButton.classList.contains('hidden'),
            expectedDirection: isAtTop ? 'down' : isAtBottom ? 'up' : 'varies',
            buttonPosition: {
                bottom: scrollButtonContainer.style.bottom,
                left: scrollButtonContainer.style.left,
                centered: 'precisely centered on top edge of textbox',
                transform: scrollButtonContainer.style.transform
            }
        });
        return { needsScrolling, isAtTop, isAtBottom };
    };
    
    window.repositionScrollButton = function() {
        console.log('Manually repositioning scroll button');
        positionScrollButton();
    };
    
    // Test function to verify perfect centering
    window.testButtonCentering = function() {
        const terminalInput = document.getElementById('terminal-input');
        const scrollButtonContainer = document.querySelector('.scroll-button-container');
        const scrollButton = document.getElementById('smart-scroll-btn');
        
        if (!terminalInput || !scrollButtonContainer || !scrollButton) {
            console.error('Elements not found:', {
                terminalInput: !!terminalInput,
                scrollButtonContainer: !!scrollButtonContainer,
                scrollButton: !!scrollButton
            });
            return;
        }
        
        const inputRect = terminalInput.getBoundingClientRect();
        const buttonRect = scrollButton.getBoundingClientRect();
        
        const inputCenter = inputRect.left + (inputRect.width / 2);
        const buttonCenter = buttonRect.left + (buttonRect.width / 2);
        const centerDifference = Math.abs(inputCenter - buttonCenter);
        
        console.log('Detailed centering test:', {
            textboxInfo: {
                left: inputRect.left,
                width: inputRect.width,
                center: inputCenter,
                centerPercentage: ((inputCenter / window.innerWidth) * 100).toFixed(1) + '%'
            },
            buttonInfo: {
                left: buttonRect.left,
                width: buttonRect.width,
                center: buttonCenter,
                centerPercentage: ((buttonCenter / window.innerWidth) * 100).toFixed(1) + '%'
            },
            comparison: {
                difference: centerDifference.toFixed(2) + 'px',
                isPerfectlyCentered: centerDifference < 1,
                status: centerDifference < 1 ? 'CENTERED' : 'OFF-CENTER'
            },
            containerStyles: {
                left: scrollButtonContainer.style.left,
                transform: scrollButtonContainer.style.transform,
                position: scrollButtonContainer.style.position
            }
        });
        
        return centerDifference < 1;
    };
    
    // Force perfect centering function
    window.forceButtonCenter = function() {
        console.log('Forcing button to perfect center...');
        
        const terminalInput = document.getElementById('terminal-input');
        const scrollButtonContainer = document.querySelector('.scroll-button-container');
        const scrollButton = document.getElementById('smart-scroll-btn');
        
        if (!terminalInput || !scrollButtonContainer || !scrollButton) {
            console.error('Required elements not found');
            return;
        }
        
        const inputRect = terminalInput.getBoundingClientRect();
        const inputCenterX = inputRect.left + (inputRect.width / 2);
        const inputTopY = inputRect.top;
        const bottom = window.innerHeight - inputTopY;
        
        console.log('Manual centering calculation:', {
            inputLeft: inputRect.left,
            inputWidth: inputRect.width,
            inputCenter: inputCenterX,
            inputTop: inputTopY,
            bottomDistance: bottom
        });
        
        // Remove the container and recreate it to eliminate any style conflicts
        const newContainer = document.createElement('div');
        newContainer.className = 'scroll-button-container';
        newContainer.style.cssText = `
            position: fixed !important;
            left: ${inputCenterX}px !important;
            bottom: ${bottom}px !important;
            transform: translate(-50%, -50%) !important;
            z-index: 50 !important;
            pointer-events: none !important;
            margin: 0 !important;
            padding: 0 !important;
            width: auto !important;
            height: auto !important;
        `;
        
        // Move the button to the new container
        newContainer.appendChild(scrollButton);
        
        // Replace the old container
        scrollButtonContainer.parentNode.replaceChild(newContainer, scrollButtonContainer);
        
        // Update the global reference
        window.scrollButtonContainer = newContainer;
        
        console.log('Button container recreated and repositioned');
        
        // Test the result
        setTimeout(() => {
            window.testButtonCentering();
        }, 50);
    };
    
    // Visual debug helper
    window.showTextboxCenter = function() {
        const terminalInput = document.getElementById('terminal-input');
        if (!terminalInput) return;
        
        // Remove any existing markers
        document.querySelectorAll('.center-marker').forEach(el => el.remove());
        
        const inputRect = terminalInput.getBoundingClientRect();
        const inputCenterX = inputRect.left + (inputRect.width / 2);
        const inputTopY = inputRect.top;
        
        // Create a visual marker at the exact center
        const marker = document.createElement('div');
        marker.className = 'center-marker';
        marker.style.cssText = `
            position: fixed;
            left: ${inputCenterX}px;
            top: ${inputTopY}px;
            width: 4px;
            height: 20px;
            background: red;
            z-index: 100;
            transform: translateX(-50%);
            pointer-events: none;
        `;
        document.body.appendChild(marker);
        
        console.log('🔴 Red marker placed at textbox center:', inputCenterX);
        
        // Remove marker after 5 seconds
        setTimeout(() => marker.remove(), 5000);
    };
    
    // Simple test - just show where the button SHOULD be
    window.showWhereButtonShouldBe = function() {
        const terminalInput = document.getElementById('terminal-input');
        if (!terminalInput) return;
        
        const inputRect = terminalInput.getBoundingClientRect();
        const inputCenterX = inputRect.left + (inputRect.width / 2);
        const inputTopY = inputRect.top;
        
        // Remove existing test buttons
        document.querySelectorAll('.test-button').forEach(el => el.remove());
        
        // Create a test button at EXACT position
        const testButton = document.createElement('div');
        testButton.className = 'test-button';
        testButton.innerHTML = '📍';
        testButton.style.cssText = `
            position: fixed !important;
            left: ${inputCenterX}px !important;
            top: ${inputTopY}px !important;
            transform: translate(-50%, -50%) !important;
            z-index: 999 !important;
            background: yellow !important;
            border: 2px solid red !important;
            width: 32px !important;
            height: 32px !important;
            border-radius: 50% !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 16px !important;
            pointer-events: none !important;
        `;
        
        document.body.appendChild(testButton);
        
        console.log('📍 YELLOW TEST BUTTON shows where scroll button should be');
        console.log('Center calculated at:', inputCenterX);
        
        // Remove after 10 seconds
        setTimeout(() => testButton.remove(), 10000);
    };
    
    // FORCE CENTER BUTTON AT TOP OF TEXTBOX (recreates button with stable positioning)
    window.fixButtonNow = function() {
        console.log('🎯 FORCING BUTTON RECREATION AT TEXTBOX CENTER...');
        
        // Clear any scroll state
        window.scrollInProgress = false;
        
        const terminalContainer = document.getElementById('terminal-container');
        const terminalInput = document.getElementById('terminal-input');
        
        if (!terminalContainer || !terminalInput) {
            console.error('❌ Required elements not found');
            return;
        }
        
        // Remove any existing button/container
        const existingButton = document.getElementById('smart-scroll-btn');
        const existingContainer = document.querySelector('.scroll-button-container');
        if (existingButton) existingButton.remove();
        if (existingContainer) existingContainer.remove();
        
        // Get actual chat messages area and textbox position (same as auto positioning)
        const terminalMessages = document.getElementById('terminal-messages');
        const inputRect = terminalInput.getBoundingClientRect();
        
        if (!terminalMessages) {
            console.error('❌ Terminal messages element not found for fixButtonNow');
            return;
        }
        
        const messagesRect = terminalMessages.getBoundingClientRect();
        const chatCenterX = messagesRect.left + (messagesRect.width / 2);
        const buttonY = inputRect.top - 50;
        
        console.log('📐 CHAT CENTER POSITIONING:', {
            inputTop: inputRect.top,
            chatCenterX: chatCenterX,
            buttonY: buttonY,
            approach: 'Centering on chat area, not entire page'
        });
        
        // Create new button structure
        const newContainer = document.createElement('div');
        newContainer.className = 'scroll-button-container';
        
        const newButton = document.createElement('button');
        newButton.id = 'smart-scroll-btn';
        newButton.className = 'glass-effect hover:bg-terminal-accent/10 text-terminal-accent border border-terminal-accent/30 hover:border-terminal-accent/50 w-8 h-8 rounded-full shadow-xl backdrop-blur-md transition-all duration-300 ease-out hover:scale-105 group flex items-center justify-center';
        
        newButton.innerHTML = `
            <svg id="scroll-icon" class="w-4 h-4 transition-transform duration-300" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 13.5 12 21m0 0-7.5-7.5M12 21V3" />
            </svg>
            <div id="scroll-indicator" class="absolute -top-8 left-1/2 transform -translate-x-1/2 bg-terminal-surface/95 border border-terminal-accent/20 text-terminal-text text-xs px-3 py-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all duration-200 whitespace-nowrap shadow-lg backdrop-blur-sm">
                <span id="scroll-indicator-text">Click to scroll</span>
                <div class="absolute -bottom-1 left-1/2 transform -translate-x-1/2 w-2 h-2 bg-terminal-surface/95 border-r border-b border-terminal-accent/20 rotate-45"></div>
            </div>
        `;
        
        // Position at CENTER of chat area (chat-specific centering)
        newContainer.style.cssText = `
            position: fixed !important;
            left: ${chatCenterX}px !important;
            top: ${buttonY}px !important;
            transform: translateX(-50%) !important;
            z-index: 50 !important;
            pointer-events: none !important;
            margin: 0 !important;
            padding: 0 !important;
        `;
        
        newButton.style.cssText = `
            pointer-events: auto !important;
            position: relative !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
        `;
        
        // Add to page
        newContainer.appendChild(newButton);
        document.body.appendChild(newContainer);
        
        // Update global reference
        window.scrollButtonContainer = newContainer;
        
                         console.log('✨ BUTTON CREATED AT CHAT CENTER!');
         
         // Add click functionality
        newButton.addEventListener('click', function() {
            console.log('🔥 Button clicked - preventing repositioning during scroll');
            
            // Prevent repositioning during scroll
            window.scrollInProgress = true;
            
            const terminalMessages = document.getElementById('terminal-messages');
            if (terminalMessages) {
                if (newButton.querySelector('#scroll-icon path').getAttribute('d').includes('M19.5 13.5')) {
                    // Scroll down
                    terminalMessages.scrollTo({
                        top: terminalMessages.scrollHeight,
                        behavior: 'smooth'
                    });
                } else {
                    // Scroll up
                    terminalMessages.scrollTo({
                        top: 0,
                        behavior: 'smooth'
                    });
                }
            }
            
            // Re-enable repositioning after scroll completes
            setTimeout(() => {
                window.scrollInProgress = false;
                console.log('✅ Scroll complete - repositioning re-enabled');
            }, 1000);
        });
        
        // Test final position
        setTimeout(() => {
            const buttonRect = newButton.getBoundingClientRect();
            const buttonCenter = buttonRect.left + (buttonRect.width / 2);
            const difference = Math.abs(chatCenterX - buttonCenter);
            
            console.log('🎯 FINAL VERIFICATION:', {
                expectedChatCenter: chatCenterX,
                actualButtonCenter: buttonCenter,
                difference: difference.toFixed(2) + 'px',
                isCentered: difference < 1 ? '✅ PERFECTLY CENTERED ON CHAT!' : '❌ Still off-center'
            });
        }, 100);
        
        return newButton;
    };
    
    // Complete verification of button positioning implementation
    window.checkButtonPositioning = function() {
        console.log('🔍 COMPREHENSIVE BUTTON POSITIONING CHECK...');
        
        const terminalInput = document.getElementById('terminal-input');
        const button = document.getElementById('smart-scroll-btn');
        const container = window.scrollButtonContainer;
        
        if (!terminalInput || !button || !container) {
            console.error('❌ MISSING ELEMENTS:', {
                terminalInput: !!terminalInput,
                button: !!button,
                container: !!container
            });
            return;
        }
        
        const inputRect = terminalInput.getBoundingClientRect();
        const buttonRect = button.getBoundingClientRect();
        const expectedCenter = inputRect.left + (inputRect.width / 2);
        const actualCenter = buttonRect.left + (buttonRect.width / 2);
        const centerDifference = Math.abs(expectedCenter - actualCenter);
        const verticalGap = inputRect.top - buttonRect.bottom;
        
        // Check positioning accuracy
        const isWellCentered = centerDifference < 2;
        const isWellPositioned = verticalGap > 20 && verticalGap < 80;
        
        console.log('📊 POSITIONING ANALYSIS:', {
            // Horizontal positioning
            horizontalAlignment: {
                textboxCenter: expectedCenter.toFixed(1),
                buttonCenter: actualCenter.toFixed(1),
                difference: centerDifference.toFixed(2) + 'px',
                status: isWellCentered ? '✅ WELL CENTERED' : '❌ OFF-CENTER'
            },
            
            // Vertical positioning
            verticalAlignment: {
                gapAboveTextbox: verticalGap.toFixed(0) + 'px',
                buttonTop: buttonRect.top.toFixed(1),
                textboxTop: inputRect.top.toFixed(1),
                status: isWellPositioned ? '✅ GOOD SPACING' : '❌ TOO CLOSE/FAR'
            },
            
            // Container properties
            containerInfo: {
                position: container.style.position,
                left: container.style.left,
                top: container.style.top,
                transform: container.style.transform,
                zIndex: container.style.zIndex
            },
            
            // Overall assessment
            overallStatus: (isWellCentered && isWellPositioned) ? 
                '✅ POSITIONING IS PERFECT' : '⚠️ NEEDS ADJUSTMENT',
                
            // Recommendations
            recommendations: [
                !isWellCentered ? '• Run fixButtonNow() to correct horizontal alignment' : null,
                !isWellPositioned ? '• Check vertical spacing (should be 40-60px above textbox)' : null,
                'Test with: testResizeBehavior() to verify resize stability'
            ].filter(Boolean)
        });
        
        return {
            centered: isWellCentered,
            positioned: isWellPositioned,
            overall: isWellCentered && isWellPositioned
        };
    };
    
    // Complete test suite for button positioning
    window.runAllPositioningTests = function() {
        console.log('🧪 RUNNING COMPLETE POSITIONING TEST SUITE...');
        console.log('================================================');
        
        // Test 1: Current positioning
        console.log('1️⃣ CHECKING CURRENT POSITION:');
        const currentCheck = window.checkButtonPositioning();
        
        // Test 2: Textbox center positioning
        console.log('\n2️⃣ TESTING TEXTBOX CENTER LOGIC:');
        window.testTextboxCenterPositioning();
        
        // Test 3: Resize behavior
        setTimeout(() => {
            console.log('\n3️⃣ TESTING RESIZE BEHAVIOR:');
            window.testResizeBehavior();
            
            // Test 4: Final verification
            setTimeout(() => {
                console.log('\n4️⃣ FINAL VERIFICATION:');
                const finalCheck = window.checkButtonPositioning();
                
                console.log('\n🎯 TEST SUITE SUMMARY:');
                console.log('================================================');
                console.log('Current Position:', currentCheck.overall ? '✅ GOOD' : '❌ NEEDS FIX');
                console.log('Resize Stability: Check console above for resize test results');
                console.log('Recommendation:', finalCheck.overall ? 
                    '✅ Button positioning is working perfectly!' : 
                    '⚠️ Run fixButtonNow() to correct positioning');
                console.log('================================================');
            }, 500);
        }, 300);
    };
    
    // Test textbox center positioning (for verification)
    window.testTextboxCenterPositioning = function() {
        console.log('🧪 TESTING TEXTBOX CENTER POSITIONING...');
        
        // Clear any scroll state and force repositioning
        window.scrollInProgress = false;
        
        // Trigger default positioning
        positionScrollButton();
        
        // Verify result
        setTimeout(() => {
            const terminalInput = document.getElementById('terminal-input');
            const button = document.getElementById('smart-scroll-btn');
            
            if (terminalInput && button) {
                const inputRect = terminalInput.getBoundingClientRect();
                const buttonRect = button.getBoundingClientRect();
                
                const textboxCenter = inputRect.left + (inputRect.width / 2);
                const buttonCenter = buttonRect.left + (buttonRect.width / 2);
                const difference = Math.abs(textboxCenter - buttonCenter);
                
                console.log('🎯 TEXTBOX CENTER POSITIONING TEST:', {
                    textboxCenter: textboxCenter,
                    buttonCenter: buttonCenter,
                    difference: difference.toFixed(2) + 'px',
                    isCentered: difference < 2 ? '✅ PERFECTLY CENTERED!' : '❌ Needs adjustment',
                    deviceType: window.innerWidth < 768 ? '📱 Mobile' : '💻 Desktop',
                    textboxWidth: inputRect.width,
                    viewportWidth: window.innerWidth,
                    positionAboveTextbox: (inputRect.top - buttonRect.bottom).toFixed(0) + 'px gap'
                });
            }
        }, 200);
    };
    
    // Test resize behavior
    window.testResizeBehavior = function() {
        console.log('🔄 TESTING RESIZE BEHAVIOR...');
        
        // Get initial position
        const terminalInput = document.getElementById('terminal-input');
        const button = document.getElementById('smart-scroll-btn');
        
        if (!terminalInput || !button) {
            console.error('❌ Required elements not found');
            return;
        }
        
        const initialInputRect = terminalInput.getBoundingClientRect();
        const initialButtonRect = button.getBoundingClientRect();
        const initialInputCenter = initialInputRect.left + (initialInputRect.width / 2);
        const initialButtonCenter = initialButtonRect.left + (initialButtonRect.width / 2);
        
        console.log('📐 INITIAL POSITION:', {
            textboxCenter: initialInputCenter,
            buttonCenter: initialButtonCenter,
            difference: Math.abs(initialInputCenter - initialButtonCenter).toFixed(2) + 'px'
        });
        
        // Simulate resize event
        console.log('🔄 Simulating resize event...');
        window.dispatchEvent(new Event('resize'));
        
        // Check position after resize handling
        setTimeout(() => {
            const newInputRect = terminalInput.getBoundingClientRect();
            const newButtonRect = button.getBoundingClientRect();
            const newInputCenter = newInputRect.left + (newInputRect.width / 2);
            const newButtonCenter = newButtonRect.left + (newButtonRect.width / 2);
            const finalDifference = Math.abs(newInputCenter - newButtonCenter);
            
            console.log('✅ POST-RESIZE POSITION:', {
                textboxCenter: newInputCenter,
                buttonCenter: newButtonCenter,
                difference: finalDifference.toFixed(2) + 'px',
                resizeBehaviorWorking: finalDifference < 2 ? '✅ YES' : '❌ NO - Button shifted',
                recommendation: finalDifference >= 2 ? 'Run fixButtonNow() to correct' : 'Positioning is stable'
            });
        }, 300);
    };
    
    window.getScrollButtonInfo = function() {
        const terminalContainer = document.getElementById('terminal-container');
        const terminalRect = terminalContainer ? terminalContainer.getBoundingClientRect() : null;
        
        console.log('Scroll button positioning info:', {
            terminalContainer: !!terminalContainer,
            terminalVisible: terminalContainer && !terminalContainer.classList.contains('hidden'),
            terminalRect: terminalRect,
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            },
            buttonContainer: {
                bottom: scrollButtonContainer.style.bottom,
                left: scrollButtonContainer.style.left,
                centered: 'precisely centered on top edge of textbox',
                visible: !scrollButton.classList.contains('hidden')
            }
        });
        
        return {
            terminalRect,
            buttonVisible: !scrollButton.classList.contains('hidden'),
            buttonPosition: {
                bottom: scrollButtonContainer.style.bottom,
                left: scrollButtonContainer.style.left,
                centered: 'horizontally centered relative to terminal container'
            }
        };
    };
    
    // Initial check with delay to ensure content is rendered
    setTimeout(() => {
        positionScrollButton();
        checkScrollPosition();
    }, 200);
    
                // Final setup of direct positioning system
    setTimeout(() => {
        const textbox = document.getElementById('terminal-input');
        if (!textbox) {
            console.log('🚫 HOMEPAGE MODE - Scroll button hidden');
            console.log('📍 Navigate to a chat session to see the scroll button');
            return;
        }
        
        console.log('✅ TEXTBOX-TOP POSITIONING SYSTEM ACTIVE');
        console.log('🎯 Button positioned at top edge of chat textbox');
        console.log('');
        console.log('📚 CEO GPU DISCOUNT MODE - HISTORY BUTTON SYSTEM ACTIVE');
        console.log('🎯 History button ONLY shows for actual user commands');
        console.log('🚫 System messages do NOT trigger history button');
        console.log('⚡ Periodic enforcement ensures button stays hidden');
        console.log('');
        console.log('🧪 TEST: Resize your browser window now');
        console.log('');
        console.log('🛠️  Commands:');
        console.log('   fixButtonPosition() - Apply positioning manually');
        console.log('   updateHistoryButton() - Update history button visibility');
        console.log('   forceHideHistoryButton() - Force hide history button');
        console.log('   checkHistoryContent() - Debug history content and button state');
    }, 1000);
    
    // Periodic check to ensure button is correctly shown/hidden
    setInterval(() => {
        const currentTerminalMessages = document.getElementById('terminal-messages');
        const currentScrollButton = document.getElementById('smart-scroll-btn');
        
        if (!currentTerminalMessages || !currentScrollButton) return;
        
        const scrollHeight = currentTerminalMessages.scrollHeight;
        const clientHeight = currentTerminalMessages.clientHeight;
        const needsScrolling = scrollHeight > clientHeight + 20;
        
        if (!needsScrolling && !currentScrollButton.classList.contains('hidden')) {
            // Content doesn't need scrolling but button is showing - hide it
            currentScrollButton.classList.add('hidden');
            currentScrollButton.style.display = 'none';
        } else if (needsScrolling && currentScrollButton.classList.contains('hidden')) {
            // Content needs scrolling but button is hidden - run check to potentially show it
            checkScrollPosition();
        }
    }, 2000); // Check every 2 seconds
    
    // CEO GPU DISCOUNT MODE: Periodic history button enforcement
    setInterval(() => {
        const histBtn = document.getElementById('history-toggle-btn');
        const oldHistory = document.getElementById('old-history');
        
        if (histBtn && !histBtn.classList.contains('hidden')) {
            // Button is showing - verify it should be
            let shouldShow = false;
            
            if (oldHistory && oldHistory.children.length > 0) {
                for (let i = 0; i < oldHistory.children.length; i++) {
                    const child = oldHistory.children[i];
                    const text = child.textContent || '';
                    
                    if (child.classList.contains('terminal-message') && 
                        text.includes('user@k8s-terminal:~$') &&
                        !text.includes('Connected to') &&
                        !text.includes('Terminal ready') &&
                        !text.includes('Type \'help\'')) {
                        
                        const commandPart = text.split('user@k8s-terminal:~$')[1];
                        if (commandPart && commandPart.trim() && 
                            commandPart.trim() !== 'clear' &&
                            commandPart.trim() !== 'history') {
                            shouldShow = true;
                            break;
                        }
                    }
                }
            }
            
            if (!shouldShow) {
                histBtn.classList.add('hidden');
                histBtn.style.setProperty('display', 'none', 'important');
                console.log('🎯 CEO ENFORCEMENT: History button force hidden');
            }
        }
    }, 1000); // Check every 1 second for bulletproof enforcement
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

// Auto-scroll to bottom
function autoScrollToBottom() {
    const terminalMessages = document.getElementById('terminal-messages');
    if (terminalMessages) {
        terminalMessages.scrollTop = terminalMessages.scrollHeight;
    }
}
