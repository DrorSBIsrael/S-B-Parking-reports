/**
 * Development Proxy Server
 * Handles CORS and HTTPS certificate issues for local development
 */

const express = require('express');
const cors = require('cors');
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = 3000;

// Enable CORS for all origins in development
app.use(cors());

// Parse JSON bodies
app.use(express.json());

// Serve static files
app.use(express.static('.'));

// Configuration for the parking server
// NOTE: This should be configured dynamically from database (parkings table)
// This file is deprecated - use Flask proxy instead
const PARKING_SERVER = {
    host: 'CONFIGURE_FROM_DB',  // Should be loaded from parkings table
    port: 8443,
    protocol: 'https'
};

// Proxy middleware to forward requests to parking server
app.use('/api', (req, res) => {
    console.log(`Proxying ${req.method} ${req.path} to parking server`);
    
    const options = {
        hostname: PARKING_SERVER.host,
        port: PARKING_SERVER.port,
        path: `/api${req.path}`,
        method: req.method,
        headers: {
            ...req.headers,
            host: PARKING_SERVER.host
        },
        // Ignore self-signed certificate errors in development
        rejectUnauthorized: false
    };
    
    const protocol = PARKING_SERVER.protocol === 'https' ? https : http;
    
    const proxyReq = protocol.request(options, (proxyRes) => {
        // Set CORS headers
        res.set('Access-Control-Allow-Origin', '*');
        res.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, PATCH');
        res.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
        
        // Forward status code
        res.status(proxyRes.statusCode);
        
        // Forward headers
        Object.keys(proxyRes.headers).forEach(key => {
            res.set(key, proxyRes.headers[key]);
        });
        
        // Forward response body
        proxyRes.pipe(res);
    });
    
    proxyReq.on('error', (error) => {
        console.error('Proxy error:', error);
        res.status(500).json({ 
            error: 'Proxy error', 
            message: error.message,
            details: 'Could not connect to parking server'
        });
    });
    
    // Forward request body
    if (req.body && Object.keys(req.body).length > 0) {
        proxyReq.write(JSON.stringify(req.body));
    }
    
    proxyReq.end();
});

// Handle OPTIONS requests for CORS preflight
app.options('*', cors());

// Fallback route - serve the main HTML file
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'parking_subscribers.html'));
});

// Start server
app.listen(PORT, () => {
    console.log(`
    ========================================
    🚗 Parking Management Proxy Server
    ========================================
    
    Local Server:     http://localhost:${PORT}
    Parking Server:   ${PARKING_SERVER.protocol}://${PARKING_SERVER.host}:${PARKING_SERVER.port}
    
    Open your browser at: http://localhost:${PORT}
    
    This proxy server will:
    - Handle CORS issues
    - Bypass HTTPS certificate warnings
    - Forward requests to the parking server
    
    Press Ctrl+C to stop the server
    ========================================
    `);
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\n\nShutting down proxy server...');
    process.exit(0);
});

