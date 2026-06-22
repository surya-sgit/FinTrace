import axios from 'axios';

// Create a configured Axios instance
const api = axios.create({
    baseURL: 'http://localhost:8000/api/v1', // Your FastAPI base URL
    headers: {
        'Content-Type': 'application/json',
    },
});

// Request Interceptor: Attach the JWT token automatically
api.interceptors.request.use(
    (config) => {
        // We only run this on the client side (browser)
        if (typeof window !== 'undefined') {
            const token = localStorage.getItem('fintrace_token');
            if (token && config.headers) {
                config.headers.Authorization = `Bearer ${token}`;
            }
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Response Interceptor: Handle expired tokens globally
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response && error.response.status === 401) {
            // If the backend says the token is invalid/expired, wipe it and force logout
            if (typeof window !== 'undefined') {
                localStorage.removeItem('fintrace_token');
                // Redirect to login page
                window.location.href = '/login';
            }
        }
        return Promise.reject(error);
    }
);

export default api;
