import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT token to every request if available
api.interceptors.request.use(
  (config) => {
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
  const customWs = import.meta.env.VITE_WS_BASE_URL;
  if (customWs) {
    return `${customWs}${path.startsWith('/') ? path : `/${path}`}`;
  }
  const loc = window.location;
  const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  // If Vite dev server with proxy or direct
  const host = loc.port === '5173' ? 'localhost:8000' : loc.host;
  return `${protocol}//${host}${path.startsWith('/') ? path : `/${path}`}`;
}

export default api;
