<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Policy Assistant</title>
    <style>
        :root {
            --primary: #2563eb;
            --bg: #f8fafc;
            --chat-bg: #ffffff;
            --user-msg: #eff6ff;
            --bot-msg: #f1f5f9;
        }
        * {
            box-sizing: border-box;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg);
            margin: 0;
            display: flex;
            justify-content: center;
            height: 100vh;
        }
        .container {
            width: 100%;
            max-width: 800px;
            background: var(--chat-bg);
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
            display: flex;
            flex-direction: column;
            height: 100%;
        }
        .header {
            padding: 1rem;
            border-bottom: 1px solid #e2e8f0;
            background: white;
            z-index: 10;
        }
        .header h1 {
            margin: 0;
            font-size: 1.25rem;
            color: #0f172a;
        }
        .chat-window {
            flex: 1;
            overflow-y: auto;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        .message {
            max-width: 80%;
            padding: 1rem;
            border-radius: 0.5rem;
            line-height: 1.5;
        }
        .message.user {
            align-self: flex-end;
            background-color: var(--user-msg);
            color: #1e3a8a;
        }
        .message.bot {
            align-self: flex-start;
            background-color: var(--bot-msg);
            color: #334155;
        }
        .citations {
            margin-top: 0.5rem;
            font-size: 0.875rem;
            border-top: 1px solid #cbd5e1;
            padding-top: 0.5rem;
        }
        .citations a {
            color: var(--primary);
            text-decoration: none;
            display: block;
            margin-bottom: 0.25rem;
        }
        .input-area {
            padding: 1.5rem;
            border-top: 1px solid #e2e8f0;
            background: white;
            display: flex;
            gap: 1rem;
        }
        input {
            flex: 1;
            padding: 0.75rem;
            border: 1px solid #cbd5e1;
            border-radius: 0.375rem;
            font-size: 1rem;
            outline: none;
        }
        input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
        }
        button {
            padding: 0.75rem 1.5rem;
            background-color: var(--primary);
            color: white;
            border: none;
            border-radius: 0.375rem;
            font-weight: 500;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        button:hover {
            background-color: #1d4ed8;
        }
        button:disabled {
            background-color: #94a3b8;
            cursor: not-allowed;
        }
        .loading {
            align-self: flex-start;
            background-color: var(--bot-msg);
            color: #334155;
            padding: 1rem;
            border-radius: 0.5rem;
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }
        .dot {
            width: 8px;
            height: 8px;
            background-color: #64748b;
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out both;
        }
        .dot:nth-child(1) { animation-delay: -0.32s; }
        .dot:nth-child(2) { animation-delay: -0.16s; }
        
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Policy Intelligence Assistant</h1>
        </div>
        <div class="chat-window" id="chat">
            <div class="message bot">
                Hello! I can help you answer questions about the privacy policies of companies in the database. Ask me anything!
            </div>
        </div>
        <div class="input-area">
            <input type="text" id="query" placeholder="Ask a question about a company..." />
            <button id="sendBtn">Send</button>
        </div>
    </div>

    <script>
        const chat = document.getElementById('chat');
        const queryInput = document.getElementById('query');
        const sendBtn = document.getElementById('sendBtn');
        let loadingElement = null;

        function appendMessage(text, isUser, sources = []) {
            const div = document.createElement('div');
            div.className = `message ${isUser ? 'user' : 'bot'}`;
            
            let content = text;
            if (sources && sources.length > 0) {
                content += '<div class="citations"><strong>Sources:</strong>';
                sources.forEach(s => {
                    content += `<a href="${s.url}" target="_blank">${s.domain} (${s.type})</a>`;
                });
                content += '</div>';
            }
            
            div.innerHTML = content;
            chat.appendChild(div);
            // If loading bubble exists, move it to bottom or ensure msg is before it? 
            // Actually usually we remove loading before adding msg.
            chat.scrollTop = chat.scrollHeight;
        }

        function showLoading() {
            if (loadingElement) return;
            const div = document.createElement('div');
            div.className = 'loading';
            div.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
            chat.appendChild(div);
            loadingElement = div;
            chat.scrollTop = chat.scrollHeight;
        }

        function hideLoading() {
            if (loadingElement) {
                loadingElement.remove();
                loadingElement = null;
            }
        }

        async function sendMessage() {
            const text = queryInput.value.trim();
            if (!text) return;

            appendMessage(text, true);
            queryInput.value = '';
            queryInput.disabled = true;
            sendBtn.disabled = true;
            
            showLoading();

            // Safety timeout to re-enable in case of net error/hang
            const safetyTimeout = setTimeout(() => {
                if (queryInput.disabled) {
                    hideLoading();
                    queryInput.disabled = false;
                    sendBtn.disabled = false;
                    appendMessage("Request timed out on client side.", false);
                }
            }, 125000); 

            try {
                const res = await fetch('api.php', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ query: text })
                });
                const data = await res.json();
                
                hideLoading();

                if (data.error) {
                    appendMessage("Error: " + data.error, false);
                } else {
                    appendMessage(data.answer, false, data.sources);
                }
            } catch (e) {
                hideLoading();
                appendMessage("Failed to contact server.", false);
            } finally {
                clearTimeout(safetyTimeout);
                queryInput.disabled = false;
                sendBtn.disabled = false;
                queryInput.focus();
            }
        }

        sendBtn.addEventListener('click', sendMessage);
        queryInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    </script>
</body>
</html>
