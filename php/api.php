<?php
header('Content-Type: application/json');

// Database configuration
$host = 'postgres';
$db = 'policy_db';
$user = 'user';
$pass = 'password';
$dsn = "pgsql:host=$host;port=5432;dbname=$db";
$qdrant_url = 'http://qdrant:6333';
$ollama_url = 'http://host.docker.internal:11434/api/chat'; // Assuming direct access for now, or via python proxy? 
// Actually, better to route LLM request via Python or direct if possible. 
// For simplicity, let's call the Python API if we had an endpoint for generic chat.
// But we didn't add one. So I will do a simple RAG here.

// NOTE: In a real PHP app, we'd use a client library. Here we do raw cURL.

$input = json_decode(file_get_contents('php://input'), true);
$query = $input['query'] ?? '';

if (!$query) {
    echo json_encode(['error' => 'No query provided']);
    exit;
}

try {
    // 1. Vector Search (Qdrant)
    // We need embeddings for the query. 
    // Usually we need the same embedding model. 
    // Since we can't easily run HuggingFace in PHP, we should expose an endpoint in Python for "search" or "chat".
    // Making a strategic decision to add a /chat endpoint to Python Main.py is better.
    
    // Let's redirect to Python API for the heavy lifting.
    // Bypass n8n and call Python API directly for robustness
    $target_url = 'http://python_api:8000/api/chat'; 

    
    // Fallback if we hadn't added it yet (I will add it).
    
    $ch = curl_init($target_url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode(['query' => $query]));
    curl_setopt($ch, CURLOPT_TIMEOUT, 120);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 10);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        throw new Exception("Python API Error: " . $response);
    }
    
    echo $response;

} catch (Exception $e) {
    echo json_encode(['error' => $e->getMessage()]);
}
?>
