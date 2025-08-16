/**
 * Proxy Server for XML API
 * Handles CORS and HTTPS certificate issues
 */

const http = require('http');
const https = require('https');
const url = require('url');

const PORT = 8080;
// NOTE: These should be configured dynamically from database (parkings table)
// This file is deprecated - use Flask proxy instead
const TARGET_HOST = 'CONFIGURE_FROM_DB';  // Should be loaded from parkings table
const TARGET_PORT = 8443;
const TARGET_PATH = '/CustomerMediaWebService';

// Create HTTP server
const server = http.createServer((req, res) => {
    console.log(`[${new Date().toLocaleTimeString()}] ${req.method} ${req.url}`);
    
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept');
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    
    // Handle preflight
    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }
    
    // Parse the request URL
    const parsedUrl = url.parse(req.url);
    
    // Add basic auth if not present
    let headers = { ...req.headers };
    if (!headers.authorization) {
        // Add default credentials
        const auth = Buffer.from('2022:2022').toString('base64');
        headers.authorization = `Basic ${auth}`;
    }
    
    // Prepare proxy request options
    const options = {
        hostname: TARGET_HOST,
        port: TARGET_PORT,
        path: TARGET_PATH + parsedUrl.path,
        method: req.method,
        headers: {
            ...headers,
            host: TARGET_HOST,
            'Content-Type': headers['content-type'] || 'application/xml',
            'Accept': headers['accept'] || 'application/xml'
        },
        // Ignore self-signed certificate
        rejectUnauthorized: false
    };
    
    // Log the full URL being requested
    console.log(`  -> Proxying to: https://${TARGET_HOST}:${TARGET_PORT}${TARGET_PATH}${parsedUrl.path}`);
    console.log(`  -> Auth: ${headers.authorization ? 'Present' : 'Missing'}`);
    
    // Create proxy request
    const proxyReq = https.request(options, (proxyRes) => {
        // Copy status code
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        
        // Pipe the response
        proxyRes.pipe(res);
        
        // Log response
        console.log(`  -> Response: ${proxyRes.statusCode} ${proxyRes.statusMessage || ''}`);
        
        // Log response headers for debugging
        if (proxyRes.statusCode === 401) {
            console.log(`  -> 401 Unauthorized - Check credentials`);
            console.log(`  -> WWW-Authenticate: ${proxyRes.headers['www-authenticate'] || 'Not provided'}`);
        }
    });
    
    // Handle errors
    proxyReq.on('error', (error) => {
        console.error(`  -> Error: ${error.message}`);
        res.writeHead(502);
        res.end(JSON.stringify({ error: 'Proxy Error', message: error.message }));
    });
    
    // Pipe request body
    req.pipe(proxyReq);
});

server.listen(PORT, () => {
    console.log('================================================');
    console.log('🚀 XML Proxy Server Started');
    console.log('================================================');
    console.log(`Local:  http://localhost:${PORT}`);
    console.log(`Target: https://${TARGET_HOST}:${TARGET_PORT}${TARGET_PATH}`);
    console.log('');
    console.log('Use these URLs in your browser:');
    console.log(`  Contracts: http://localhost:${PORT}/contracts`);
    console.log(`  Consumer:  http://localhost:${PORT}/consumers/2,1`);
    console.log('');
    console.log('Press Ctrl+C to stop');
    console.log('================================================');
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\nShutting down proxy server...');
    server.close();
    process.exit(0);
});
