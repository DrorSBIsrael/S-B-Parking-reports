// ===================================
// S&B Parking Reports - Main Server
// ===================================

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const compression = require('compression');
const path = require('path');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3001;

// ===================================
// Security & Middleware
// ===================================

// Security headers
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com"],
      scriptSrc: ["'self'", "https://cdnjs.cloudflare.com"],
      imgSrc: ["'self'", "data:", "https:"],
      connectSrc: ["'self'"],
      fontSrc: ["'self'", "https://fonts.gstatic.com"],
    },
  },
}));

// Compression
app.use(compression());

// CORS configuration
const allowedOrigins = process.env.ALLOWED_ORIGINS ? 
  process.env.ALLOWED_ORIGINS.split(',') : 
  ['http://localhost:3000'];

app.use(cors({
  origin: function (origin, callback) {
    // Allow requests with no origin (mobile apps, etc.)
    if (!origin) return callback(null, true);
    
    if (allowedOrigins.indexOf(origin) !== -1) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));

// Request logging
app.use(morgan(process.env.NODE_ENV === 'production' ? 'combined' : 'dev'));

// Body parsing
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Static files
app.use('/uploads', express.static(path.join(__dirname, '../uploads')));

// ===================================
// Rate Limiting
// ===================================

const rateLimit = require('express-rate-limit');

const limiter = rateLimit({
  windowMs: (process.env.RATE_LIMIT_WINDOW || 15) * 60 * 1000, // 15 minutes
  max: process.env.RATE_LIMIT_MAX_REQUESTS || 100, // limit each IP to 100 requests per windowMs
  message: {
    error: 'Too many requests from this IP, please try again later.',
    retryAfter: 'Check the Retry-After header for when to retry'
  },
  standardHeaders: true,
  legacyHeaders: false,
});

app.use('/api/', limiter);

// ===================================
// Routes
// ===================================

// Import route handlers
const authRoutes = require('./routes/auth');
const dataRoutes = require('./routes/data');
const uploadRoutes = require('./routes/upload');
const whatsappRoutes = require('./routes/whatsapp');
const adminRoutes = require('./routes/admin');

// API routes
app.use('/api/auth', authRoutes);
app.use('/api/data', dataRoutes);
app.use('/api/upload', uploadRoutes);
app.use('/api/whatsapp', whatsappRoutes);
app.use('/api/admin', adminRoutes);

// ===================================
// Health Check & Info
// ===================================

app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'OK',
    service: 'S&B Parking Reports API',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
    environment: process.env.NODE_ENV,
    uptime: process.uptime()
  });
});

app.get('/api/info', (req, res) => {
  res.json({
    name: 'S&B Parking Reports API',
    version: '1.0.0',
    description: 'Backend API for S&B Parking Reports Dashboard',
    endpoints: {
      auth: '/api/auth',
      data: '/api/data', 
      upload: '/api/upload',
      whatsapp: '/api/whatsapp',
      admin: '/api/admin',
      health: '/api/health'
    }
  });
});

// ===================================
// Error Handling
// ===================================

// 404 handler
app.use('*', (req, res) => {
  res.status(404).json({ 
    error: 'Route not found',
    message: `Cannot ${req.method} ${req.originalUrl}`,
    availableEndpoints: [
      'GET /api/health',
      'GET /api/info',
      'POST /api/auth/login',
      'GET /api/data/dashboard',
    ]
  });
});

// Global error handler
app.use((err, req, res, next) => {
  console.error('Error occurred:', {
    message: err.message,
    stack: process.env.NODE_ENV === 'development' ? err.stack : undefined,
    url: req.originalUrl,
    method: req.method,
    ip: req.ip,
    timestamp: new Date().toISOString()
  });

  // CORS errors
  if (err.message === 'Not allowed by CORS') {
    return res.status(403).json({
      error: 'CORS Error',
      message: 'Origin not allowed by CORS policy'
    });
  }

  // JWT errors
  if (err.name === 'JsonWebTokenError') {
    return res.status(401).json({
      error: 'Invalid token',
      message: 'The provided token is invalid'
    });
  }

  // Validation errors
  if (err.name === 'ValidationError') {
    return res.status(400).json({
      error: 'Validation Error',
      message: err.message
    });
  }

  // Default error response
  res.status(err.status || 500).json({ 
    error: 'Internal Server Error',
    message: process.env.NODE_ENV === 'development' ? err.message : 'Something went wrong!',
    ...(process.env.NODE_ENV === 'development' && { stack: err.stack })
  });
});

// ===================================
// Graceful Shutdown
// ===================================

process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('SIGINT received, shutting down gracefully');
  process.exit(0);
});

// ===================================
// Start Server
// ===================================

app.listen(PORT, () => {
  console.log('🚀 S&B Parking Reports API Server Started');
  console.log('=====================================');
  console.log(`📡 Port: ${PORT}`);
  console.log(`🌍 Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`🔗 Health Check: http://localhost:${PORT}/api/health`);
  console.log(`📊 API Info: http://localhost:${PORT}/api/info`);
  console.log(`🕒 Started at: ${new Date().toISOString()}`);
  console.log('=====================================');
  
  // Log important configuration
  if (process.env.NODE_ENV === 'development') {
    console.log('🔧 Development Configuration:');
    console.log(`   Database: ${process.env.SUPABASE_URL ? '✅ Connected' : '❌ Not configured'}`);
    console.log(`   JWT Secret: ${process.env.JWT_SECRET ? '✅ Set' : '❌ Missing'}`);
    console.log(`   WhatsApp: ${process.env.GREENAPI_ID ? '✅ Configured' : '⚠️  Not configured'}`);
    console.log('=====================================');
  }
});

module.exports = app;
