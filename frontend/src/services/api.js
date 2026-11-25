import axios from 'axios';

const rawApiBase = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '/api').trim().replace(/\/+$/, '');
const normalizedBase = rawApiBase.replace(/(\/api)+$/i, '') + '/api';
const API_BASE_URL = rawApiBase === '/api' ? '/api' : normalizedBase;

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT token and prevent duplicated /api/api prefixes
api.interceptors.request.use(
  (config) => {
    if (typeof config.url === 'string' && config.url.startsWith('/api/')) {
      config.url = config.url.slice(4);
    }
    const token = localStorage.getItem('meetmind_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor to handle session expiration
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      // If token expired, clear and optionally redirect if not on public pages
      const publicPaths = ['/login', '/register', '/accept-invitation', '/'];
      if (!publicPaths.some((p) => window.location.pathname.startsWith(p))) {
        localStorage.removeItem('meetmind_token');
        localStorage.removeItem('meetmind_user');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export function getWebSocketUrl(path) {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const customWs = (import.meta.env.VITE_WS_BASE_URL || '').trim().replace(/\/+$/, '');
  if (customWs) {
    return `${customWs}${cleanPath}`;
  }
  if (/^https?:\/\//i.test(API_BASE_URL)) {
    const wsBase = API_BASE_URL.replace(/^http/i, 'ws').replace(/\/api$/i, '');
    return `${wsBase}${cleanPath}`;
  }
  const loc = window.location;
  const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = loc.port === '5173' ? 'localhost:8000' : loc.host;
  return `${protocol}//${host}${cleanPath}`;
}

export default api;
